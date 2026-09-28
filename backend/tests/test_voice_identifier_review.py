"""D-LIVE structural warnings: raw text is evidence, never a corrected tag."""
import base64
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import httpx
import test_advanced_c
from app.services import local_voice as voice


class IdentifierReviewTests(unittest.TestCase):
    def test_malformed_tags_and_documents(self):
        samples = ("P204A", "P 204 A", "P-204 A", "P204-A", "XV204D", "XV 204 D", "XV-204 D",
                   "SOP P204-001", "SOC P204-001", "SOP-P204 001", "WO7745", "WO 7745",
                   "FV87B", "NRV 987 C", "M432-D", "DOC M432-002", "DWC M432-002")
        for raw in samples:
            with self.subTest(raw=raw):
                text = "Review " + raw + " today."
                items = voice.identifier_review(text)
                self.assertTrue(any(i["raw_span"] == raw for i in items), items)
                for item in items:
                    self.assertEqual(text[item["start"]:item["end"]], item["raw_span"])
                    self.assertTrue(item["review_required"])
                    self.assertTrue(item["confirmation_required"])
                    # No registry consulted: even an obvious candidate is not invented.
                    self.assertEqual(item["candidates"], [])

    def test_valid_identifiers_and_ordinary_text(self):
        for raw in ("P-204A", "XV-204D", "SOP-P204-001", "WO-7745", "FV-87B",
                    "7.1 mm/s", "42 rpm", "ISO 9001", "pump vibration is elevated"):
            with self.subTest(raw=raw):
                self.assertEqual(voice.identifier_review(raw), [])

    def test_units_and_orphan_fragment(self):
        for raw in ("7.1mm-S", "7.1 mm-S", "7 point 1 millimeters per second", "12.4 kg-h", "15204D"):
            with self.subTest(raw=raw):
                self.assertTrue(any(i["raw_span"] == raw for i in voice.identifier_review(raw)))
        self.assertFalse(any("XV" in str(i["candidates"]) for i in voice.identifier_review("Roman 15204D")))

    def test_raw_transcript_language_hints_and_no_correction_llm(self):
        audio = base64.b64encode(test_advanced_c.wav_bytes()).decode()
        raw = "P204A Roman 15204D SOC P204-001 7.1mm-S"
        for language in ("en", "hi", "ta"):
            with self.subTest(language=language), \
                    patch.object(voice, "exchange", return_value={"text": raw}) as exchange, \
                    patch("socket.socket", side_effect=AssertionError("No correction network call")):
                result = voice.transcribe(audio, "audio/wav", language)
                self.assertEqual(result["text"], raw)
                self.assertEqual(result["original_text"], raw)
                self.assertTrue(result["confirmation_required"])
                self.assertGreaterEqual(len(result["identifier_review"]), 4)
                exchange.assert_called_once_with(voice.settings.stt_url,
                    {"audio_base64": audio, "mime_type": "audio/wav", "language": language})

    def test_failure_fallbacks(self):
        audio = base64.b64encode(test_advanced_c.wav_bytes()).decode()
        with patch.object(voice, "exchange", side_effect=httpx.ConnectError("offline")):
            stt = voice.transcribe(audio, "audio/wav", "hi")
            tts = voice.synthesize("Original Tamil/Hindi answer", "ta")
        self.assertEqual((stt["status"], stt["fallback"]), ("unavailable", "editable_text"))
        self.assertEqual((tts["status"], tts["fallback"], tts["text"]),
                         ("unavailable", "text", "Original Tamil/Hindi answer"))

    def test_runtime_language_hints_reach_model(self):
        with patch.dict(os.environ):
            from scripts import local_speech_runtime as runtime
        audio = base64.b64encode(test_advanced_c.wav_bytes()).decode()
        for language in ("hi", "ta"):
            with self.subTest(language=language), patch.object(runtime, "model") as model:
                model.transcribe.return_value = ([], SimpleNamespace(language=language))
                runtime.stt(runtime.STTRequest(audio_base64=audio, mime_type="audio/wav", language=language))
                self.assertEqual(model.transcribe.call_args.kwargs["language"], language)
                self.assertFalse(model.transcribe.call_args.kwargs["condition_on_previous_text"])


if __name__ == "__main__":
    unittest.main()
