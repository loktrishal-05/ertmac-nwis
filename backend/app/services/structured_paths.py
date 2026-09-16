"""Bounded, path-confined CSV source resolution for maintenance/sensor ingestion."""
from pathlib import Path

from app.core.config import settings


def resolve_structured_source(relative: str, subdir: str) -> Path:
    root = (settings.data_root / "raw" / subdir).resolve()
    requested = Path(relative)
    if requested.is_absolute() or requested.drive or ":" in relative or ".." in requested.parts:
        raise ValueError(f"Use a relative path inside data/raw/{subdir}")
    path = (root / requested).resolve()
    if not path.is_relative_to(root) or not path.is_file() or path.suffix.lower() != ".csv":
        raise ValueError(f"Expected a CSV file inside data/raw/{subdir}")
    return path


def read_csv_source(path: Path) -> bytes:
    with path.open("rb") as stream:
        source = stream.read(settings.structured_csv_max_bytes + 1)
    if not source or len(source) > settings.structured_csv_max_bytes:
        raise ValueError(f"CSV must be between 1 byte and {settings.structured_csv_max_bytes} bytes")
    return source


def decode_csv(source: bytes) -> str:
    try:
        return source.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("CSV must be UTF-8 encoded") from error


def advisory_lock_key(checksum: str) -> int:
    return int.from_bytes(bytes.fromhex(checksum[:16]), "big", signed=True)
