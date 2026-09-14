"""Deterministic Phase 3A unit tests; no model downloads or live database needed."""
import re
import unittest
import warnings
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import numpy as np
import pymupdf
from pydantic import ValidationError
from qdrant_client import QdrantClient, models
from app.schemas.knowledge import ChunkMetadata, IngestRequest, RetrieveRequest, RetrieveResponse
from app.services.tags import extract_tags
from app.services.extraction import Block, extract_pdf, source_sha256
from app.services.chunking import Chunker
from app.services.embeddings import EmbeddingService
from app.services.ingestion import duplicate_matches, IngestionConflict, resolve_source
from app.services.qdrant_service import QdrantService
from app.services.retrieval import citation_result


class TestTokenizer:
    """Whitespace offsets for deterministic boundary tests; live test uses BGE."""
    def encode(self, text, add_special_tokens=True):
        return list(range(len(text.split()) + (2 if add_special_tokens else 0)))

    def __call__(self, text, **kwargs):
        return {"offset_mapping": [(m.start(), m.end()) for m in re.finditer(r"\S+", text)]}


def metadata():
    return ChunkMetadata(
        chunk_id=uuid4(), document_id=uuid4(), document_version_id=uuid4(),
        document_type="sop", title="Synthetic Pump SOP", source_filename="test.pdf",
        source_uri="raw/sops/source/test.pdf", source_sha256="a" * 64,
        facility_id=None, unit_id=None, equipment_tags=["P-101A"], instrument_tags=[], line_numbers=[],
        section_path=["1. Startup"], section_title="1. Startup", chunk_index=0,
        content="P-101A is a synthetic test tag.", content_type="paragraph", token_count=25,
        page_start=1, page_end=1, bounding_boxes=[], document_date=None, revision="test",
        effective_date=None, language="en", synthetic=True, extraction_method="pymupdf_fallback",
        extraction_quality="native_text_fallback", access_scope="internal", ingested_at=datetime.now(timezone.utc),
    )


