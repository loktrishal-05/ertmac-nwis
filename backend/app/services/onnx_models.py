"""int8 ONNX runtime for the same BGE models (no torch), used when RETRIEVAL_RUNTIME=onnx.

Artifacts live under <model_root>/<name>-onnx/. Only the hosted synthetic demo may fetch them, from pinned
Hugging Face revisions, and every file is checked against its SHA-256 before use. Stdlib-only at import so the
Vercel build can run `python3 backend/app/services/onnx_models.py <dir>` to bundle them with the function.
"""
from hashlib import sha256
from pathlib import Path
import urllib.request

MAX_TOKENS = 512
ARTIFACTS = {
    "bge-base-en-v1.5": ("Xenova/bge-base-en-v1.5", "4d6cd88e18e51a5e020c2c305726d76ada9c03cf", {
        "onnx/model_int8.onnx": "b83dfe249580ff1c2d0dcebe61ee565b1f6dcd5c2469632773d4508b9efd0889",
        "tokenizer.json": "d241a60d5e8f04cc1b2b3e9ef7a4921b27bf526d9f6050ab90f9267a1f9e5c66"}),
    "bge-reranker-base": ("Xenova/bge-reranker-base", "280bcc27a84e0b898c251e06fddb25171bd9b101", {
        "onnx/model_int8.onnx": "2059d8ef0b6e935b4845e11b38c9af9e9e2e7b91f69fc99efe03254e0a7da8d3",
        "tokenizer.json": "48564c5c7d3fa64d85d95e65414a542385f88b0f128fd8d4163fd7a57f2be05c"}),
}


def _digest(path):
    h = sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def artifact_dir(name):
    from app.core.config import settings
    return fetch(name, settings.model_root, download=settings.hosted_demo)


def fetch(name, root, download):
    repo, revision, files = ARTIFACTS[name]
    folder = Path(root) / f"{name}-onnx"
    for remote, expected in files.items():
        path = folder / Path(remote).name
        if not path.is_file():
            if not download:
                raise RuntimeError(f"ONNX artifacts for {name} unavailable; place them under {folder}")
            folder.mkdir(parents=True, exist_ok=True)
            part = path.with_suffix(path.suffix + ".part")
            urllib.request.urlretrieve(f"https://huggingface.co/{repo}/resolve/{revision}/{remote}", part)
            part.replace(path)
        if _digest(path) != expected:
            path.unlink(missing_ok=True)
            raise RuntimeError(f"ONNX artifact {path.name} for {name} failed its integrity check")
    return folder


def load(name, truncate=False):
    import onnxruntime as ort
    from tokenizers import Tokenizer
    folder = artifact_dir(name)
    tokenizer = Tokenizer.from_file(str(folder / "tokenizer.json"))
    pad = next(t for t in ("[PAD]", "<pad>") if tokenizer.token_to_id(t) is not None)
    tokenizer.enable_padding(pad_id=tokenizer.token_to_id(pad), pad_token=pad)
    if truncate:
        tokenizer.enable_truncation(MAX_TOKENS)
    session = ort.InferenceSession(str(folder / "model_int8.onnx"), providers=["CPUExecutionProvider"])
    return tokenizer, session


def run(session, encodings):
    import numpy as np
    feed = {"input_ids": np.array([e.ids for e in encodings], dtype=np.int64),
            "attention_mask": np.array([e.attention_mask for e in encodings], dtype=np.int64)}
    if "token_type_ids" in {i.name for i in session.get_inputs()}:
        feed["token_type_ids"] = np.array([e.type_ids for e in encodings], dtype=np.int64)
    return session.run(None, feed)[0]


if __name__ == "__main__":  # Vercel build step: bundle verified artifacts inside the function (no runtime /tmp use)
    import sys
    for artifact in ARTIFACTS:
        print("verified", fetch(artifact, sys.argv[1], download=True))
