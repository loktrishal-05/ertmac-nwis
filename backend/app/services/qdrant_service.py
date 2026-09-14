"""Named dense vectors; a single extension point for later sparse retrieval."""
from functools import lru_cache
from threading import Lock
from qdrant_client import QdrantClient, models
from app.core.config import settings
from app.schemas.knowledge import ChunkMetadata

PAYLOAD_INDEXES = {
    name: models.PayloadSchemaType.KEYWORD for name in (
        "document_type", "document_id", "document_version_id", "facility_id",
        "unit_id", "equipment_tags", "instrument_tags", "access_scope", "language",
    )
}
PAYLOAD_INDEXES["synthetic"] = models.PayloadSchemaType.BOOL


class QdrantService:
    def __init__(self, client=None):
        self.client = client or QdrantClient(url=settings.qdrant_url, timeout=10)
        self.collection = settings.qdrant_collection
        self._lock = Lock()

    def initialize(self):
        with self._lock:
            if not self.client.collection_exists(self.collection):
                try:
                    self.client.create_collection(
                        self.collection,
                        vectors_config={"dense": models.VectorParams(size=768, distance=models.Distance.COSINE)},
                    )
                except Exception:
                    if not self.client.collection_exists(self.collection):
                        raise
            info = self.client.get_collection(self.collection)
            vectors = info.config.params.vectors
            if not isinstance(vectors, dict) or "dense" not in vectors or vectors["dense"].size != 768 or vectors["dense"].distance != models.Distance.COSINE:
                raise RuntimeError("Existing collection does not match dense/768/cosine; it was not modified")
            for name, kind in PAYLOAD_INDEXES.items():
                if name not in info.payload_schema:
                    self.client.create_payload_index(self.collection, name, field_schema=kind, wait=True)

    def upsert(self, chunks: list[ChunkMetadata], vectors: list[list[float]]):
        if len(chunks) != len(vectors) or any(len(v) != 768 for v in vectors):
            raise ValueError("Chunk/vector count or dimension mismatch")
        for offset in range(0, len(chunks), 32):
            points = [
                models.PointStruct(id=str(chunk.chunk_id), vector={"dense": vector}, payload=chunk.model_dump(mode="json"))
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

    def search(self, vector, top_k, filters):
        must = []
        for name, value in filters.items():
            if value is None or value == []:
                continue
            match = models.MatchAny(any=value) if isinstance(value, list) else models.MatchValue(value=value)
            must.append(models.FieldCondition(key=name, match=match))
        return self.client.query_points(
            self.collection, query=vector, using="dense", limit=top_k,
            query_filter=models.Filter(must=must) if must else None,
            with_payload=True,
        ).points


@lru_cache(maxsize=1)
def get_qdrant():
    return QdrantService()
