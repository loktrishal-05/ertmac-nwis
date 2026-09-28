"""Quiesced single-node backup and checksum validation. Restore procedure is in the runbook."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]


def validate_destination(destination, sources):
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError("Backup destination must be new")
    for source in sources:
        source = Path(source).resolve()
        if not source.is_dir() or destination == source or source in destination.parents or destination in source.parents:
            raise ValueError("Backup destination must be separate from existing source directories")
        if any(p.is_symlink() or (hasattr(p, "is_junction") and p.is_junction()) for p in source.rglob("*")):
            raise ValueError("Source tree must not contain filesystem links")
    return destination


def checksum(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify(folder):
    folder = Path(folder).resolve()
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("format") != 1 or not manifest.get("quiesced") or not manifest.get("files"):
        raise ValueError("Unsupported or incomplete backup manifest")
    if "postgres.dump" not in manifest["files"] or not manifest.get("data_included") or not (folder / "data").is_dir():
        raise ValueError("Database and source-file backup required")
    for name, expected in manifest["files"].items():
        path = (folder / name).resolve()
        if folder not in path.parents or not path.is_file() or checksum(path) != expected:
            raise ValueError("Missing, unsafe or corrupt backup member")
    actual = {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file() and p != folder / "manifest.json"}
    if actual != set(manifest["files"]):
        raise ValueError("Unmanifested backup files")
    for snapshot in manifest.get("qdrant", []):
        if (not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", snapshot["collection"])
                or snapshot["file"] != f"qdrant-{snapshot['collection']}.snapshot"
                or snapshot["file"] not in manifest["files"]):
            raise ValueError("Invalid Qdrant snapshot manifest")
    return manifest


def create(destination, *, quiesced=False, compose=False):
    import httpx
    from sqlalchemy.engine import make_url
    from app.core.config import settings as s
    from app.core.locality import require_private_resolution
    if not quiesced:
        raise ValueError("Stop backend, ingestion, n8n and every writer; then use --quiesced")
    destination = validate_destination(destination, [s.data_root, s.model_root])
    url = make_url(s.database_url)
    if url.query:
        raise ValueError("Backup requires a whole database URL without query overrides")
    env = os.environ.copy()
    env.update(PGHOST=url.host or "", PGPORT=str(url.port or 5432), PGUSER=url.username or "",
               PGPASSWORD=url.password or "", PGDATABASE=url.database or "", PGCONNECT_TIMEOUT="5")
    command = ["pg_dump", "--format=custom", "--no-owner", "--no-acl"]
    if compose:
        if url.host not in {"localhost", "127.0.0.1"} or url.port not in {None, 5432}:
            raise ValueError("--compose is only for the bundled loopback PostgreSQL")
        command = ["docker", "compose", "-f", str(ROOT / "infra/docker-compose.yml"), "exec", "-T", "postgres",
                   "pg_dump", "-U", "postgres", "-d", url.database, "--format=custom", "--no-owner", "--no-acl"]
    elif not shutil.which("pg_dump"):
        raise ValueError("Install PostgreSQL 17 client tools or use --compose for the bundled service")
    require_private_resolution(s.qdrant_url)
    destination.mkdir(parents=True)
    # Failed backups deliberately have no manifest; never reuse them as complete backups.
    with (destination / "postgres.dump").open("wb") as output:
        subprocess.run(command, env=env, stdout=output, stderr=subprocess.PIPE, check=True, timeout=3600)
    shutil.copytree(s.data_root, destination / "data")
    snapshots = []
    with httpx.Client(base_url=s.qdrant_url, timeout=300, trust_env=False, follow_redirects=False) as client:
        response = client.get("/collections")
        response.raise_for_status()
        collections = response.json()["result"]["collections"]
        for row in collections:
            name = row["name"]
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", name):
                raise ValueError("Collection name is unsupported for backup")
            response = client.post(f"/collections/{name}/snapshots", params={"wait": "true"})
            response.raise_for_status()
            snapshot = response.json()["result"]["name"]
            if not re.fullmatch(r"[A-Za-z0-9_.-]{1,250}", snapshot):
                raise ValueError("Invalid snapshot name")
            file = f"qdrant-{name}.snapshot"
            with client.stream("GET", f"/collections/{name}/snapshots/{snapshot}") as download:
                download.raise_for_status()
                with (destination / file).open("wb") as output:
                    for chunk in download.iter_bytes():
                        output.write(chunk)
            snapshots.append({"collection": name, "file": file})
    files = {p.relative_to(destination).as_posix(): checksum(p) for p in destination.rglob("*") if p.is_file()}
    manifest = {"format": 1, "quiesced": True, "data_included": True,
                "created_at": datetime.now(timezone.utc).isoformat(), "files": files,
                "qdrant": snapshots, "consistency": "operator-quiesced; not atomic across services",
                "excluded": ["model weights", "secrets", "database roles", "Qdrant aliases/config", "external audit checkpoints"]}
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    verify(destination)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["create", "verify"])
    parser.add_argument("folder", type=Path)
    parser.add_argument("--quiesced", action="store_true")
    parser.add_argument("--compose", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.operation == "create":
            create(args.folder, quiesced=args.quiesced, compose=args.compose)
        else:
            verify(args.folder)
    except Exception:
        print("BACKUP FAIL: invalid configuration, incomplete backup, or unavailable service; no credentials emitted")
        return 1
    print("BACKUP PASS: checksums verified; restore rehearsal remains required")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
