"""Deliver finished text and optional audio without losing successful work."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .production_export import export_production


def deliver_production(
    workspace, receipt, plan, output, *, audio_provider=None, progress=None
):
    """Attach delivery outcomes to the receipt before exporting the final report.

    Audio failures leave a readable document and a review outcome. Adapter errors
    stay in the operator console, not a public artifact or browser response.
    """
    output = Path(output)
    links = {}
    if receipt.get("format") == "podcast-script" and audio_provider is not None:
        if receipt.get("status") != "ready":
            receipt["audio_delivery"] = {
                "status": "skipped",
                "reason": "Resolve the script findings before rendering audio.",
            }
        else:
            from .audio_delivery import render_audio

            try:
                links = render_audio(
                    workspace, audio_provider, receipt, output, progress
                )
                manifest = json.loads(
                    (output / links["manifest"]).read_text(encoding="utf-8")
                )
                receipt["audio_delivery"] = {"status": "ready", **manifest}
            except Exception as exc:
                print(
                    f"Lamina audio delivery failed: {type(exc).__name__}: {exc}",
                    file=sys.stderr,
                    flush=True,
                )
                receipt["audio_delivery"] = {
                    "status": "review",
                    "reason": "Audio rendering failed. The finished script is retained; inspect the local console and resume.",
                }
                receipt["status"] = "review"
    return {**export_production(receipt, plan, output), **links}
