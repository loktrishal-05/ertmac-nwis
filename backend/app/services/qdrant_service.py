"""Named dense and sparse vectors, preserving collection and point identities."""
from functools import lru_cache
from threading import Lock
from qdrant_client import QdrantClient, models
from app.core.config import settings
from app.schemas.knowledge import ChunkMetadata
from app.services.sparse import ENCODING, encode, index_text

PAYLOAD_INDEXES = {
    name: models.PayloadSchemaType.KEYWORD for name in (
        "document_type", "document_id", "document_version_id", "facility_id",
        "unit_id", "equipment_tags", "instrument_tags", "access_scope", "language",
    )
}
PAYLOAD_INDEXES["synthetic"] = models.PayloadSchemaType.BOOL


class QdrantService:
    def __init__(self, client=None):
        self.client = client or QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key, timeout=10, trust_env=False)
        self.collection = settings.qdrant_collection
        self._lock = Lock()

    def initialize(self, require_sparse=None, *, read_only=False):
        require_sparse = settings.sparse_retrieval_enabled if require_sparse is None else require_sparse
        with self._lock:
            if not self.client.collection_exists(self.collection):
                if read_only:
                    raise RuntimeError("Qdrant collection is not initialized; retrieval cannot create it")
                try:
                    self.client.create_collection(
                        self.collection,
                        vectors_config={"dense": models.VectorParams(size=768, distance=models.Distance.COSINE)},
                        sparse_vectors_config={"sparse": models.SparseVectorParams(modifier=models.Modifier.IDF)},
                    )
                except Exception:
                    if not self.client.collection_exists(self.collection):
                        raise
            info = self.client.get_collection(self.collection)
            vectors = info.config.params.vectors
            if not isinstance(vectors, dict) or "dense" not in vectors or vectors["dense"].size != 768 or vectors["dense"].distance != models.Distance.COSINE:
                raise RuntimeError("Existing collection does not match dense/768/cosine; it was not modified")
            sparse = info.config.params.sparse_vectors or {}
            if require_sparse and "sparse" not in sparse:
                raise RuntimeError("Sparse migration required: python -m scripts.reindex_sparse; existing collection preserved")
            if "sparse" in sparse and sparse["sparse"].modifier != models.Modifier.IDF:
                raise RuntimeError("Existing sparse vector must use IDF; collection was not modified")
            if not read_only:
                for name, kind in PAYLOAD_INDEXES.items():
                    if name not in info.payload_schema:
                        self.client.create_payload_index(self.collection, name, field_schema=kind, wait=True)
            # Retrieval remains read-only even when an operator has not yet
            # provisioned every optional payload index; query filters still
            # apply, with the expected performance trade-off.

    def upsert(self, chunks: list[ChunkMetadata], vectors: list[list[float]]):
        if len(chunks) != len(vectors) or any(len(v) != 768 for v in vectors):
            raise ValueError("Chunk/vector count or dimension mismatch")
        has_sparse = "sparse" in (self.client.get_collection(self.collection).config.params.sparse_vectors or {})
        for offset in range(0, len(chunks), 32):
            points = [
                models.PointStruct(id=str(chunk.chunk_id),
                                   vector={"dense": vector} | ({"sparse": encode(index_text(chunk))} if has_sparse else {}),
                                   payload=chunk.model_dump(mode="json") | {"sparse_encoding": ENCODING if has_sparse else None})
                for chunk, vector in zip(chunks[offset:offset + 32], vectors[offset:offset + 32])
            ]
            self.client.upsert(self.collection, points=points, wait=True)

    def delete_version(self, version_id):
        self.client.delete(
            self.collection, wait=True,
            points_selector=models.FilterSelector(filter=models.Filter(must=[
                models.FieldCondition(key="document_version_id", match=models.MatchValue(value=str(version_id))),
            ])),
        )

    @staticmethod
    def filter(filters):
        must = []
        for name, value in filters.items():
            if value is None or value == []:
                continue
            match = models.MatchAny(any=value) if isinstance(value, list) else models.MatchValue(value=value)
            must.append(models.FieldCondition(key=name, match=match))
        return models.Filter(must=must) if must else None

    def search(self, vector, top_k, filters, using="dense"):
        return self.client.query_points(
            self.collection, query=vector, using=using, limit=top_k,
            query_filter=self.filter(filters),
            with_payload=True,
        ).points

    def sparse_search(self, query, top_k, filters):
        query_filter = self.filter(filters) or models.Filter()
        pending = models.Filter(must=query_filter.must, must_not=[
            models.FieldCondition(key="sparse_encoding", match=models.MatchValue(value=ENCODING))])
        if self.client.count(self.collection, count_filter=pending, exact=True).count:
            raise RuntimeError("Sparse backfill incomplete; run python -m scripts.reindex_sparse")
        vector = encode(query, query=True)
        return self.search(vector, top_k, filters, using="sparse") if vector.indices else []

    def migrate_sparse(self, promote=False):
        """Explicit resumable backfill: update only sparse vector and version marker."""
        self.initialize(require_sparse=False)
        info = self.client.get_collection(self.collection)
        if "sparse" not in (info.config.params.sparse_vectors or {}):
            return self.prepare_hybrid_copy(promote)
        offset, updated = None, 0
        while True:
            points, offset = self.client.scroll(self.collection, limit=64, offset=offset, with_payload=True, with_vectors=True)
            for point in points:
                if point.payload.get("sparse_encoding") == ENCODING and "sparse" in point.vector:
                    continue
                metadata = ChunkMetadata.model_validate(point.payload)
                if str(metadata.chunk_id) != str(point.id):
                    raise RuntimeError("Point identity mismatch; migration stopped")
                self.client.update_vectors(self.collection, points=[models.PointVectors(
                    id=point.id, vector={"sparse": encode(index_text(metadata))})], wait=True)
                self.client.set_payload(self.collection, payload={"sparse_encoding": ENCODING}, points=[point.id], wait=True)
                updated += 1
            if offset is None:
                break
        return {"collection": self.collection, "sparse_encoding": ENCODING, "updated_points": updated}

    def prepare_hybrid_copy(self, promote=False):
        """Qdrant 1.17 cannot add a named vector: verified copy + explicit alias promotion.

        Run through the CLI's exclusive database migration lock. External writers
        must be stopped during this maintenance operation.
        """
        import math
        hybrid = self.collection + "_hybrid_v1"
        backup = self.collection + "_dense_backup"
        for name, sparse in ((backup, False), (hybrid, True)):
            if not self.client.collection_exists(name):
                self.client.create_collection(name, vectors_config={"dense": models.VectorParams(size=768, distance=models.Distance.COSINE)},
                                              sparse_vectors_config={"sparse": models.SparseVectorParams(modifier=models.Modifier.IDF)} if sparse else None)
            config = self.client.get_collection(name).config.params
            if config.vectors["dense"].size != 768 or config.vectors["dense"].distance != models.Distance.COSINE:
                raise RuntimeError("Migration target is incompatible; no collections removed")
            if sparse and (config.sparse_vectors or {}).get("sparse") != models.SparseVectorParams(modifier=models.Modifier.IDF):
                raise RuntimeError("Hybrid migration target has incompatible sparse configuration")
        offset, count = None, 0
        while True:
            points, offset = self.client.scroll(self.collection, limit=32, offset=offset, with_vectors=True, with_payload=True)
            old, new = [], []
            for p in points:
                metadata = ChunkMetadata.model_validate(p.payload)
                if str(metadata.chunk_id) != str(p.id):
                    raise RuntimeError("Migration point identity mismatch")
                old.append(models.PointStruct(id=p.id, vector=p.vector, payload=p.payload))
                new.append(models.PointStruct(id=p.id, vector=p.vector | {"sparse": encode(index_text(metadata))},
                                               payload=p.payload | {"sparse_encoding": ENCODING}))
            if points:
                self.client.upsert(backup, points=old, wait=True)
                self.client.upsert(hybrid, points=new, wait=True)
                for name in (backup, hybrid):
                    copied = {str(p.id): p for p in self.client.retrieve(name, ids=[p.id for p in points], with_vectors=True, with_payload=True)}
                    for original in points:
                        copy = copied[str(original.id)]
                        if not all(math.isclose(a, b, abs_tol=1e-6) for a, b in zip(original.vector["dense"], copy.vector["dense"])):
                            raise RuntimeError("Dense vector copy verification failed")
                        expected = original.payload | ({"sparse_encoding": ENCODING} if name == hybrid else {})
                        if copy.payload != expected:
                            raise RuntimeError("Payload copy verification failed")
            count += len(points)
            if offset is None:
                break
        if any(self.client.count(name, exact=True).count != count for name in (self.collection, hybrid, backup)):
            raise RuntimeError("Migration count mismatch; stop writers and inspect target collections")
        for name, kind in PAYLOAD_INDEXES.items():
            self.client.create_payload_index(hybrid, name, field_schema=kind, wait=True)
        if promote:
            # Verified full backup remains. A short maintenance window is required.
            self.client.delete_collection(self.collection)
            try:
                self.client.update_collection_aliases([models.CreateAliasOperation(create_alias=models.CreateAlias(
                    collection_name=hybrid, alias_name=self.collection))])
            except Exception:
                self.client.update_collection_aliases([models.CreateAliasOperation(create_alias=models.CreateAlias(
                    collection_name=backup, alias_name=self.collection))])
                raise
        return {"collection": self.collection, "hybrid_collection": hybrid, "backup_collection": backup,
                "verified_points": count, "promoted": promote, "sparse_encoding": ENCODING}


@lru_cache(maxsize=1)
def get_qdrant():
    return QdrantService()
