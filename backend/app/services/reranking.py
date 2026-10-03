"""Lazy local cross-encoder; scores are raw logits, never probabilities."""
from functools import lru_cache
from threading import Lock
import math
from app.core.config import settings


class Reranker:
    def __init__(self):
        self._model = None
        self._tokenizer = None
        self._lock = Lock()

    def _load(self):
        if self._model is None:
            import torch
            from transformers import AutoTokenizer, AutoModelForSequenceClassification
            path = settings.model_root / "bge-reranker-base"
            if not (path / "model.safetensors").is_file():
                raise RuntimeError("Reranker missing; run python -m scripts.download_reranker or disable RERANKING_ENABLED")
            self._tokenizer = AutoTokenizer.from_pretrained(str(path), local_files_only=True, trust_remote_code=False)
            model = AutoModelForSequenceClassification.from_pretrained(str(path), local_files_only=True, trust_remote_code=False, use_safetensors=True)
            self._model = model.to("cuda" if torch.cuda.is_available() else "cpu").eval()

    def _score_onnx(self, query, texts):
        from app.services.onnx_models import load, run
        if self._model is None:
            self._tokenizer, self._model = load("bge-reranker-base", truncate=True)
        scores = []
        for offset in range(0, len(texts), 8):
            scores.extend(run(self._model, self._tokenizer.encode_batch([(query, t) for t in texts[offset:offset + 8]])).reshape(-1).tolist())
        return scores

    def score(self, query, texts):
        if not texts:
            return []
        if settings.retrieval_runtime == "onnx":
            with self._lock:
                scores = self._score_onnx(query, texts)
            if len(scores) != len(texts) or not all(math.isfinite(s) for s in scores):
                raise RuntimeError("Invalid reranker scores")
            return scores
        import torch
        with self._lock:
            self._load()
            scores = []
            for offset in range(0, len(texts), 8):
                inputs = self._tokenizer([[query, t] for t in texts[offset:offset + 8]],
                                         padding=True, truncation=True, max_length=512, return_tensors="pt")
                with torch.inference_mode():
                    logits = self._model(**inputs.to(self._model.device)).logits.view(-1).float().cpu().tolist()
                scores.extend(logits)
            if len(scores) != len(texts) or not all(math.isfinite(s) for s in scores):
                raise RuntimeError("Invalid reranker scores")
            return scores


@lru_cache(maxsize=1)
def get_reranker():
    return Reranker()
