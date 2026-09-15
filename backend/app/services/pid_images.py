"""Bounded immutable input inspection, rendering, and OpenCV preprocessing."""
from io import BytesIO
from pathlib import Path
import math

import cv2
import numpy as np
import pymupdf
from PIL import Image, ImageOps

from app.core.config import settings
from app.schemas.pid import PIDPage, PreprocessOptions

MAX_BYTES = 20 * 1024 * 1024
MAX_PAGE_PIXELS = 40_000_000
MAX_TOTAL_PIXELS = 120_000_000
MAX_PAGES = 10


def read_pid_source(relative: str):
    root = (settings.data_root / "raw/pids/source").resolve()
    requested = Path(relative)
    if requested.is_absolute() or requested.drive or ":" in relative or ".." in requested.parts:
        raise ValueError("Use a relative path inside data/raw/pids/source")
    path = (root / requested).resolve()
    if not path.is_relative_to(root) or not path.is_file() or path.suffix.lower() not in {".pdf", ".png", ".jpg", ".jpeg"}:
        raise ValueError("Expected a PDF, PNG, JPG, or JPEG inside data/raw/pids/source")
    with path.open("rb") as stream:
        source = stream.read(MAX_BYTES + 1)
    if not source or len(source) > MAX_BYTES:
        raise ValueError("P&ID input must be between 1 byte and 20 MiB")
    return path, source


def check_pixels(width, height):
    if width < 8 or height < 8 or width * height > MAX_PAGE_PIXELS:
        raise ValueError("Invalid image dimensions or page exceeds 40 million pixels")


def load_image(source, suffix):
    try:
        with Image.open(BytesIO(source)) as original:
            allowed = {"PNG"} if suffix == ".png" else {"JPEG"}
            if original.format not in allowed or getattr(original, "n_frames", 1) != 1:
                raise ValueError("Image format does not match its extension or has multiple frames")
            check_pixels(*original.size)
            metadata = {
                "width": original.width, "height": original.height,
                "dpi": original.info.get("dpi"),
                "exif_orientation": original.getexif().get(274, 1),
                "format": original.format,
            }
        # EXIF access may consume PNG's stream; verify on a fresh decoder.
        with Image.open(BytesIO(source)) as verification:
            verification.verify()
        with Image.open(BytesIO(source)) as original:
            image = ImageOps.exif_transpose(original).convert("RGBA")
            white = Image.new("RGBA", image.size, "white")
            white.alpha_composite(image)
            return cv2.cvtColor(np.asarray(white.convert("RGB")), cv2.COLOR_RGB2BGR), metadata
    except (OSError, SyntaxError, Image.DecompressionBombError) as error:
        raise ValueError("Malformed or unreasonable image") from error


def preprocess(image, options: PreprocessOptions):
    """Return processed pixels plus an exact inverse rotation transform."""
    output = image.copy()
    height, width = image.shape[:2]
    rotation = options.rotation_degrees
    forward = np.eye(3)
    if rotation == 90:
        output = cv2.rotate(output, cv2.ROTATE_90_CLOCKWISE)
        forward = np.array([[0, -1, height - 1], [1, 0, 0], [0, 0, 1]], dtype=float)
    elif rotation == 180:
        output = cv2.rotate(output, cv2.ROTATE_180)
        forward = np.array([[-1, 0, width - 1], [0, -1, height - 1], [0, 0, 1]], dtype=float)
    elif rotation == 270:
        output = cv2.rotate(output, cv2.ROTATE_90_COUNTERCLOCKWISE)
        forward = np.array([[0, 1, 0], [-1, 0, width - 1], [0, 0, 1]], dtype=float)
    if options.grayscale or options.adaptive_threshold:
        output = cv2.cvtColor(output, cv2.COLOR_BGR2GRAY)
    if options.denoise:
        output = cv2.medianBlur(output, 3)
    if options.contrast_normalization:
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        if output.ndim == 2:
            output = clahe.apply(output)
        else:
            lab = cv2.cvtColor(output, cv2.COLOR_BGR2LAB)
            lab[:, :, 0] = clahe.apply(lab[:, :, 0])
            output = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    if options.adaptive_threshold:
        output = cv2.adaptiveThreshold(output, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                       cv2.THRESH_BINARY, 31, 11)
    return output, np.linalg.inv(forward)


def save_png(path, image):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = cv2.imdecode(np.frombuffer(path.read_bytes(), dtype=np.uint8), cv2.IMREAD_UNCHANGED)
        if existing is None or not np.array_equal(existing, image):
            raise ValueError("Existing page image differs; preserved without overwriting")
        return
    success, data = cv2.imencode(".png", image)
    if not success:
        raise ValueError("Could not encode rendered image")
    with path.open("xb") as stream:
        stream.write(data.tobytes())


def render_pages(source, suffix, version_id, dpi, options):
    """Yield one page at a time; raw source is never written."""
    folder = settings.data_root / "processed/pids/page_images" / str(version_id)

    def save_page(index, image, metadata, actual_dpi):
        height, width = image.shape[:2]
        processed, transform = preprocess(image, options)
        rendered_path = folder / f"page_{index:04d}_rendered.png"
        processed_path = folder / f"page_{index:04d}_processed.png"
        save_png(rendered_path, image)
        save_png(processed_path, processed)
        return PIDPage(
            page=index, width=width, height=height,
            source_image_uri=rendered_path.relative_to(settings.data_root).as_posix(),
            processed_image_uri=processed_path.relative_to(settings.data_root).as_posix(),
            render_dpi=actual_dpi, original_resolution=metadata,
            preprocessing=options, processed_to_rendered=transform.tolist(),
        )

    if suffix != ".pdf":
        image, metadata = load_image(source, suffix)
        yield save_page(1, image, metadata, None)
        return
    if not source.startswith(b"%PDF-"):
        raise ValueError("Invalid PDF signature")
    try:
        with pymupdf.open(stream=source, filetype="pdf") as pdf:
            if pdf.needs_pass or not 1 <= len(pdf) <= MAX_PAGES:
                raise ValueError("PDF must be unencrypted and contain 1 to 10 pages")
            total = 0
            for page in pdf:
                width, height = math.ceil(page.rect.width * dpi / 72), math.ceil(page.rect.height * dpi / 72)
                check_pixels(width, height)
                total += width * height
            if total > MAX_TOTAL_PIXELS:
                raise ValueError("PDF exceeds 120 million total rendered pixels")
            for index, page in enumerate(pdf, 1):
                pixmap = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csRGB, alpha=False)
                image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(pixmap.height, pixmap.width, 3)
                yield save_page(index, cv2.cvtColor(image, cv2.COLOR_RGB2BGR), {
                    "pdf_width_points": page.rect.width, "pdf_height_points": page.rect.height,
                    "pdf_rotation": page.rotation,
                }, dpi)
    except (pymupdf.FileDataError, pymupdf.EmptyFileError) as error:
        raise ValueError("Malformed PDF") from error
