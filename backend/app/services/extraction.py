"""Native PDF extraction; no OCR or generated document content."""
from dataclasses import dataclass, field, asdict
from hashlib import sha256
from pathlib import Path
import re

from app.core.config import settings


def source_sha256(source: bytes) -> str:
    return sha256(source).hexdigest()


@dataclass
class Block:
    text: str
    section_path: list[str]
    page_start: int
    page_end: int
    bounding_boxes: list[dict] = field(default_factory=list)
    content_type: str = "paragraph"


@dataclass
class Extraction:
    status: str
    blocks: list[Block]
    markdown: str
    structured: dict
    report: dict


def inspect_pdf(source: bytes) -> tuple[list[Block], dict]:
    import pymupdf

    blocks = []
    page_reports = []
    with pymupdf.open(stream=source, filetype="pdf") as pdf:
        if pdf.needs_pass:
            raise ValueError("Encrypted PDFs are not supported")
        if not 1 <= len(pdf) <= 100:
            raise ValueError("Prototype PDFs must contain 1 to 100 pages")
        section = []
        for index, page in enumerate(pdf):
            text = page.get_text("text")
            letters = sum(c.isalnum() for c in text)
            images = len(page.get_images())
            page_reports.append({"page": index + 1, "native_characters": letters, "images": images})
            for item in page.get_text("dict", sort=True)["blocks"]:
                if item["type"] != 0:
                    continue
                lines = ["".join(span["text"] for span in line["spans"]) for line in item["lines"]]
                content = "\n".join(lines).strip()
                if not content:
                    continue
                # Only explicit short numbered headings; avoid treating procedure steps as headings.
                if len(content) < 100 and re.match(r"^\d+(?:\.\d+)*\.?\s+[A-Z]", content) and len(lines) == 1:
                    spans = item["lines"][0]["spans"]
                    if any(span["size"] >= 13 or span["flags"] & 16 for span in spans):
                        depth = content.split()[0].rstrip(".").count(".") + 1
                        section = section[:depth - 1] + [content]
                        continue
                blocks.append(Block(content, section.copy(), index + 1, index + 1, [{
                    "page": index + 1, "coordinates": list(item["bbox"]), "origin": "TOPLEFT",
                }]))
        # Conservatively block mixed scanned/native files instead of silently omitting image pages.
        ocr_pages = [p["page"] for p in page_reports if p["native_characters"] < 30 and p["images"]]
        total = sum(p["native_characters"] for p in page_reports)
        report = {"pages": page_reports, "ocr_required_pages": ocr_pages, "native_characters": total}
        return blocks, report


def _docling(source: bytes) -> tuple[list[Block], str, dict]:
    from io import BytesIO
    from docling.datamodel.base_models import InputFormat, DocumentStream
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    artifacts = settings.model_root / "docling"
    if not artifacts.is_dir() or not any(artifacts.iterdir()):
        raise FileNotFoundError("Docling artifacts not cached")
    options = PdfPipelineOptions(
        artifacts_path=artifacts, do_ocr=False, enable_remote_services=False,
        do_picture_description=False, do_picture_classification=False,
        document_timeout=120,
    )
    converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)})
    result = converter.convert(DocumentStream(name="source.pdf", stream=BytesIO(source)))
    if str(result.status.value) != "success":
        raise ValueError("Docling conversion incomplete")
    document = result.document
    blocks = []
    section = []
    for item, _ in document.iterate_items():
        label = getattr(item.label, "value", str(item.label))
        text = getattr(item, "text", "").strip()
        if label in ("section_header", "title"):
            depth = max(1, getattr(item, "level", 1))
            section = section[:depth - 1] + [text]
            continue
        if label in ("page_header", "page_footer", "picture"):
            continue
        if label == "table":
            text = item.export_to_markdown(doc=document)
        if label == "list_item" and getattr(item, "marker", ""):
            text = item.marker + " " + text
        if not text:
            continue
        provenance = getattr(item, "prov", [])
        if not provenance:
            raise ValueError("Docling text missing page provenance")
        pages = [p.page_no for p in provenance]
        boxes = [{
            "page": p.page_no,
            "coordinates": [p.bbox.l, p.bbox.t, p.bbox.r, p.bbox.b],
            "origin": p.bbox.coord_origin.value,
        } for p in provenance]
        blocks.append(Block(text, section.copy(), min(pages), max(pages), boxes, label))
    return blocks, document.export_to_markdown(), document.export_to_dict()


def extract_pdf(source: bytes) -> Extraction:
    fallback, report = inspect_pdf(source)
    report["source_sha256"] = source_sha256(source)
    report["warnings"] = []
    if report["ocr_required_pages"] or report["native_characters"] < 30:
        report.update(status="ocr_required", extraction_method="pymupdf_inspection", extraction_quality="insufficient")
        return Extraction("ocr_required", [], "", {}, report)
    try:
        blocks, markdown, structured = _docling(source)
        if any(b.page_start < 1 or b.page_end > len(report["pages"]) for b in blocks):
            raise ValueError("Docling returned page provenance outside the inspected PDF")
        extracted = sum(sum(c.isalnum() for c in b.text) for b in blocks)
        if not blocks or extracted < report["native_characters"] * 0.5:
            raise ValueError("Docling extracted insufficient native text")
        report.update(extraction_method="docling", extraction_quality="native_text")
    except Exception as error:
        # Explicitly report fallback; no model substitution and no invented OCR output.
        report["warnings"].append(f"Docling unavailable or incomplete ({type(error).__name__}); used PyMuPDF native-text fallback. Table structure may be reduced.")
        blocks = fallback
        markdown = "\n\n".join(
            ("\n".join("#" * (i + 1) + " " + h for i, h in enumerate(b.section_path)) + "\n\n" + b.text).strip()
            for b in blocks
        )
        structured = {"blocks": [asdict(b) for b in blocks]}
        report.update(extraction_method="pymupdf_fallback", extraction_quality="native_text_fallback")
    report["status"] = "extracted"
    return Extraction("extracted", blocks, markdown, structured, report)
