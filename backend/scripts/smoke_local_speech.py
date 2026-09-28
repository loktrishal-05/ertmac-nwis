"""Opt-in real loopback speech check with synthetic audio and an isolated DB schema.

Start local_speech_runtime.py first; run from backend with its existing venv.
No microphone, audio files, hosted services or production records are used.
"""
import base64
import io
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
from uuid import uuid4
import wave
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.security import hash_password
from app.db.models import User

ROOT = Path(__file__).resolve().parents[2]
SAMPLES = {
    "en": "Pump P-204A vibration is elevated.",
    "hi": "पंप P-204A का कंपन बढ़ा हुआ है।",
    "ta": "P-204A பம்பின் அதிர்வு அதிகமாக உள்ளது.",
    "identifiers": "P-204A. XV-204D. SOP-P204-001. 7.1 mm/s.",
}


def main():
    schema = "test_dlive_" + uuid4().hex
    admin = create_engine(settings.database_url)
    engine = server = None
    results = {"synthetic_only": True, "samples": {}, "runtime_url": "http://127.0.0.1:8765"}
    output = ROOT / "data/dlive-repair-results.json"
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    try:
        url = make_url(settings.database_url).update_query_dict({"options": "-csearch_path=" + schema})
        engine = create_engine(url)
        with patch.object(settings, "database_url", url.render_as_string(hide_password=False)):
            command.upgrade(Config(str(ROOT / "backend/alembic.ini")), "head")
        password = secrets.token_urlsafe(32)
        with Session(engine) as session:
            session.add(User(username="dlive_synthetic", role="requester", password_hash=hash_password(password)))
            session.commit()
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        env = {**os.environ, "DATABASE_URL": url.render_as_string(hide_password=False),
               "WORKBENCH_STT_URL": "http://127.0.0.1:8765/stt",
               "WORKBENCH_TTS_URL": "http://127.0.0.1:8765/tts",
               "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}
        with (ROOT / "data/dlive-backend.log").open("w") as log:
            server = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
                                       "--port", str(port), "--no-access-log"], cwd=ROOT / "backend", env=env,
                                      stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False, timeout=120) as app, \
                httpx.Client(base_url=results["runtime_url"], trust_env=False, timeout=120) as runtime:
            for _ in range(120):
                try:
                    if app.get("/health").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                if server.poll() is not None:
                    raise RuntimeError("Backend startup failed; see data/dlive-backend.log")
                time.sleep(0.5)
            response = app.post("/auth/login", json={"username": "dlive_synthetic", "password": password})
            response.raise_for_status()
            results["backend_health"] = app.get("/product/status").json()
            assert results["backend_health"]["stt_health"] == results["backend_health"]["tts_health"] == "ready"
            for label, sentence in SAMPLES.items():
                lang = "en" if label == "identifiers" else label
                start = time.perf_counter()
                response = runtime.post("/tts", json={"text": sentence, "language": lang})
                response.raise_for_status()
                audio = response.json()
                tts_seconds = time.perf_counter() - start
                with wave.open(io.BytesIO(base64.b64decode(audio["audio_base64"]))) as wav:
                    duration = wav.getnframes() / wav.getframerate()
                start = time.perf_counter()
                response = app.post("/voice/transcribe", json={**audio, "input_language": lang})
                response.raise_for_status()
                transcript = response.json()
                stt_seconds = time.perf_counter() - start
                assert transcript["status"] == "ok", transcript
                assert transcript["text"] == transcript["original_text"] and transcript["confirmation_required"]
                assert transcript["review_message"]
                if label in ("en", "identifiers"):
                    assert transcript["review_required"], transcript
                    for item in transcript["identifier_review"]:
                        assert item["raw_span"] == transcript["text"][item["start"]:item["end"]]
                        assert item["review_required"] and item["confirmation_required"]
                        assert item["candidates"] == []
                if label == "identifiers":
                    for raw in ("P204A", "15204D", "SOC P204-001", "7.1mm-S"):
                        assert any(i["raw_span"] == raw for i in transcript["identifier_review"]), transcript
                start = time.perf_counter()
                response = app.post("/voice/synthesize", json={"text": sentence, "input_language": lang})
                response.raise_for_status()
                spoken = response.json()
                assert spoken["status"] == "ok" and spoken["text"] == sentence
                with wave.open(io.BytesIO(base64.b64decode(spoken["audio_base64"], validate=True))) as wav:
                    assert wav.getnframes() > 0 and wav.getsampwidth() == 2
                    assert len(wav.readframes(wav.getnframes())) == wav.getnframes() * wav.getnchannels() * 2
                results["samples"][label] = {"input": sentence, "audio_seconds": duration,
                    "tts_seconds": tts_seconds, "adapter_tts_seconds": time.perf_counter() - start,
                    "stt_seconds": stt_seconds, "transcript": transcript,
                    "tts_text_unchanged": spoken["text"] == sentence}
                output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
                print(label, "STT seconds:", round(stt_seconds, 3), flush=True)
            # Confidence is a model word probability, not a calibrated accuracy score.
            response = runtime.post("/stt", json={**audio, "language": "en"})
            response.raise_for_status()
            results["identifier_word_probabilities"] = response.json()
            unsupported = app.post("/voice/synthesize", json={"text": "Original safe text", "input_language": "fr"}).json()
            assert unsupported["status"] == "unsupported_language" and unsupported["text"] == "Original safe text"
            assert unsupported["fallback"] == "text"
            results["unsupported_tts"] = unsupported
            assert runtime.post("/tts", json={"text": "test", "language": "fr"}).status_code == 422
            assert runtime.post("/stt", json={"audio_base64": "bad", "mime_type": "audio/wav", "language": "en"}).status_code == 422
            assert runtime.get("/health", headers={"Origin": "http://example.com"}).status_code == 403
            results["runtime_input_checks"] = "passed"
            results["validation_complete"] = True
            app.post("/auth/logout").raise_for_status()
    finally:
        if server:
            server.terminate()
            server.wait(timeout=15)
        if engine:
            engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
        results["temporary_schema_removed"] = True
        output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
