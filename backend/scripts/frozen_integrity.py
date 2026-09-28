"""Verify frozen benchmark bytes without loading or executing benchmark cases."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def verify():
    expected = json.loads((ROOT / "infra/frozen_benchmark_sha256.json").read_text(encoding="utf-8"))
    if not expected or any(not name.startswith("benchmark/") or ".." in Path(name).parts for name in expected):
        raise ValueError("Invalid frozen benchmark manifest")
    for name, digest in expected.items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
            raise ValueError("Frozen benchmark integrity mismatch: " + name)
    return len(expected)


if __name__ == "__main__":
    print(f"FROZEN BENCHMARK PASS: {verify()} files; no benchmark execution")
