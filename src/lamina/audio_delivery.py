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
from contextlib import contextmanager
from pathlib import Path
from typing import Callable

from filelock import FileLock, Timeout

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


def _speech_provider(provider):
    return getattr(provider, "stages", {}).get(
        STAGE, getattr(provider, "default", provider)
    )


@contextmanager
def _audio_slot(provider):
    provider = _speech_provider(provider)
    resource = getattr(provider, "audio_resource", None)
    capacity = getattr(provider, "audio_concurrency", 1)
    if not resource:
        with FileLock(str(_local_audio_lock()), timeout=_lock_timeout(provider)):
            yield
        return
    if (
        not isinstance(resource, str)
        or type(capacity) is not int
        or not 1 <= capacity <= 128
    ):
        raise AudioDeliveryError(
            "audio resource needs a name and concurrency from 1 to 128"
        )
    token = digest(resource)[:24]
    start = time.monotonic()
    while True:
        for slot in range(capacity):
            lock = FileLock(str(_local_audio_lock()) + f".{token}.{slot}")
            try:
                lock.acquire(timeout=0)
            except Timeout:
                continue
            try:
                yield
            finally:
                lock.release()
            return
        if time.monotonic() - start > _lock_timeout(provider):
            raise AudioDeliveryError("timed out waiting for the speech resource")
        time.sleep(0.05)


def render_audio(
    workspace: Workspace,
    provider,
    receipt: dict,
    output: Path,
    progress: Callable[[dict], None] | None = None,
    *,
    require_ready: bool = True,
) -> dict[str, str]:
    """Render a ready podcast script, using sections when available.

    Sectioned receipts use independently cached segments. For a legacy receipt
    without sections, the adapter receives the complete script and returns PCM WAV
    plus the text it submitted to speech synthesis. Cache identity includes the
    script, title, requested format, adapter identity, and this protocol version.
    A per-local-user process-safe file lock covers only the adapter invocation;
    cache hits never acquire it. The lock wait is at least 600 seconds or the
    adapter timeout plus 30 seconds, whichever is longer.

    ``require_ready=False`` renders a script that is still in ``review``. A
    finding on one section is not a reason to withhold the other sections from
    the speech lane; the manifest lists the sections with remaining findings so
    the listener knows which parts are provisional.
    """
    if not isinstance(receipt, dict) or receipt.get("format") != "podcast-script":
        raise AudioDeliveryError("audio delivery requires a podcast-script receipt")
    if receipt.get("status") != "ready":
        if require_ready or receipt.get("status") != "review":
            raise AudioDeliveryError("audio delivery requires a ready podcast script")
    if receipt.get("sections"):
        return render_audio_segments(workspace, provider, receipt, output, progress)
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
        with _audio_slot(provider):
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


