"""Explicit PP-OCRv5 artifact download; no OCR is executed remotely."""
from app.core.config import settings
from app.services.paddle_ocr import OCR_MODELS


def main():
    from huggingface_hub import snapshot_download
    for model in OCR_MODELS:
        path = settings.model_root / "paddleocr" / model
        snapshot_download(repo_id="PaddlePaddle/" + model, local_dir=path,
                          allow_patterns=["*.json", "*.pdiparams", "*.yml", "*.yaml"])
        print("Local OCR artifacts ready:", path)


if __name__ == "__main__":
    main()
