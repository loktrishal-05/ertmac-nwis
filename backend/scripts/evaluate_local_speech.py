"""Opt-in offline decoding comparison; synthetic audio stays in memory."""
import base64
import inspect
import io
import json
import time

from local_speech_runtime import MODEL, ROOT, TTSRequest, tts
from faster_whisper import WhisperModel

SAMPLES = {
    "en": "Pump P-204A vibration is elevated.",
    "hi": "पंप P-204A का कंपन बढ़ा हुआ है।",
    "ta": "P-204A பம்பின் அதிர்வு அதிகமாக உள்ளது.",
    "identifiers": "P-204A. XV-204D. SOP-P204-001. 7.1 mm/s.",
}
CONTEXT = {
    "en": "Industrial maintenance: pump, valve, vibration, SOP, work order.",
    "hi": "औद्योगिक रखरखाव: पंप, वाल्व, कंपन, कार्य आदेश।",
    "ta": "தொழிற்சாலை பராமரிப்பு: பம்ப், வால்வு, அதிர்வு, பணி ஆணை.",
}


def main():
    model = WhisperModel(str(MODEL), device="cpu", compute_type="int8", cpu_threads=4,
                         num_workers=1, local_files_only=True)
    profiles = {"baseline": {"beam_size": 3},
                "deterministic_vad": {"beam_size": 5, "temperature": 0.0, "vad_filter": True},
                "generic_context": {"beam_size": 5, "temperature": 0.0, "vad_filter": True}}
    report = {"supported_parameters": list(inspect.signature(model.transcribe).parameters), "trials": []}
    for label, sentence in SAMPLES.items():
        language = "en" if label == "identifiers" else label
        audio = base64.b64decode(tts(TTSRequest(text=sentence, language=language))["audio_base64"])
        for profile, options in profiles.items():
            if profile == "generic_context":
                options = {**options, "initial_prompt": CONTEXT[language]}
            start = time.perf_counter()
            segments, _ = model.transcribe(io.BytesIO(audio), language=language,
                word_timestamps=True, condition_on_previous_text=False, **options)
            transcript = "".join(segment.text for segment in segments).strip()
            report["trials"].append({"label": label, "language": language, "expected": sentence,
                "profile": profile, "options": options, "transcript": transcript,
                "seconds": time.perf_counter() - start})
            (ROOT / "data/dlive-decoding-comparison.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(label, profile, round(report["trials"][-1]["seconds"], 3), flush=True)


if __name__ == "__main__":
    main()