class KnowledgeTests(unittest.TestCase):
    def test_tags(self):
        result = extract_tags('P-101A P-101B V-101 E-101 C-101 FV-101 TT-101 PT-101 FT-101 p-101a 6"-CW-1001-A')
        self.assertEqual(result["equipment_tags"], ["C-101", "E-101", "P-101A", "P-101B", "V-101"])
        self.assertEqual(result["instrument_tags"], ["FT-101", "FV-101", "PT-101", "TT-101"])
        self.assertEqual(result["line_numbers"], ['6"-CW-1001-A'])
        self.assertEqual(extract_tags("XP-101A P-101AB P-101A-2")["equipment_tags"], [])
        self.assertEqual(extract_tags("Z-12", {"custom": r"Z-\d+"}), {"custom": ["Z-12"]})

    def test_sha256(self):
        self.assertEqual(source_sha256(b"abc"), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")

    def test_chunk_boundaries_and_provenance(self):
        blocks = [Block(" ".join(f"word{i}" for i in range(1100)), ["1. Startup"], 2, 2),
                  Block("Separate shutdown evidence.", ["2. Shutdown"], 5, 5)]
        chunks = Chunker(TestTokenizer()).chunk(blocks, "SOP")
        self.assertGreater(len(chunks), 3)
        self.assertTrue(all(c.token_count <= 500 for c in chunks))
        self.assertTrue(all("Document: SOP" in c.embedding_text for c in chunks))
        self.assertEqual(chunks[-1].section_path, ["2. Shutdown"])
        self.assertEqual(chunks[-1].page_start, 5)
        self.assertNotIn("Shutdown", chunks[0].content)
        self.assertTrue(set(chunks[0].content.split()) & set(chunks[1].content.split()))
        for chunk in chunks[:-1]:
            self.assertIn(chunk.content, blocks[0].text)

    def test_small_table_and_steps(self):
        text = "| Tag | State |\n| P-101A | Test |"
        chunks = Chunker(TestTokenizer()).chunk([Block(text, ["Table"], 1, 1, content_type="table")], "Test")
        self.assertEqual(chunks[0].content, text)
        self.assertEqual(chunks[0].content_type, "table")
        steps = [Block(f"{i}. " + "test " * 85, ["Procedure"], 1, 1) for i in range(1, 8)]
        chunks = Chunker(TestTokenizer()).chunk(steps, "Test")
        for step in steps:
            self.assertTrue(any(step.text in chunk.content for chunk in chunks))

    def test_metadata_validation_and_citation(self):
        item = metadata()
        result = citation_result(item, 0.87)
        self.assertEqual(result.citation.quote, item.content)
        self.assertEqual(result.citation.section_path, item.section_path)
        response = RetrieveResponse(query="test", detected_identifiers={}, results=[result])
        self.assertEqual(RetrieveResponse.model_validate_json(response.model_dump_json()), response)
        for update in ({"page_end": 0}, {"source_sha256": "bad"}, {"token_count": 501}):
            with self.assertRaises(ValidationError):
                ChunkMetadata.model_validate(item.model_dump() | update)
        with self.assertRaises(ValidationError):
            RetrieveRequest(query=" ")

    def test_collection_and_dense_search(self):
        client = QdrantClient(":memory:")
        self.addCleanup(client.close)
        service = QdrantService(client)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)  # local Qdrant cannot build payload indexes
            service.initialize()
            service.initialize()
        info = client.get_collection(service.collection)
        self.assertEqual(info.config.params.vectors["dense"].size, 768)
        self.assertEqual(info.config.params.vectors["dense"].distance, models.Distance.COSINE)
        item = metadata()
        vector = [1.0] + [0.0] * 767
        service.upsert([item], [vector])
        self.assertEqual(len(service.search(vector, 3, {"synthetic": True})), 1)
        self.assertEqual(len(service.search(vector, 3, {"synthetic": False})), 0)
        service.delete_version(item.document_version_id)
        self.assertEqual(client.count(service.collection).count, 0)

    def test_incompatible_collection_rejected(self):
        client = QdrantClient(":memory:")
        self.addCleanup(client.close)
        service = QdrantService(client)
        client.create_collection(service.collection, vectors_config={"dense": models.VectorParams(size=3, distance=models.Distance.COSINE)})
        with self.assertRaises(RuntimeError):
            service.initialize()
        self.assertEqual(client.get_collection(service.collection).config.params.vectors["dense"].size, 3)

    def test_embedding_contract(self):
        service = EmbeddingService()
        service._model = SimpleNamespace(
            tokenizer=TestTokenizer(), max_seq_length=512,
            encode=lambda texts, **kwargs: np.ones((len(texts), 768)),
        )
        self.assertEqual(len(service.embed(["a", "b"])), 2)
        self.assertEqual(len(service.embed(["query"], query=True)[0]), 768)
        service._model.encode = lambda texts, **kwargs: np.ones((1, 3))
        with self.assertRaises(RuntimeError):
            service.embed(["bad dimensions"])
        with self.assertRaises(ValueError):
            service.embed(["word " * 600])

    def test_duplicate_handling(self):
        request = IngestRequest(source_path="sops/source/test.pdf", title="Test")
        version = SimpleNamespace(
            ingestion_metadata=request.model_dump(mode="json", exclude={"source_path", "document_id"}),
            status="indexed", document_id=uuid4(),
        )
        self.assertTrue(duplicate_matches(version, request))
        version.ingestion_metadata["source_filename"] = "original.pdf"
        version.ingestion_metadata["source_uri"] = "raw/sops/source/original.pdf"
        self.assertTrue(duplicate_matches(version, request))
        version.status = "failed"
        self.assertFalse(duplicate_matches(version, request))
        with self.assertRaises(IngestionConflict):
            duplicate_matches(version, request.model_copy(update={"title": "Changed"}))

    def test_path_boundary(self):
        for path in ("../../.env", "../test.pdf", "https://example.com/test.pdf"):
            with self.assertRaises(ValueError):
                resolve_source(path)

    def test_native_fallback_and_scanned_detection(self):
        pdf = pymupdf.open()
        self.addCleanup(pdf.close)
        page = pdf.new_page()
        page.insert_text((50, 50), "Synthetic native text for equipment P-101A. Evidence is only for testing.")
        source = pdf.tobytes()
        with patch("app.services.extraction._docling", side_effect=FileNotFoundError):
            result = extract_pdf(source)
        self.assertEqual(result.report["extraction_method"], "pymupdf_fallback")
        self.assertEqual(result.blocks[0].page_start, 1)
        self.assertTrue(result.blocks[0].bounding_boxes)
        scanned = pymupdf.open()
        self.addCleanup(scanned.close)
        image = page.get_pixmap().tobytes("png")
        scanned.new_page().insert_image(pymupdf.Rect(0, 0, 500, 700), stream=image)
        self.assertEqual(extract_pdf(scanned.tobytes()).status, "ocr_required")