def render_audio_segments(workspace, provider, receipt, output, progress=None):
    """Cache each reviewed section and assemble PCM on disk in source order.

    A segment retains the adapter's 20 MB limit. The assembled file has no
    base64 transport and may exceed it. PCM formats must agree; silently
    resampling or truncating speech is forbidden. Prosody remains unmeasured.
    """
    from .execution import bounded_collect

    target = Path(output)
    rows = receipt["sections"]
    if not isinstance(rows, list) or not rows:
        raise AudioDeliveryError("audio segments require finished sections")
    ids = [row.get("id") for row in rows if isinstance(row, dict)]
    if (
        len(ids) != len(rows)
        or any(not isinstance(i, str) or not i for i in ids)
        or len(set(ids)) != len(ids)
    ):
        raise AudioDeliveryError("audio segment IDs must be unique")
    target.mkdir(parents=True, exist_ok=True)

    def segment(row):
        sid = digest(row["id"])[:24]
        body = _text(row.get("body"), "section script", 500000)
        title = _text(row.get("title"), "section title", 500)
        folder = target / "segments" / sid

        def report(event):
            if progress:
                progress(
                    {
                        **event,
                        "item": row["id"],
                        "audio_file": f"segments/{sid}/narration.wav"
                        if event["status"] == "completed"
                        else None,
                    }
                )

        render_audio(
            workspace,
            provider,
            {
                "format": "podcast-script",
                "status": "ready",
                "title": title,
                "markdown": body,
            },
            folder,
            report,
        )
        manifest = json.loads((folder / "audio.json").read_text())
        return {
            "section_id": row["id"],
            "title": title,
            "file": f"segments/{sid}/narration.wav",
            "transcript_file": f"segments/{sid}/narration.txt",
            "audio": manifest["audio"],
            "execution": manifest["execution"],
        }

    speech = _speech_provider(provider)
    workers = (
        getattr(speech, "audio_concurrency", 1)
        if getattr(speech, "audio_resource", None)
        else 1
    )
    outcomes = bounded_collect(segment, rows, workers)
    # Sections that still carry review findings are rendered with the rest and
    # named here, so a listener knows which parts may change after revision.
    remaining = receipt.get("findings") or {}
    provisional = sorted(remaining) if isinstance(remaining, dict) else []
    manifest = {
        "revision": "lamina-segmented-audio-1",
        "stage": STAGE,
        "title": receipt["title"],
        "script_status": receipt.get("status", "ready"),
        "provisional_sections": provisional,
        "segments": [r.value for r in outcomes if r.ok],
        "failed_sections": [rows[r.index]["id"] for r in outcomes if not r.ok],
        "verification": "PCM structure and order checked. Listening quality, pronunciation, transitions and transcript fidelity were not checked.",
    }
    _write_atomic(
        target / "audio-segments.json", (json.dumps(manifest, indent=2) + "\n").encode()
    )
    if manifest["failed_sections"]:
        error = AudioDeliveryError(
            "Some speech segments failed; completed segments are retained"
        )
        error.partial_results = manifest
        raise error

    pending = target / ("narration." + uuid.uuid4().hex + ".tmp")
    params, frames = None, 0
    try:
        with wave.open(str(pending), "wb") as writer:
            for row in manifest["segments"]:
                with wave.open(str(target / row["file"]), "rb") as reader:
                    current = (
                        reader.getnchannels(),
                        reader.getsampwidth(),
                        reader.getframerate(),
                    )
                    if params is None:
                        params = current
                        writer.setnchannels(params[0])
                        writer.setsampwidth(params[1])
                        writer.setframerate(params[2])
                    elif current != params:
                        raise AudioDeliveryError(
                            "Speech segments have different PCM formats"
                        )
                    frames += reader.getnframes()
                    while chunk := reader.readframes(65536):
                        writer.writeframesraw(chunk)
        os.replace(pending, target / "narration.wav")
    finally:
        pending.unlink(missing_ok=True)
    transcript = "\n\n".join(
        (target / row["transcript_file"]).read_text() for row in manifest["segments"]
    )
    _write_atomic(target / "narration.txt", transcript.encode())
    with (target / "narration.wav").open("rb") as stream:
        sha = hashlib.file_digest(stream, "sha256").hexdigest()
    manifest.update(
        audio={
            "file": "narration.wav",
            "sha256": sha,
            "bytes": (target / "narration.wav").stat().st_size,
            "frames": frames,
            "duration_seconds": frames / params[2],
            "channels": params[0],
            "sample_width_bytes": params[1],
            "sample_rate_hz": params[2],
        },
        transcript={
            "file": "narration.txt",
            "source": "adapter-reported synthesis input; not independently transcribed",
        },
        execution={
            "cache": "hit"
            if all(r["execution"]["cache"] == "hit" for r in manifest["segments"])
            else "miss"
        },
    )
    _write_atomic(
        target / "audio.json", (json.dumps(manifest, indent=2) + "\n").encode()
    )
    return {
        "audio": "narration.wav",
        "transcript": "narration.txt",
        "manifest": "audio.json",
    }
