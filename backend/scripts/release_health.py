"""Read-only release preflight: python -m scripts.release_health [--dependencies-only]."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_TIMEOUT_SECONDS = 180  # First CPU load of both BGE models dominates; inference itself is tiny.


def retrieval_runtime(config, timeout=None):
    """Real, bounded embedding + rerank on fixed synthetic text; returns (ok, detail).

    Catches runtime failures the artifact check cannot, such as a native DLL refused by
    OS code-integrity policy. Local files only, no download, no confidential data; the
    detail names only the failing stage and exception type, never exception text.
    """
    import threading
    import time
    timeout = RUNTIME_TIMEOUT_SECONDS if timeout is None else timeout
    outcome = {}

    def run():
        stage, started = "Embedding runtime", time.perf_counter()
        try:
            from app.services.embeddings import get_embeddings
            vector = get_embeddings().embed(["Synthetic pump vibration reading for a release health check."])[0]
            if len(vector) != 768:
                raise ValueError("unexpected embedding dimension")
            if config.reranking_enabled:
                stage = "Reranker runtime"
                from app.services.reranking import get_reranker
                scores = get_reranker().score("synthetic pump vibration",
                    ["Synthetic pump vibration note for testing.", "Unrelated synthetic cafeteria menu."])
                if len(scores) != 2 or not scores[0] > scores[1]:
                    raise ValueError("implausible reranker ordering")
            outcome["seconds"] = time.perf_counter() - started
        except Exception as error:
            outcome["error"] = (stage, type(error).__name__)

    # Daemon thread: a hung native load can fail this check without blocking process exit.
    worker = threading.Thread(target=run, name="release-retrieval-runtime", daemon=True)
    worker.start()
    worker.join(timeout)
    if worker.is_alive():
        return False, f"Retrieval runtime exceeded {timeout:g}s; check CPU load, native runtime policy and local model artifacts"
    if "error" in outcome:
        stage, kind = outcome["error"]
        return False, (f"{stage} failed ({kind}); check native runtime policy (e.g. a blocked DLL), "
                       "installed packages and local model artifacts")
    reranked = "reranked 2 synthetic passages" if config.reranking_enabled else "reranking disabled"
    return True, f"Embedded 1 synthetic string (768-d), {reranked} in {outcome['seconds']:.1f}s; no confidential data"


def exit_code(rows):
    return int(any(row["status"] == "FAIL" for row in rows))


def collect(*, dependencies_only=False):
    # Import inside the command: malformed configuration must produce a safe FAIL, not a secret traceback.
    from alembic.config import Config
    from alembic.migration import MigrationContext
    from alembic.script import ScriptDirectory
    import httpx
    from sqlalchemy import create_engine
    from sqlalchemy.engine import make_url
    from sqlalchemy.pool import NullPool
    from app.core.config import settings as s
    from app.core.locality import classify_http_url, require_private_resolution
    from app.services import language_resources, local_voice, readiness
    from app.services.sovereignty_service import get_sovereignty_proof

    rows = []

    def add(name, ok, detail, *, optional=False):
        rows.append({"name": name, "status": "PASS" if ok else ("WARNING" if optional else "FAIL"), "detail": detail})

    def probe(name, check, detail, *, optional=False):
        try:
            ok = bool(check())
        except Exception:
            ok = False
        add(name, ok, detail, optional=optional)
        return ok

    database = probe("DATABASE", readiness.check_postgres, "PostgreSQL reachable; inspect local service if FAIL")

    def migrations():
        engine = create_engine(s.database_url, poolclass=NullPool,
                               connect_args={"connect_timeout": 3, "options": "-c statement_timeout=3000"})
        try:
            with engine.connect() as conn:
                current = set(MigrationContext.configure(conn).get_current_heads())
            expected = set(ScriptDirectory.from_config(Config(str(ROOT / "backend/alembic.ini"))).get_heads())
            return current == expected
        finally:
            engine.dispose()

    probe("MIGRATIONS", lambda: database and migrations(), "Run reviewed alembic upgrade head if behind; no automatic migration")
    probe("QDRANT", readiness.check_qdrant, "Qdrant /readyz reachable")
    inventory, descriptions = {}, {}

    def ollama():
        require_private_resolution(s.model_base_url)
        with httpx.Client(base_url=s.model_base_url, timeout=5, trust_env=False, follow_redirects=False) as client:
            version = client.get("/api/version")
            version.raise_for_status()
            if not version.json().get("version"):
                return False
            response = client.get("/api/tags")
            response.raise_for_status()
            inventory.update({m["name"]: m for m in response.json()["models"]})
            for tag in {s.primary_model, s.fast_model, s.pid_vision_model}:
                if tag in inventory:
                    result = client.post("/api/show", json={"model": tag})
                    result.raise_for_status()
                    descriptions[tag] = result.json()
            return True

    probe("OLLAMA", ollama, "Version, model inventory and metadata available; no inference performed")
    for label, tag in (("PRIMARY MODEL", s.primary_model), ("FAST MODEL", s.fast_model)):
        model = inventory.get(tag, {})
        digest = model.get("digest", "")
        quant = model.get("details", {}).get("quantization_level", "")
        expected = s.release_model_digests.get(tag)
        valid = tag in descriptions and (not expected or digest == expected)
        # Strict formats prevent untrusted runtime metadata from becoming arbitrary diagnostic text.
        safe_digest = digest if re.fullmatch(r"(?:sha256:)?[a-f0-9]{64}", digest) else "unavailable"
        safe_quant = quant if re.fullmatch(r"[A-Z0-9_]{1,30}", quant) else "unavailable"
        add(label, valid, f"{tag}; digest={safe_digest}; quantization={safe_quant}; both routing models required")
        add(label + " PIN", bool(expected) and valid, "Set WORKBENCH_RELEASE_MODEL_DIGESTS after approved provisioning", optional=True)
    contexts = [v for tag in (s.primary_model, s.fast_model)
                for k, v in descriptions.get(tag, {}).get("model_info", {}).items() if k.endswith(".context_length")]
    add("RUNTIME CONFIG", s.model_runtime == "ollama" and s.model_name == s.primary_model
        and 0 < s.model_max_output_tokens < s.model_context_window
        and len(contexts) == 2 and all(isinstance(c, int) and c >= s.model_context_window for c in contexts),
        "Ollama primary gateway; output below configured context; installed model context capacity sufficient")
    add("VISION", s.pid_vision_enabled and "vision" in descriptions.get(s.pid_vision_model, {}).get("capabilities", []),
        "Enabled local model must advertise vision; disabled vision leaves OCR workflow available", optional=not s.pid_vision_enabled)
    for name, url in (("STT", s.stt_url), ("TTS", s.tts_url)):
        ready = local_voice.health(url) == "ready"
        detail = "Configured local speech is healthy" if ready else (
            "Configured local speech unavailable; text fallback remains available" if url else
            "Optional speech not configured; text fallback remains available")
        add(name, ready, detail, optional=True)
    paths = [s.data_root, s.model_root]
    probe("DIRECTORIES", lambda: all(p.is_dir() and os.access(p, os.R_OK | os.W_OK) for p in paths),
          "Data/model roots must exist and be readable/writable by the service account")
    probe("DISK", lambda: all(shutil.disk_usage(p).free >= s.release_min_free_gib * 1024**3 for p in paths),
          "Free space meets WORKBENCH_RELEASE_MIN_FREE_GIB; size backups and model RAM separately")
    probe("RETRIEVAL ARTIFACTS", lambda: all((s.model_root / p / "config.json").is_file()
          and any((s.model_root / p).glob("*.safetensors")) for p in
          (["bge-base-en-v1.5", "bge-reranker-base"] if s.reranking_enabled else ["bge-base-en-v1.5"])),
          "Local BGE artifacts present; this is not an inference/quality test")
    add("RETRIEVAL RUNTIME", *retrieval_runtime(s))
    probe("SOVEREIGNTY", lambda: get_sovereignty_proof().status == "sovereign" and s.model_runtime == "ollama",
          "Configured local/private services and local paths; NOT firewall or air-gap attestation")
    add("EGRESS POLICY", s.deployment_mode == "confidential" and not s.bhashini_enabled and not s.government_resources_enabled,
        "Release requires confidential mode and disabled public external integrations")
    probe("RESOURCE REGISTRY", lambda: all(r.classification != "LOCAL_APPROVED" or
          r.deployment != "local_downloaded" or _artifact_matches(r) for r in language_resources.registry(s)),
          "Approved downloaded artifacts require an existing local source file matching SHA-256")
    url = make_url(s.database_url)
    add("SECRETS/CONFIG", bool(url.password) and url.password not in {"postgres", "password", "changeme"}
        and url.username != "postgres" and s.session_cookie_secure and not s.model_log_prompts
        and bool(s.cors_origins) and all(o.startswith("https://") and "*" not in o for o in s.cors_origins)
        and (not s.automation_secret and not s.automation_user_id or len(s.automation_secret) >= 32 and bool(s.automation_user_id)),
        "Production DB credentials/role, Secure cookies, HTTPS CORS and optional webhook secret/principal required")
    if not dependencies_only:
        def backend():
            with httpx.Client(timeout=5, trust_env=False, follow_redirects=False) as client:
                response = client.get("http://127.0.0.1:8000/ready")
                return response.status_code == 200 and response.json().get("status") == "ready"
        probe("BACKEND", backend, "Local backend /ready on port 8000")
        add("FRONTEND", (ROOT / "frontend/dist/index.html").is_file(),
            "Production build exists; TLS proxy/browser acceptance is a deployment requirement")
    return rows


def _artifact_matches(resource):
    import hashlib
    path = Path(resource.source)
    if not path.is_file():
        return False
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest() == resource.artifact_sha256


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dependencies-only", action="store_true", help="Before starting backend/frontend")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        rows = collect(dependencies_only=args.dependencies_only)
    except Exception:
        rows = [{"name": "CONFIGURATION", "status": "FAIL", "detail": "Invalid configuration or unavailable dependency; no values emitted"}]
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        for row in rows:
            print(f"{row['name']:<22} {row['status']:<7} {row['detail']}")
    return exit_code(rows)


if __name__ == "__main__":
    raise SystemExit(main())
