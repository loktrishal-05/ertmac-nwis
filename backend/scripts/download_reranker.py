"""Explicit artifact download; runtime reranking never accesses model hosts."""
import json
from app.core.config import settings


def main():
    from huggingface_hub import HfApi, snapshot_download
    revision = HfApi().model_info(settings.reranker_model).sha
    path = settings.model_root / "bge-reranker-base"
    snapshot_download(settings.reranker_model, revision=revision, local_dir=path,
                      allow_patterns=["config.json", "tokenizer*", "special_tokens_map.json", "sentencepiece.bpe.model", "model.safetensors"])
    (path / "download_manifest.json").write_text(json.dumps({"model": settings.reranker_model, "revision": revision}, indent=2), encoding="utf-8")
    print("Local reranker ready:", path, "revision", revision)


if __name__ == "__main__":
    main()
