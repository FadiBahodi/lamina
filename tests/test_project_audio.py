"""Connected podcast-script HTTP project and downloadable local WAV artifact."""

from __future__ import annotations

import base64
import io
import json
import wave

from lamina.production_example import FixtureAdapter
from test_project_api import _call, _finished, _server, _stop, _upload_four


def _fixture_wav() -> bytes:
    """Silent PCM bytes test file handling, not speech or listening quality."""
    stream = io.BytesIO()
    with wave.open(stream, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(b"\0\0" * 1600)
    return stream.getvalue()


class PcmAdapter:
    identity = "http-project-audio-pcm-fixture-v1"

    def __init__(self):
        self.calls = []

    def call(self, stage, envelope):
        assert stage == "production_audio"
        assert envelope["protocol"] == "lamina-stage-1"
        assert envelope["stage"] == stage
        assert envelope["input"]["audio_format"]["encoding"] == "PCM"
        self.calls.append(envelope)
        return {
            "wav_base64": base64.b64encode(_fixture_wav()).decode("ascii"),
            "spoken_text": "Fixture submitted to synthesis.",
        }


def test_podcast_project_delivers_wave_link_and_report(tmp_path, monkeypatch):
    server, thread = _server(tmp_path / "studio", monkeypatch, FixtureAdapter())
    audio = PcmAdapter()
    server.audio_provider = audio
    try:
        code, raw = _call(server, "/api/status")
        assert code == 200
        assert json.loads(raw)["audio_adapter_configured"] is True
        ids = _upload_four(server)
        code, raw = _call(
            server,
            "/api/projects",
            {
                "brief": "Write a short engineering podcast script about lease safety.",
                "source_ids": ids,
                "options": {
                    "workflow": "planned",
                    "format": "podcast-script",
                    "reader_workers": 4,
                    "writer_workers": 4,
                    "review_workers": 4,
                },
            },
        )
        assert code == 202, raw
        result = _finished(server, json.loads(raw)["id"])
        assert result["status"] == "ready", result.get("error")
        assert result["receipt"]["audio_delivery"]["status"] == "ready"
        assert result["receipt"]["audio_delivery"]["audio"]["duration_seconds"] == 0.1
        assert len(audio.calls) == 1
        for name in ("audio", "transcript", "manifest", "report"):
            assert name in result["outputs"]
            assert _call(server, result["outputs"][name])[0] == 200
        assert _call(server, result["outputs"]["audio"])[1] == _fixture_wav()
        assert (
            _call(server, result["outputs"]["transcript"])[1].decode()
            == "Fixture submitted to synthesis."
        )
        manifest = json.loads(_call(server, result["outputs"]["manifest"])[1])
        report = json.loads(_call(server, result["outputs"]["report"])[1])
        assert manifest["audio"]["duration_seconds"] == 0.1
        assert report["audio_delivery"]["status"] == "ready"
        assert (
            report["audio_delivery"]["audio"]["sha256"] == manifest["audio"]["sha256"]
        )
        assert any(
            e["stage"] == "production_audio" and e["status"] == "completed"
            for e in result["events"]
        )
    finally:
        _stop(server, thread)
