"""Deterministic ranking tests using real local Qdrant and stubbed neural models."""
import unittest
import warnings
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4
from qdrant_client import QdrantClient, models
from pydantic import ValidationError
from app.core.config import settings
from app.schemas.knowledge import RetrieveRequest, RetrieveResponse
from app.services.sparse import encode, terms, identifiers, index_text, ENCODING
from app.services.ranking import fuse, deduplicate
from app.services.qdrant_service import QdrantService
from app.services.retrieval import retrieve
from app.services.retrieval_metrics import metrics
from app.services.pid_indexing import region_chunks
from app.services.reranking import Reranker
from app.services.pid_regions import group_regions
from app.services.paddle_ocr import normalize_result
from app.schemas.pid import PIDManifest
from test_knowledge import metadata, TestTokenizer
from test_pid import result, page_info


def point(item, score=1):
    return SimpleNamespace(id=item.chunk_id, payload=item.model_dump(mode="json"), score=score)


class HybridTests(unittest.TestCase):
    def setUp(self):
        self.client = QdrantClient(":memory:")
        self.addCleanup(self.client.close)
        self.qdrant = QdrantService(self.client)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.qdrant.initialize()

    def test_sparse_encoding_identifiers_and_metadata(self):
        text = "P – 101 A WO-7712 SOP-P204-001 TT-101 API NPSH"
        self.assertIn("p-101a", terms(text))
        self.assertIn("WO-7712", identifiers(text)["technical_identifiers"])
        self.assertIn("P-101A", identifiers(text)["equipment_tags"])
        self.assertEqual(encode(text), encode(text))
        self.assertEqual(encode(text).indices, encode(text, query=True).indices)
        self.assertEqual(encode("the and of").indices, [])
        self.assertTrue(all(v > 0 for v in encode(text).values))
        item = metadata()
        self.assertIn("startup", index_text(item))
        self.assertEqual(terms(index_text(item)).count("p-101a"), 1)

    def test_rrf_deterministic_and_duplicates(self):
        a, b = point(metadata()), point(metadata())
        results = fuse([a, b, a], [b, a])
        self.assertEqual(len(results), 2)
        self.assertAlmostEqual(results[0]["fusion_score"], 1 / 61 + 1 / 62)
        self.assertEqual([str(r["point"].id) for r in results], sorted([str(a.id), str(b.id)]))
        self.assertEqual(fuse([a, b, a], [b, a]), results)

    def test_real_sparse_search_and_scope_filters(self):
        a = metadata().model_copy(update={"content": "WO-7712 repair log and NPSH investigation"})
        b = metadata().model_copy(update={"content": "WO-9999 unrelated log", "access_scope": "restricted"})
        self.qdrant.upsert([a, b], [[1.0] + [0.0] * 767] * 2)
        points = self.qdrant.sparse_search("WO-7712", 30, {"access_scope": "internal"})
        self.assertEqual([p.id for p in points], [str(a.chunk_id)])
        self.assertEqual(self.qdrant.sparse_search("WO-9999", 30, {"access_scope": "internal"}), [])

    def test_sparse_backfill_idempotence_and_dense_preservation(self):
        item = metadata()
        self.client.upsert(self.qdrant.collection, points=[models.PointStruct(id=str(item.chunk_id), vector={"dense": [1.] + [0.] * 767}, payload=item.model_dump(mode="json"))])
        with self.assertRaises(RuntimeError):
            self.qdrant.sparse_search("P-101A", 2, {})
        self.assertEqual(self.qdrant.migrate_sparse()["updated_points"], 1)
        self.assertEqual(self.qdrant.migrate_sparse()["updated_points"], 0)
        saved = self.client.retrieve(self.qdrant.collection, [str(item.chunk_id)], with_vectors=True)[0]
        self.assertEqual(saved.vector["dense"], [1.] + [0.] * 767)
        self.assertEqual(saved.payload["source_sha256"], item.source_sha256)
        self.assertEqual(saved.payload["sparse_encoding"], ENCODING)

    def test_hybrid_reranker_and_response(self):
        a, b = metadata(), metadata().model_copy(update={"content": "Independent maintenance evidence for WO-7712", "equipment_tags": []})
        self.qdrant.upsert([a, b], [[1.] + [0.] * 767] * 2)
        session = SimpleNamespace(scalars=lambda stmt: SimpleNamespace(all=lambda: [a.document_version_id, b.document_version_id]))
        embeddings = SimpleNamespace(embed=lambda texts, query: [[1.] + [0.] * 767])
        reranker = SimpleNamespace(score=lambda query, texts: [10. if "WO-7712" in text else -10. for text in texts])
        with patch.object(settings, "reranking_enabled", True):
            response = retrieve(RetrieveRequest(query="P-101A WO-7712", strategy="hybrid_rerank"), session, embeddings, self.qdrant, reranker)
        self.assertEqual(response.results[0].chunk_id, b.chunk_id)  # no implicit tag filter
        self.assertEqual(response.results[0].rerank_score, 10.)
        self.assertTrue(response.results[0].sparse_rank)
        self.assertEqual(response.results[0].citation.quote, b.content)
        self.assertEqual(RetrieveResponse.model_validate_json(response.model_dump_json()), response)
        with patch.object(settings, "reranking_enabled", False):
            with patch("app.services.retrieval.get_reranker", side_effect=AssertionError("must not load")):
                response = retrieve(RetrieveRequest(query="P-101A", strategy="hybrid"), session, embeddings, self.qdrant)
                self.assertTrue(all(r.rerank_score is None for r in response.results))
            with self.assertRaises(ValueError):
                retrieve(RetrieveRequest(query="test", strategy="hybrid_rerank"), session)

    def test_filter_bounds_and_conflicts(self):
        for body in ({"top_k": 100000}, {"equipment_tags": ["x"] * 31},
                     {"facility_id": "a", "filters": {"facility_id": "b"}}):
            with self.assertRaises(ValidationError):
                RetrieveRequest(query="test", **body)
        self.assertEqual(RetrieveRequest(query="test", document_types=["pid"]).document_types, ["pid"])

    def test_revision_preference_and_conflicts(self):
        a = metadata().model_copy(update={"effective_date": date(2025, 1, 1), "revision": "A"})
        b = a.model_copy(update={"chunk_id": uuid4(), "document_version_id": uuid4(), "revision": "B", "effective_date": date(2026, 1, 1), "content": "Changed facts P-101B"})
        make = lambda m: {"metadata": m, "point": point(m)}
        kept, warning = deduplicate([make(a), make(b)])
        self.assertEqual([k["metadata"].revision for k in kept], ["B"])
        self.assertTrue(warning)
        b.effective_date = a.effective_date
        kept, warning = deduplicate([make(a), make(b)])
        self.assertEqual(len(kept), 2)
        self.assertIn("Conflicting", warning[0])
        self.assertEqual(len(deduplicate([make(a), make(b)], explicit_version=True)[0]), 2)

    def test_near_duplicate_and_changed_numbers_preserved(self):
        a = metadata().model_copy(update={"content": "P-101A test temperature 80 C. " * 20})
        b = a.model_copy(update={"chunk_id": uuid4(), "content": a.content + "Note."})
        c = a.model_copy(update={"chunk_id": uuid4(), "content": a.content.replace("80", "90")})
        kept, _ = deduplicate([{"metadata": m} for m in (a, b, c)])
        self.assertEqual(len(kept), 2)

    def test_ocr_low_confidence_indexing(self):
        page = page_info()
        detections = normalize_result(result("XV-1010") | {"rec_scores": [0.54]}, page)
        version = uuid4()
        regions = group_regions(detections, version)
        manifest = PIDManifest(document_id=uuid4(), document_version_id=version, source_filename="test.png", source_uri="raw/pids/source/test.png",
                               source_sha256="a" * 64, page_count=1, render_dpi=None, ocr_model=["PP-OCRv5_server_rec"], processed_at=metadata().ingested_at,
                               synthetic=True, warnings=[], pages=[page], ocr_json_uri="x", region_json_uri="y", ocr_detections=1, regions=1,
                               equipment_tags=[], instrument_tags=["XV-1010"])
        chunks = region_chunks(manifest, regions, {"title": "Drawing", "access_scope": "internal"}, TestTokenizer())
        self.assertEqual(chunks[0].ocr_confidence, 0.54)
        self.assertTrue(chunks[0].ocr_derived)
        self.assertEqual(chunks[0].content_type, "pid_region_text")
        self.assertEqual(chunks[0].bounding_boxes[0].coordinates, detections[0].bbox)
        self.qdrant.upsert(chunks, [[1.] + [0.] * 767])
        self.assertEqual(self.qdrant.sparse_search("XV-1010", 2, {})[0].payload["ocr_confidence"], 0.54)
        regions[0].combined_text = "Invented evidence"
        with self.assertRaises(ValueError):
            region_chunks(manifest, regions, {"title": "Drawing", "access_scope": "internal"}, TestTokenizer())

    def test_reranker_lazy_missing_model_and_empty_input(self):
        service = Reranker()
        self.assertIsNone(service._model)
        self.assertEqual(service.score("query", []), [])
        with patch.object(settings, "model_root", settings.data_root / "missing-model-test"):
            with self.assertRaises(RuntimeError):
                service.score("query", ["text"])

    def test_metrics_known_ranks(self):
        actual = metrics(["wrong", "a", "b"], {"a": 2, "b": 1}, 3)
        self.assertEqual(actual["recall"], 1)
        self.assertEqual(actual["precision"], 2 / 3)
        self.assertEqual(actual["mrr"], 0.5)
        self.assertGreater(actual["ndcg"], 0)
        self.assertLess(actual["ndcg"], 1)
        self.assertEqual(metrics([], {}, 3)["empty_result_accuracy"], 1)
        self.assertEqual(metrics(["x"], {}, 3)["empty_result_accuracy"], 0)
        self.assertEqual(metrics(["a", "a"], {"a": 1}, 2)["precision"], 0.5)

    def test_reranker_batches_and_model_reuse(self):
        import torch
        service = Reranker()
        batches = []
        class Inputs(dict):
            def to(self, device):
                return self
        def tokenize(pairs, **kwargs):
            batches.append(len(pairs))
            return Inputs(count=len(pairs))
        class Model:
            device = "cpu"
            def __call__(self, count):
                return SimpleNamespace(logits=torch.ones((count, 1)))
        service._model, service._tokenizer = Model(), tokenize
        self.assertEqual(service.score("test", ["text"] * 17), [1.] * 17)
        self.assertEqual(batches, [8, 8, 1])

    def test_ocr_duplicate_locations_and_negation(self):
        a = metadata().model_copy(update={"ocr_derived": True, "source_image_uri": "page.png", "content": "P-101A",
                                         "bounding_boxes": []})
        from app.schemas.knowledge import BoundingBox
        a.bounding_boxes = [BoundingBox(page=1, coordinates=(10, 10, 100, 40), origin="TOPLEFT")]
        b = a.model_copy(update={"chunk_id": uuid4(), "section_path": ["another region"]})
        self.assertEqual(len(deduplicate([{"metadata": a}, {"metadata": b}])[0]), 1)
        b.bounding_boxes = [BoundingBox(page=1, coordinates=(300, 10, 390, 40), origin="TOPLEFT")]
        self.assertEqual(len(deduplicate([{"metadata": a}, {"metadata": b}])[0]), 2)
        a = metadata().model_copy(update={"content": "The repeated synthetic inspection procedure " * 20 + "is permitted."})
        b = a.model_copy(update={"chunk_id": uuid4(), "content": a.content.replace("is permitted", "is not permitted")})
        self.assertEqual(len(deduplicate([{"metadata": a}, {"metadata": b}])[0]), 2)
