"""Explicit artifact download only; runtime inference stays local."""
import argparse
from app.core.config import settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--docling", action="store_true", help="Also download Docling layout/table artifacts")
    args = parser.parse_args()
    from huggingface_hub import snapshot_download
    destination = settings.model_root / "bge-base-en-v1.5"
    destination.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=settings.embedding_model, local_dir=destination,
        allow_patterns=["*.json", "*.txt", "*.safetensors", "1_Pooling/*"],
    )
    print("BGE artifacts ready:", destination)
    if args.docling:
        from docling.utils.model_downloader import download_models
        download_models(
            output_dir=settings.model_root / "docling",
            with_layout=True, with_tableformer=True,
            with_code_formula=False, with_picture_classifier=False,
            with_smolvlm=False, with_granitedocling=False,
            with_easyocr=False, with_rapidocr=False,
        )
        print("Docling artifacts ready")


if __name__ == "__main__":
    main()
