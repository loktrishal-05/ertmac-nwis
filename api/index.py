"""Vercel serverless entry for the hosted NWIS demo: the unchanged FastAPI backend behind the same route
allowlist and /api path mapping as infra/nwis-release/nginx.conf. Secrets come from Vercel env vars."""
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
ORIGIN = "https://sovereign-ai-workbench-nine.vercel.app"

# Neon via the Vercel integration: prefer the direct (unpooled) URL; SQLAlchemy needs the psycopg driver scheme.
_db = os.environ.get("DATABASE_URL_UNPOOLED") or os.environ.get("DATABASE_URL", "")
os.environ["DATABASE_URL"] = re.sub(r"^postgres(ql)?://", "postgresql+psycopg://", _db)
for _key, _value in {
    "WORKBENCH_HOSTED_DEMO": "true", "WORKBENCH_NWIS_ONLY": "true", "RETRIEVAL_RUNTIME": "onnx",
    "WORKBENCH_DEPLOYMENT_MODE": "public", "WORKBENCH_SIGNUP_MODE": "open", "WORKBENCH_GOOGLE_ENABLED": "false",
    "WORKBENCH_CORS_ORIGINS": f'["{ORIGIN}"]', "WORKBENCH_AUTH_FRONTEND_ORIGIN": ORIGIN,
    "SESSION_COOKIE_SECURE": "true", "SESSION_COOKIE_NAME": "workbench_session", "SESSION_TTL_SECONDS": "28800",
    "WORKBENCH_DATA_ROOT": str(ROOT / "data" / "nwis-hosted"), "WORKBENCH_MODEL_ROOT": "/tmp/models",
    "MODEL_NAME": "qwen3.5:9b", "MODEL_BASE_URL": "http://127.0.0.1:11434", "MODEL_ALLOWED_HOSTS": "127.0.0.1",
    "OMP_NUM_THREADS": "2",
}.items():
    os.environ.setdefault(_key, _value)

sys.path.insert(0, str(Path(__file__).resolve().parent))
import logging  # noqa: E402
import threading  # noqa: E402
from anyio import to_thread  # noqa: E402
from _routes import upstream  # noqa: E402
from app.main import app as backend  # noqa: E402

_indexed = threading.Event()
_index_lock = threading.Lock()


def ensure_index():
    """Once per instance, make Qdrant match Neon (idempotent; embeds only changed events). Self-heals a wiped cluster."""
    with _index_lock:
        if _indexed.is_set():
            return
        from app.db.session import SessionLocal
        from app.services.nwis_knowledge import index_events
        try:
            with SessionLocal() as session:
                index_events(session)
            _indexed.set()
        except Exception as error:  # the query itself still reports a clear error; retry on the next search
            # Type only: client exceptions can embed request headers (the Qdrant API key).
            logging.error("NWIS evidence index check failed: %s", type(error).__name__)


async def app(scope, receive, send):
    if scope["type"] == "http":
        path = upstream(scope["path"])
        if path is None:
            await send({"type": "http.response.start", "status": 404, "headers": [(b"content-type", b"application/json")]})
            await send({"type": "http.response.body", "body": b'{"detail":"Route unavailable"}'})
            return
        if path == "/api/query" and not _indexed.is_set():
            await to_thread.run_sync(ensure_index)
        scope = {**scope, "path": path, "raw_path": path.encode()}
    await backend(scope, receive, send)
