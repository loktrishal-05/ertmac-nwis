"""Tiny synthetic corpus through real ingestion; one explicitly simulated OCR case.

This controlled 0.54-confidence case tests evidence handling, not OCR accuracy.
Real OCR accuracy is checked separately by scripts.smoke_pid --fresh.
"""
import json
from types import SimpleNamespace
import pymupdf
from PIL import Image, ImageDraw
from app.core.config import settings
from app.db.session import SessionLocal
from app.schemas.knowledge import IngestRequest
from app.schemas.pid import PIDProcessRequest
from app.services.ingestion import ingest
from app.services.pid_processing import process_pid
from app.services.paddle_ocr import normalize_result
from app.services.pid_indexing import index_pid

SCOPE = "synthetic-retrieval-eval"


def main():
    corpus = json.loads((settings.data_root / "evaluation/retrieval_corpus.json").read_text(encoding="utf-8"))
    for doc in corpus:
        source = settings.data_root / "raw/sops/source" / ("retrieval_eval_" + doc["id"] + ".pdf")
        if not source.exists():
            source.parent.mkdir(parents=True, exist_ok=True)
            with pymupdf.open() as pdf:
                page = pdf.new_page()
                page.insert_text((50, 50), doc["section"], fontsize=16)
                assert page.insert_textbox(pymupdf.Rect(50, 90, 545, 750), doc["text"], fontsize=12) >= 0
                pdf.save(source)
        with SessionLocal() as session:
            result = ingest(IngestRequest(source_path=source.relative_to(settings.data_root / "raw").as_posix(),
                                          title=doc["title"], document_type=doc["document_type"], revision="SYNTHETIC-1",
                                          synthetic=True, access_scope=SCOPE), session)
        print(doc["id"], result.status, flush=True)
    source = settings.data_root / "raw/pids/source/retrieval_eval_ambiguous_ocr.png"
    if not source.exists():
        image = Image.new("RGB", (800, 200), "white")
        ImageDraw.Draw(image).text((30, 40), "XV-3010 ambiguous drawing label", fill="black", font_size=32)
        with source.open("xb") as stream:
            image.save(stream, format="PNG")

    def controlled_ocr(pages):
        for page in pages:
            yield normalize_result({"rec_texts": ["XV-3010 ambiguous drawing label"], "rec_scores": [0.54],
                                    "rec_polys": [[[25, 35], [650, 35], [650, 85], [25, 85]]]}, page)

    with SessionLocal() as session:
        result = process_pid(PIDProcessRequest(source_path=source.name, title="Simulated ambiguous OCR evidence",
                                              synthetic=True, access_scope=SCOPE), session, SimpleNamespace(recognize_pages=controlled_ocr))
    with SessionLocal() as session:
        print(index_pid(result.document_version_id, session), flush=True)


if __name__ == "__main__":
    main()
