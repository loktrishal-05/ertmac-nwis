"""Reusable PP-OCRv5 service with explicit local model paths."""
from functools import lru_cache
from threading import Lock
import os
import sys
import numpy as np
from app.core.config import settings
from app.schemas.pid import OCRDetection
from app.services.pid_identifiers import classify_text

OCR_MODELS = ("PP-OCRv5_server_det", "PP-OCRv5_server_rec")


def normalize_result(result, page):
    """Map Paddle's processed-image polygons back to rendered-image pixels."""
    texts = result.get("rec_texts", [])
    scores = result.get("rec_scores", [])
    polygons = result.get("rec_polys", [])
    if not len(texts) == len(scores) == len(polygons):
        raise ValueError("OCR output text/score/polygon lengths differ")
    if len(texts) > 5000:
        raise ValueError("OCR page exceeds prototype detection limit")
    transform = np.asarray(page.processed_to_rendered, dtype=float)
    detections = []
    for text, score, polygon in zip(texts, scores, polygons):
        if not text.strip():
            continue
        points = np.asarray(polygon, dtype=float)
        if points.ndim != 2 or points.shape[1] != 2 or len(points) < 3 or not np.isfinite(points).all():
            raise ValueError("Malformed OCR polygon")
        mapped = np.column_stack([points, np.ones(len(points))]) @ transform.T
        points = mapped[:, :2]
        # Detector boxes occasionally touch image edges; accept at most one pixel rounding.
        if (points[:, 0].min() < -1 or points[:, 1].min() < -1 or
                points[:, 0].max() > page.width + 1 or points[:, 1].max() > page.height + 1):
            raise ValueError("OCR coordinates exceed stored rendered image")
        points[:, 0] = np.clip(points[:, 0], 0, page.width)
        points[:, 1] = np.clip(points[:, 1], 0, page.height)
        normalized, category, tags = classify_text(text)
        detections.append(OCRDetection(
            text=text, normalized_text=normalized, confidence=float(score),
            bbox=(float(points[:, 0].min()), float(points[:, 1].min()),
                  float(points[:, 0].max()), float(points[:, 1].max())),
            polygon=points.tolist(), page=page.page, source_image=page.source_image_uri,
            image_width=page.width, image_height=page.height, category=category, identified_tags=tags,
        ))
    return detections


class PaddleOCRService:
    def __init__(self):
        self._model = None
        self._lock = Lock()

    def _load(self):
        if self._model is None:
            paths = [settings.model_root / "paddleocr" / model for model in OCR_MODELS]
            if any(not (path / "inference.pdiparams").is_file() or not (path / "inference.json").is_file() for path in paths):
                raise RuntimeError("PP-OCRv5 artifacts missing; run python -m scripts.download_pid_models")
            # Disable PaddleX's model-host availability probe. Explicit directories prevent downloads.
            os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
            if sys.platform == "win32":
                # Load the existing PyTorch DLLs before Paddle's conflicting Windows DLLs.
                import torch  # noqa: F401
            import paddle
            from paddleocr import PaddleOCR
            device = "gpu:0" if paddle.is_compiled_with_cuda() and paddle.device.cuda.device_count() else "cpu"
            self._model = PaddleOCR(
                text_detection_model_name=OCR_MODELS[0], text_detection_model_dir=str(paths[0]),
                text_recognition_model_name=OCR_MODELS[1], text_recognition_model_dir=str(paths[1]),
                use_doc_orientation_classify=False, use_doc_unwarping=False, use_textline_orientation=False,
                device=device, enable_mkldnn=True, cpu_threads=4,
            )
        return self._model

    def recognize_pages(self, pages):
        """Yield page detections, bounding memory and serializing predictor access."""
        for page in pages:
            with self._lock:
                model = self._load()
                path = settings.data_root / page.processed_image_uri
                results = list(model.predict(input=str(path), text_rec_score_thresh=0.0))
                if len(results) != 1:
                    raise RuntimeError("OCR did not return exactly one result for the page")
                detections = normalize_result(results[0], page)
            yield detections


@lru_cache(maxsize=1)
def get_paddle_ocr():
    return PaddleOCRService()
