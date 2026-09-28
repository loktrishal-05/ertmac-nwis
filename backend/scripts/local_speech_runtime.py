"""Optional loopback speech shim; provision models separately. No application dependencies."""
import base64
from contextlib import asynccontextmanager
import io
import os
from pathlib import Path
import subprocess
from threading import Lock
import wave

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["DO_NOT_TRACK"] = "1"

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parents[2]
MODEL = ROOT / "models/local-speech/faster-whisper-small"
ESPEAK = Path(os.environ.get("WORKBENCH_ESPEAK_EXE", str(ROOT / "models/local-speech/espeak/eSpeak NG/espeak-ng.exe")))
os.environ["ESPEAK_DATA_PATH"] = str(ESPEAK.parent / "espeak-ng-data")
LANGUAGES = {"en": "en-us", "hi": "hi", "ta": "ta"}
lock = Lock()
model = None


@asynccontextmanager
async def lifespan(app):
    global model
    from faster_whisper import WhisperModel
    if not ESPEAK.is_file():
        raise RuntimeError("Provision the local eSpeak NG executable first")
    for voice in LANGUAGES.values():
        subprocess.run([str(ESPEAK), "-v", voice, "--stdout", "test"], capture_output=True, check=True, timeout=10)
    model = WhisperModel(str(MODEL), device="cpu", compute_type="int8", cpu_threads=4,
                         num_workers=1, local_files_only=True)
    yield
    model = None


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)


@app.middleware("http")
async def loopback_only(request: Request, call_next):
    if not request.client or request.client.host not in {"127.0.0.1", "::1"}:
        return JSONResponse({"detail": "Loopback only"}, status_code=403)
    # No browser access: application-to-adapter requests only.
    if request.headers.get("origin"):
        return JSONResponse({"detail": "Browser requests are not accepted"}, status_code=403)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response


class STTRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    audio_base64: str = Field(max_length=5592408)
    mime_type: str
    language: str


class TTSRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=2000)
    language: str


@app.get("/health")
def health():
    return {"status": "ready", "stt": "faster-whisper-small/cpu/int8", "tts": "espeak-ng",
            "languages": list(LANGUAGES), "audio_retention": "none"}


@app.post("/stt")
def stt(body: STTRequest):
    if body.language not in LANGUAGES or body.mime_type != "audio/wav":
        raise HTTPException(422, "This runtime supports en/hi/ta PCM WAV only")
    try:
        raw = base64.b64decode(body.audio_base64, validate=True)
        if not 0 < len(raw) <= 4 * 1024 * 1024:
            raise ValueError()
        with wave.open(io.BytesIO(raw)) as wav:
            if wav.getnframes() / wav.getframerate() > 60 or wav.getnchannels() not in (1, 2):
                raise ValueError()
    except (ValueError, wave.Error, EOFError):
        raise HTTPException(422, "Invalid PCM WAV or duration over 60 seconds") from None
    if not lock.acquire(blocking=False):
        raise HTTPException(503, "Speech runtime busy; use text fallback")
    try:
        segments, info = model.transcribe(io.BytesIO(raw), language=body.language, beam_size=3,
                                         word_timestamps=True, condition_on_previous_text=False,
                                         vad_filter=False, initial_prompt=None, hotwords=None)
        segments = list(segments)
        words = [{"text": w.word.strip(), "confidence": w.probability} for s in segments for w in (s.words or [])]
        return {"text": "".join(s.text for s in segments).strip(), "language": info.language, "words": words}
    finally:
        lock.release()


@app.post("/tts")
def tts(body: TTSRequest):
    if body.language not in LANGUAGES:
        raise HTTPException(422, "Unsupported language; use text fallback")
    result = subprocess.run([str(ESPEAK), "--stdin", "--stdout", "-v", LANGUAGES[body.language], "-s", "145"],
                            input=body.text.encode("utf-8"), capture_output=True, timeout=20, check=True)
    if len(result.stdout) > 4 * 1024 * 1024:
        raise HTTPException(422, "Speech exceeds audio limit; use text fallback")
    # eSpeak stdout uses a streaming WAV length; normalize it for bounded WAV consumers.
    raw = bytearray(result.stdout)
    if raw[:4] != b"RIFF" or raw[8:12] != b"WAVE" or raw[36:40] != b"data":
        raise HTTPException(503, "Invalid local TTS output")
    raw[4:8] = (len(raw) - 8).to_bytes(4, "little")
    raw[40:44] = (len(raw) - 44).to_bytes(4, "little")
    return {"audio_base64": base64.b64encode(raw).decode("ascii"), "mime_type": "audio/wav"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8765, access_log=False)
