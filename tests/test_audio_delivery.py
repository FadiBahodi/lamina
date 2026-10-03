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


def test_segment_cache_rebuilds_only_changed_speech_and_retains_order(tmp_path):
    provider, ws = AudioProvider(), Workspace(tmp_path / "ws")
    full = {
        **receipt(),
        "sections": [
            {"id": "one", "title": "First", "body": "First speech."},
            {"id": "two", "title": "Second", "body": "Second speech."},
            {"id": "three", "title": "Third", "body": "Third speech."},
        ],
    }
    out = tmp_path / "out"
    render_audio(ws, provider, full, out)
    assert len(provider.requests) == 3
    data = json.loads((out / "audio.json").read_text())
    assert [row["section_id"] for row in data["segments"]] == ["one", "two", "three"]
    assert data["audio"]["duration_seconds"] == pytest.approx(0.3)
    full["sections"][1]["body"] = "Corrected second speech."
    render_audio(ws, provider, full, out)
    assert len(provider.requests) == 4
    assert provider.requests[-1]["input"]["script"] == "Corrected second speech."
    assert (
        json.loads((out / "audio.json").read_text())["segments"][0]["execution"][
            "cache"
        ]
        == "hit"
    )


def test_review_script_renders_only_when_requested_and_names_provisional_sections(
    tmp_path,
):
    provider, ws = AudioProvider(), Workspace(tmp_path / "ws")
    in_review = {
        **receipt(),
        "status": "review",
        "sections": [
            {"id": "one", "title": "First", "body": "First speech."},
            {"id": "two", "title": "Second", "body": "Second speech."},
        ],
        "findings": {"two": [{"issue": "A quantity is unsupported."}]},
    }
    with pytest.raises(AudioDeliveryError, match="ready"):
        render_audio(ws, provider, in_review, tmp_path / "blocked")
    assert provider.requests == []
    render_audio(ws, provider, in_review, tmp_path / "out", require_ready=False)
    assert len(provider.requests) == 2
    data = json.loads((tmp_path / "out" / "audio.json").read_text())
    assert data["script_status"] == "review"
    assert data["provisional_sections"] == ["two"]
    assert [row["section_id"] for row in data["segments"]] == ["one", "two"]
    # A failed script never renders, whatever the policy.
    with pytest.raises(AudioDeliveryError, match="ready"):
        render_audio(
            ws, provider, {**in_review, "status": "failed"}, tmp_path / "failed", require_ready=False
        )


def test_delivery_policy_controls_review_audio(tmp_path, monkeypatch):
    from lamina.production_delivery import deliver_production

    monkeypatch.setattr(
        "lamina.production_delivery.export_production", lambda *a, **k: {"html": "x"}
    )
    provider, ws = AudioProvider(), Workspace(tmp_path / "ws")
    base = {
        **receipt(),
        "status": "review",
        "sections": [{"id": "one", "title": "First", "body": "First speech."}],
        "findings": {"one": [{"issue": "Unsupported."}]},
        "plan_digest": "x",
    }
    skipped = dict(base)
    deliver_production(
        ws, skipped, {}, tmp_path / "a", audio_provider=provider, audio_when="ready"
    )
    assert skipped["audio_delivery"]["status"] == "skipped"
    assert provider.requests == []
    # The default renders a script that is still in review.
    rendered = dict(base)
    links = deliver_production(ws, rendered, {}, tmp_path / "b", audio_provider=provider)
    assert rendered["status"] == "review"
    assert rendered["audio_delivery"]["status"] == "provisional"
    assert rendered["audio_delivery"]["provisional_sections"] == ["one"]
    assert links["audio"] == "narration.wav"
    with pytest.raises(ValueError, match="audio_when"):
        deliver_production(ws, dict(base), {}, tmp_path / "c", audio_when="later")


def test_podcast_sections_are_synthesized_while_writing_and_delivered_from_cache(
    tmp_path,
):
    from lamina.production import build_production, run_production, plan_production
    from lamina.production_delivery import deliver_production
    from test_production import FixtureProvider, workspace as production_workspace

    speech = AudioProvider()
    speech.audio_resource = "fixture-tts"
    speech.audio_concurrency = 2
    order = []

    class Recorder(FixtureProvider):
        def call(self, stage, payload):
            if stage == "production_write":
                order.append(("write", payload["input"]["section"]["id"]))
            return super().call(stage, payload)

    ws = production_workspace(tmp_path / "ws")
    options = {"format": "podcast-script", "workflow": "planned"}
    plan = plan_production(ws, Recorder(), "A short podcast on lease safety", ["s1", "s2"], options)
    out = tmp_path / "out"
    events = []
    receipt = run_production(
        ws,
        Recorder(),
        plan,
        progress=events.append,
        audio_provider=speech,
        audio_output=out,
    )
    sections = [row["id"] for row in receipt["sections"]]
    prefetch = receipt["metrics"]["speech_prefetch"]
    assert prefetch["speech_workers"] == 2
    assert sorted(prefetch["rendered_sections"]) == sorted(sections)
    assert prefetch["failed_sections"] == []
    assert len(speech.requests) == len(sections)
    # Every section's speech request was submitted before the pipeline finished:
    # the lane reports through progress while writing is still running.
    assert any(e.get("lane") == "speech_prefetch" for e in events)
    # Delivery assembles the same cached segments without new synthesis.
    links = deliver_production(ws, receipt, plan, out, audio_provider=speech)
    assert len(speech.requests) == len(sections)
    assert links["audio"] == "narration.wav"
    manifest = json.loads((out / "audio.json").read_text())
    assert [row["section_id"] for row in manifest["segments"]] == sections
    assert all(row["execution"]["cache"] == "hit" for row in manifest["segments"])
    assert receipt["audio_delivery"]["status"] in {"ready", "provisional"}


def test_speech_lane_is_inert_without_an_adapter_or_for_other_formats(tmp_path):
    from lamina.production import build_production
    from test_production import FixtureProvider, workspace as production_workspace

    ws = production_workspace(tmp_path / "ws")
    receipt = build_production(ws, FixtureProvider(), "A guide", ["s1", "s2"], {"workflow": "planned"})
    assert "speech_prefetch" not in receipt["metrics"]
