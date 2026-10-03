"""Lazy reusable local BGE execution. Download artifacts separately."""
from functools import lru_cache
from threading import Lock
import math
from app.core.config import settings

QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


class EmbeddingService:
    def __init__(self):
        self._model = None
        self._lock = Lock()

    @property
    def model(self):
        with self._lock:
            if self._model is None and settings.retrieval_runtime == "onnx":
                from app.services.onnx_models import load
                self._model = load("bge-base-en-v1.5")  # (tokenizer, session)
            if self._model is None:
                from sentence_transformers import SentenceTransformer
                path = settings.model_root / "bge-base-en-v1.5"
                if not (path / "config.json").is_file():
                    raise RuntimeError("BGE artifacts unavailable. Run python -m scripts.download_models first.")
                self._model = SentenceTransformer(
                    str(path), local_files_only=True, trust_remote_code=False,
                )
                dimension = getattr(self._model, "get_embedding_dimension", self._model.get_sentence_embedding_dimension)()
                if dimension != settings.embedding_dimension:
                    self._model = None
                    raise RuntimeError("Embedding model must produce 768 dimensions")
            return self._model

    @property
    def tokenizer(self):
        return self.model[0] if settings.retrieval_runtime == "onnx" else self.model.tokenizer

    def embed(self, texts: list[str], query: bool = False) -> list[list[float]]:
        if not texts:
            return []
        inputs = [QUERY_PREFIX + text if query else text for text in texts]
        if settings.retrieval_runtime == "onnx":
            return self._embed_onnx(inputs)
        for text in inputs:
            if len(self.tokenizer.encode(text, add_special_tokens=True)) > self.model.max_seq_length:
                raise ValueError("Embedding input exceeds model token limit; refusing silent truncation")
        vectors = self.model.encode(inputs, batch_size=16, normalize_embeddings=True, show_progress_bar=False)
        return self._checked(vectors.tolist())

    def _embed_onnx(self, inputs):
        import numpy as np
        from app.services.onnx_models import MAX_TOKENS, run
        tokenizer, session = self.model
        if any(len(tokenizer.encode(text)) > MAX_TOKENS for text in inputs):
            raise ValueError("Embedding input exceeds model token limit; refusing silent truncation")
        values = []
        for offset in range(0, len(inputs), 16):
            cls = run(session, tokenizer.encode_batch(inputs[offset:offset + 16]))[:, 0]  # CLS pooling, as 1_Pooling
            values.extend((cls / np.linalg.norm(cls, axis=1, keepdims=True)).tolist())
        return self._checked(values)

    @staticmethod
    def _checked(values):
        if any(len(v) != 768 or not all(math.isfinite(x) for x in v) for v in values):
            raise RuntimeError("Invalid embedding dimensions or values")
        return values


@lru_cache(maxsize=1)
def get_embeddings() -> EmbeddingService:
    return EmbeddingService()
