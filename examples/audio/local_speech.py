#!/usr/bin/env python3
"""Offline Lamina production_audio adapter for macOS say or Linux espeak.

Configure explicitly as a CommandProvider command; this program does not fetch
voices, access a network, or clone anyone's voice. `spoken_text` is the text
submitted to the local synthesizer, not an ASR-verified transcript.
"""

from __future__ import annotations

import base64
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def plain_speech(markdown: str) -> str:
    """Remove simple Markdown notation while retaining the authored words."""
    lines = []
    in_code = False
    for line in markdown.splitlines():
        if line.lstrip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        line = re.sub(r"^\s{0,3}#{1,6}\s+", "", line)
        line = re.sub(r"^\s*[-*]\s+", "", line)
        line = re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", line)
        line = line.replace("**", "").replace("__", "").replace("`", "")
        if line.strip():
            lines.append(line.strip())
    return "\n\n".join(lines)


def main() -> int:
    try:
        request = json.load(sys.stdin)
        if (
            request.get("protocol") != "lamina-stage-1"
            or request.get("stage") != "production_audio"
        ):
            raise ValueError("expected a Lamina production_audio request")
        source = request["input"]["script"]
        if not isinstance(source, str) or not source.strip():
            raise ValueError("script must be nonempty text")
        spoken = plain_speech(source)
        if not spoken:
            raise ValueError("script has no speakable text")
        with tempfile.TemporaryDirectory(prefix="lamina-audio-") as folder:
            root = Path(folder)
            text_file = root / "speech.txt"
            wav_file = root / "narration.wav"
            text_file.write_text(spoken, encoding="utf-8")
            if (
                sys.platform == "darwin"
                and shutil.which("say")
                and shutil.which("afconvert")
            ):
                aiff_file = root / "speech.aiff"
                subprocess.run(
                    ["say", "-f", str(text_file), "-o", str(aiff_file)],
                    check=True,
                    capture_output=True,
                    timeout=600,
                )
                subprocess.run(
                    [
                        "afconvert",
                        "-f",
                        "WAVE",
                        "-d",
                        "LEI16",
                        str(aiff_file),
                        str(wav_file),
                    ],
                    check=True,
                    capture_output=True,
                    timeout=600,
                )
            elif shutil.which("espeak"):
                subprocess.run(
                    ["espeak", "-f", str(text_file), "-w", str(wav_file)],
                    check=True,
                    capture_output=True,
                    timeout=600,
                )
            else:
                raise RuntimeError(
                    "local speech requires macOS say + afconvert or Linux espeak"
                )
            print(
                json.dumps(
                    {
                        "wav_base64": base64.b64encode(wav_file.read_bytes()).decode(
                            "ascii"
                        ),
                        "spoken_text": spoken,
                    },
                    ensure_ascii=False,
                )
            )
        return 0
    except (
        ValueError,
        KeyError,
        OSError,
        RuntimeError,
        subprocess.SubprocessError,
    ) as exc:
        print(f"local speech adapter failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
