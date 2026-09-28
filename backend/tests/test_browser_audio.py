"""Real in-memory codec round trips; synthetic silence, no models or network."""
import base64
import io
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import av
from fastapi import HTTPException
from fastapi.testclient import TestClient
import httpx

from scripts import local_speech_runtime as runtime
from app.services import local_voice


def audio(container_format, codec, seconds=1):
    output = io.BytesIO()
    rate = 16000 if container_format == "wav" else 48000
    with av.open(output, "w", format=container_format) as container:
        stream = container.add_stream(codec, rate=rate)
        stream.layout = "mono"
        for index in range(seconds * 10):
            frame = av.AudioFrame(format="s16", layout="mono", samples=rate // 10)
            frame.sample_rate = rate
            frame.pts = index * (rate // 10)
            frame.planes[0].update(bytes(frame.planes[0].buffer_size))
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode(None):
            container.mux(packet)
    return base64.b64encode(output.getvalue()).decode()


class BrowserAudioTests(unittest.TestCase):
    def test_browser_formats_reach_whisper_as_bounded_samples(self):
        for fmt, codec, mime in (("webm", "libopus", "audio/webm"), ("ogg", "libopus", "audio/ogg"),
                                 ("mp4", "aac", "audio/mp4"), ("wav", "pcm_s16le", "audio/wav")):
            with self.subTest(mime=mime), patch.object(runtime, "model") as model:
                model.transcribe.return_value = ([], SimpleNamespace(language="en"))
                runtime.stt(runtime.STTRequest(audio_base64=audio(fmt, codec), mime_type=mime, language="en"))
                samples = model.transcribe.call_args.args[0]
                self.assertEqual(samples.dtype.name, "float32")
                self.assertEqual(samples.ndim, 1)
                self.assertTrue(15000 <= len(samples) <= 18000)

    def test_limits_invalid_data_and_lock_cleanup(self):
        cases = [(audio("wav", "pcm_s16le", 61), "audio/wav", 422),
                 (audio("ogg", "libopus", 61), "audio/ogg", 422),
                 (audio("webm", "libopus", 61), "audio/webm", 422),
                 (audio("mp4", "aac", 61), "audio/mp4", 422),
                 (base64.b64encode(b"RIFF0000WAVE" + bytes(4 * 1024 * 1024)).decode(), "audio/wav", 422),
                 ("invalid", "audio/wav", 422),
                 (base64.b64encode(b"OggSbroken").decode(), "audio/ogg", 415),
                 ("AAAA", "audio/unknown", 415)]
        with patch.object(runtime, "model") as model:
            for value, mime, status in cases:
                with self.subTest(mime=mime, status=status), self.assertRaises(HTTPException) as error:
                    runtime.stt(runtime.STTRequest.model_construct(audio_base64=value, mime_type=mime, language="en"))
                self.assertEqual(error.exception.status_code, status)
                self.assertFalse(runtime.lock.locked())
            model.transcribe.assert_not_called()
        samples = runtime.decode_audio(runtime.STTRequest(audio_base64=audio("wav", "pcm_s16le", 60),
                                                          mime_type="audio/wav", language="en"))
        self.assertEqual(len(samples), 60 * 16000)

    def test_adapter_maps_input_failures_distinctly(self):
        for status, reason in ((415, "unsupported_audio_format"), (422, "invalid_audio"), (503, "runtime_unavailable")):
            response = httpx.Response(status, request=httpx.Request("POST", "http://127.0.0.1/stt"))
            error = httpx.HTTPStatusError("failure", request=response.request, response=response)
            with patch.object(local_voice, "exchange", side_effect=error):
                result = local_voice.transcribe(audio("wav", "pcm_s16le"), "audio/wav", "en")
            self.assertEqual(result["reason"], reason)

    def test_runtime_rejects_nonloopback_and_browser_origin(self):
        for host, headers in (("192.168.1.2", {}), ("127.0.0.1", {"origin": "http://localhost"})):
            client = TestClient(runtime.app, client=(host, 1234))
            self.assertEqual(client.post("/stt", headers=headers, json={}).status_code, 403)
