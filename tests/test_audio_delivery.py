from __future__ import annotations

import base64
import io
import json
import threading
import time
import wave
from concurrent.futures import ThreadPoolExecutor

import pytest

from lamina.audio_delivery import AudioDeliveryError, render_audio
from lamina.store import Workspace


def pcm_wav() -> bytes:
    """Tiny deterministic PCM fixture; it is not evidence of listenable speech."""
    stream = io.BytesIO()
    with wave.open(stream, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(b"\x00\x00" * 1600)
    return stream.getvalue()


class AudioProvider:
    identity = "fixture-audio-v1"

    def __init__(self, response=None):
        self.requests = []
        self.response = response or {
            "wav_base64": base64.b64encode(pcm_wav()).decode("ascii"),
            "spoken_text": "A worker with an expired lease needs a fencing token.",
        }

    def call(self, stage, payload):
        assert stage == "production_audio"
        assert payload["stage"] == stage
        assert payload["protocol"] == "lamina-stage-1"
        assert payload["input"]["audio_format"]["encoding"] == "PCM"
        self.requests.append(payload)
        return self.response


def receipt(script="# Lease safety\n\nA worker needs a fencing token."):
    return {
        "format": "podcast-script",
        "status": "ready",
        "title": "Lease safety",
        "markdown": script,
    }


def test_pcm_files_manifest_events_and_stable_cache(tmp_path):
    ws = Workspace(tmp_path / "workspace")
    provider = AudioProvider()
    events = []
    output = tmp_path / "audio"
    links = render_audio(ws, provider, receipt(), output, events.append)
    assert links == {
        "audio": "narration.wav",
        "transcript": "narration.txt",
        "manifest": "audio.json",
    }
    assert (output / "narration.wav").read_bytes() == pcm_wav()
    assert (output / "narration.txt").read_text() == provider.response["spoken_text"]
    manifest = json.loads((output / "audio.json").read_text())
    assert manifest["audio"]["duration_seconds"] == 0.1
    assert manifest["audio"]["sample_rate_hz"] == 16000
    assert manifest["audio"]["channels"] == 1
    assert manifest["audio"]["sha256"]
    assert "not independently transcribed" in manifest["transcript"]["source"]
    assert "not checked" in manifest["verification"]
    assert manifest["execution"]["cache"] == "miss"
    assert [e["status"] for e in events] == ["started", "completed"]
    render_audio(ws, provider, receipt(), output)
    assert len(provider.requests) == 1
    assert (
        json.loads((output / "audio.json").read_text())["execution"]["cache"] == "hit"
    )
    render_audio(ws, provider, receipt("# Lease safety\n\nUpdated script."), output)
    assert len(provider.requests) == 2


def test_rejects_wrong_format_bad_audio_and_provider_paths(tmp_path):
    ws = Workspace(tmp_path / "workspace")
    output = tmp_path / "audio"
    with pytest.raises(AudioDeliveryError, match="podcast-script"):
        render_audio(ws, AudioProvider(), {**receipt(), "format": "assessment"}, output)
    with pytest.raises(AudioDeliveryError, match="ready"):
        render_audio(ws, AudioProvider(), {**receipt(), "status": "review"}, output)
    with pytest.raises(AudioDeliveryError, match="only"):
        render_audio(
            ws,
            AudioProvider(
                {
                    "wav_base64": base64.b64encode(pcm_wav()).decode(),
                    "spoken_text": "hi",
                    "path": "/tmp/escape.wav",
                }
            ),
            receipt(),
            output,
        )
    with pytest.raises(AudioDeliveryError, match="RIFF/WAVE"):
        render_audio(
            ws,
            AudioProvider(
                {
                    "wav_base64": base64.b64encode(b"not audio").decode(),
                    "spoken_text": "hi",
                }
            ),
            receipt(),
            output,
        )
    assert not output.exists()


def test_rejects_zero_duration_and_truncated_pcm(tmp_path):
    ws = Workspace(tmp_path / "workspace")
    empty = io.BytesIO()
    with wave.open(empty, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
    with pytest.raises(AudioDeliveryError, match="zero duration"):
        render_audio(
            ws,
            AudioProvider(
                {
                    "wav_base64": base64.b64encode(empty.getvalue()).decode(),
                    "spoken_text": "hi",
                }
            ),
            receipt(),
            tmp_path / "out",
        )
    truncated = pcm_wav()[:-100]
    with pytest.raises(AudioDeliveryError, match="truncated"):
        render_audio(
            ws,
            AudioProvider(
                {
                    "wav_base64": base64.b64encode(truncated).decode(),
                    "spoken_text": "hi",
                }
            ),
            receipt(),
            tmp_path / "out",
        )


def test_distinct_uncached_scripts_share_one_local_adapter_lane(tmp_path):
    class SlowProvider(AudioProvider):
        def __init__(self):
            super().__init__()
            self.active = 0
            self.peak = 0
            self.lock = threading.Lock()

        def call(self, stage, payload):
            with self.lock:
                self.active += 1
                self.peak = max(self.peak, self.active)
            try:
                time.sleep(0.06)
                return super().call(stage, payload)
            finally:
                with self.lock:
                    self.active -= 1

    ws = Workspace(tmp_path / "workspace")
    provider = SlowProvider()
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(
                render_audio,
                ws,
                provider,
                receipt(f"# Lease safety\n\nDistinct script {i}."),
                tmp_path / f"out-{i}",
            )
            for i in range(2)
        ]
        for future in futures:
            future.result()
    assert len(provider.requests) == 2
    assert provider.peak == 1
