"""Speech prefetch for podcast scripts during section writing."""

from __future__ import annotations

from .store import digest


class SpeechLane:
    """Synthesize podcast sections while other sections are still being written.

    Each finished section becomes the same cached segment that delivery will
    assemble, so the speech work overlaps writing instead of following it. The
    lane is bounded by the speech adapter's declared concurrency; a failed
    prefetch is recorded and retried by delivery, never fatal here.
    """

    def __init__(self, workspace, audio_provider, audio_output, opts, progress):
        from concurrent.futures import ThreadPoolExecutor

        self.active = (
            audio_provider is not None
            and audio_output is not None
            and opts["format"] == "podcast-script"
        )
        if not self.active:
            return
        from pathlib import Path
        from .audio_delivery import _speech_provider

        self.workspace, self.provider = workspace, audio_provider
        self.output, self.progress = Path(audio_output), progress
        speech = _speech_provider(audio_provider)
        self.workers = (
            getattr(speech, "audio_concurrency", 1)
            if getattr(speech, "audio_resource", None)
            else 1
        )
        self.pool = ThreadPoolExecutor(max_workers=self.workers)
        self.futures = {}

    def submit(self, section, draft):
        if not self.active:
            return
        from .audio_delivery import render_audio

        body, title = draft.get("body"), draft.get("title")
        if not isinstance(body, str) or not body.strip() or not title:
            return
        folder = self.output / "segments" / digest(section["id"])[:24]
        receipt = {
            "format": "podcast-script",
            "status": "ready",
            "title": title,
            "markdown": body,
        }

        def report(event):
            if self.progress:
                self.progress({**event, "item": section["id"], "lane": "speech_prefetch"})

        self.futures[section["id"]] = self.pool.submit(
            render_audio, self.workspace, self.provider, receipt, folder, report
        )

    def close(self):
        if not self.active:
            return None
        rendered, failed = [], []
        for sid, future in self.futures.items():
            try:
                future.result()
                rendered.append(sid)
            except Exception as exc:
                failed.append({"section_id": sid, "error": str(exc)})
        self.pool.shutdown(wait=True)
        return {
            "speech_workers": self.workers,
            "rendered_sections": rendered,
            "failed_sections": failed,
            "scope": "Segments synthesized during writing; delivery assembles them from cache.",
        }
