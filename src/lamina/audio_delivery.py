"""Optional local WAV delivery for a completed podcast-script receipt.

The adapter reports the words it submitted to synthesis. That is a transcript
record, not an ASR check or evidence that a listener heard an acceptable file.
"""

from __future__ import annotations

import base64
import binascii
import getpass
import hashlib
import io
import json
import os
import tempfile
import time
import uuid
import wave
from pathlib import Path
from typing import Callable

from filelock import FileLock

from .store import Workspace, canonical, digest

REVISION = "lamina-audio-delivery-1"
STAGE = "production_audio"
MAX_WAV_BYTES = 20_000_000
MIN_LOCK_TIMEOUT_SECONDS = 600


class AudioDeliveryError(ValueError):
    """Invalid audio request or rendered adapter output."""


def _text(value: object, label: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise AudioDeliveryError(
            f"{label} must be nonempty text of at most {maximum} characters"
        )
    return value


def _wav(raw: bytes) -> dict:
    if not raw or len(raw) > MAX_WAV_BYTES:
        raise AudioDeliveryError(
            f"WAV must be nonempty and at most {MAX_WAV_BYTES} bytes"
        )
    if raw[:4] != b"RIFF" or raw[8:12] != b"WAVE":
        raise AudioDeliveryError("adapter did not return a RIFF/WAVE file")
    try:
        with wave.open(io.BytesIO(raw), "rb") as source:
            if source.getcomptype() != "NONE":
                raise AudioDeliveryError("WAV must contain uncompressed PCM")
            channels = source.getnchannels()
            rate = source.getframerate()
            width = source.getsampwidth()
            frames = source.getnframes()
            if not (
                1 <= channels <= 8
                and 8000 <= rate <= 192000
                and 1 <= width <= 4
                and frames > 0
            ):
                raise AudioDeliveryError(
                    "WAV has invalid PCM dimensions or zero duration"
                )
            content = source.readframes(frames)
            if len(content) != frames * channels * width:
                raise AudioDeliveryError("WAV PCM data is truncated")
    except (wave.Error, EOFError) as exc:
        raise AudioDeliveryError("WAV cannot be parsed as uncompressed PCM") from exc
    return {
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
        "duration_seconds": round(frames / rate, 6),
        "channels": channels,
        "sample_rate_hz": rate,
        "sample_width_bytes": width,
        "frames": frames,
    }


def _reply(raw: object) -> dict:
    if not isinstance(raw, dict) or set(raw) != {"wav_base64", "spoken_text"}:
        raise AudioDeliveryError(
            "audio adapter must return wav_base64 and spoken_text only"
        )
    encoded = _text(raw["wav_base64"], "wav_base64", (MAX_WAV_BYTES * 4 // 3) + 8)
    try:
        audio = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise AudioDeliveryError("wav_base64 is invalid") from exc
    _wav(audio)
    spoken = _text(raw["spoken_text"], "spoken_text", 500000)
    return {"wav_base64": encoded, "spoken_text": spoken}


def _write_atomic(path: Path, content: bytes) -> None:
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temporary.write_bytes(content)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _local_audio_lock() -> Path:
    """Use one lock per local user, across workspaces and Python processes."""
    if hasattr(os, "getuid"):
        user_token = str(os.getuid())
    else:
        user_token = hashlib.sha256(getpass.getuser().encode("utf-8")).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / f"lamina-audio-{user_token}.lock"


def _lock_timeout(provider) -> float:
    """Wait at least 600 s and at least a configured adapter call's timeout.

    The extra 30 s covers adapter startup/teardown. A busy peer can still
    exhaust this wait; it is not a distributed queue or a GPU capacity claim.
    """
    configured = getattr(provider, "timeout", 0)
    try:
        seconds = float(configured)
    except (TypeError, ValueError):
        seconds = 0
    return max(MIN_LOCK_TIMEOUT_SECONDS, seconds + 30)


def render_audio(
    workspace: Workspace,
    provider,
    receipt: dict,
    output: Path,
    progress: Callable[[dict], None] | None = None,
) -> dict[str, str]:
    """Render a ready podcast script with a configured command provider.

    The adapter receives the complete finished script and returns base64 PCM WAV
    plus the text it submitted to speech synthesis. Cache identity includes the
    script, title, requested format, adapter identity, and this protocol version.
    A per-local-user process-safe file lock covers only the adapter invocation;
    cache hits never acquire it. The lock wait is at least 600 seconds or the
    adapter timeout plus 30 seconds, whichever is longer.
    """
    if not isinstance(receipt, dict) or receipt.get("format") != "podcast-script":
        raise AudioDeliveryError("audio delivery requires a podcast-script receipt")
    if receipt.get("status") != "ready":
        raise AudioDeliveryError("audio delivery requires a ready podcast script")
    script = _text(receipt.get("markdown"), "podcast script", 500000)
    title = _text(receipt.get("title"), "podcast title", 500)
    identity = _text(getattr(provider, "identity", None), "audio adapter identity", 500)
    if not callable(getattr(provider, "call", None)):
        raise AudioDeliveryError("audio adapter must implement call(stage, envelope)")
    target = Path(output)
    if target.exists() and not target.is_dir():
        raise AudioDeliveryError("audio output must be a directory")
    envelope = {
        "protocol": "lamina-stage-1",
        "revision": REVISION,
        "stage": STAGE,
        "instruction": "Render the supplied finished podcast script to uncompressed PCM WAV. "
        "Return only base64 WAV bytes and the exact text submitted to synthesis. "
        "Do not return file paths or claim listening or transcription verification.",
        "expected_shape": {"wav_base64": "base64 PCM WAV", "spoken_text": "str"},
        "input": {
            "title": title,
            "script": script,
            "audio_format": {
                "container": "WAV",
                "encoding": "PCM",
                "max_bytes": MAX_WAV_BYTES,
            },
        },
    }
    if len(canonical(envelope).encode("utf-8")) > 2_000_000:
        raise AudioDeliveryError("audio adapter request exceeds 2 MB")
    started = time.monotonic()
    invoked = False
    if progress:
        progress({"stage": STAGE, "item": "narration", "status": "started"})

    def handler(payload: dict) -> dict:
        nonlocal invoked
        invoked = True
        with FileLock(str(_local_audio_lock()), timeout=_lock_timeout(provider)):
            raw = provider.call(STAGE, payload)
        return _reply(raw)

    try:
        rendered = workspace.run_cached(
            STAGE, envelope, handler, identity=f"{REVISION}:{identity}", retries=0
        )
        # The cached object is validated again before it can reach the filesystem.
        checked = _reply(rendered)
        wav = base64.b64decode(checked["wav_base64"], validate=True)
        audio_info = _wav(wav)
        spoken = checked["spoken_text"]
        target.mkdir(parents=True, exist_ok=True)
        _write_atomic(target / "narration.wav", wav)
        _write_atomic(target / "narration.txt", spoken.encode("utf-8"))
        manifest = {
            "revision": REVISION,
            "stage": STAGE,
            "title": title,
            "script_sha256": hashlib.sha256(script.encode("utf-8")).hexdigest(),
            "script_digest": digest(script),
            "provider_identity": identity,
            "audio": {"file": "narration.wav", **audio_info},
            "transcript": {
                "file": "narration.txt",
                "sha256": hashlib.sha256(spoken.encode("utf-8")).hexdigest(),
                "source": "adapter-reported synthesis input; not independently transcribed",
            },
            "execution": {
                "cache": "miss" if invoked else "hit",
                "wall_ms": round((time.monotonic() - started) * 1000, 3),
            },
            "verification": "PCM WAV structure, nonzero duration, and file hashes checked. Listening quality, pronunciation, and transcript fidelity were not checked.",
        }
        _write_atomic(
            target / "audio.json",
            (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
        )
    except Exception:
        if progress:
            progress({"stage": STAGE, "item": "narration", "status": "failed"})
        raise
    if progress:
        progress(
            {
                "stage": STAGE,
                "item": "narration",
                "status": "completed",
                "cache": "miss" if invoked else "hit",
            }
        )
    return {
        "audio": "narration.wav",
        "transcript": "narration.txt",
        "manifest": "audio.json",
    }
