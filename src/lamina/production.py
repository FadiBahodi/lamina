"""Source-grounded, task-shaped production with parallel local reading and writing.

Models choose the content and topology. The production modules own source
boundaries, evidence identity, concurrency, cached jobs, and an inspectable
receipt:

- ``production_plan`` reads the selected sources and plans the sections.
- ``section_context`` builds what each section's writer and reviewer may see.
- ``section_calls`` makes a section's write, review and repair calls.
- ``production_render`` renders finished sections as Markdown.
- ``speech_lane`` synthesizes podcast sections while writing continues.
- ``sweep`` reads straight to cards and publishes the deck.

This module checks a run against its plan, schedules the section pipeline and
assembles the receipt.
"""

from __future__ import annotations

import time
from typing import Callable, NamedTuple

from .call_runtime import CallTracker as _Tracker
from .execution import section_pipeline
from .production_contract import (
    FORMATS,
    REVISION,
    ProductionError,
    _options,
    _str,
    request_limit,
    validated,
)
from .production_plan import (
    _form_exemplar_context,
    _plan_identity,
    _source_bytes,
    _sources,
    plan_production,
)
from .production_render import episode_scripts, render_outputs
from .section_calls import SectionCalls
from .section_context import _require_workload, _section_context, section_contexts
from .source_policy import normalize_production_inputs
from .speech_lane import SpeechLane
from .store import Workspace, digest

__all__ = [
    "FORMATS",
    "REVISION",
    "ProductionError",
    "build_production",
    "episode_scripts",
    "plan_production",
    "request_limit",
    "run_production",
    "validated",
    # Internal helpers that assessment_checks, project_api and tests import
    # from this module.
    "_Tracker",
    "_form_exemplar_context",
    "_options",
    "_plan_identity",
    "_section_context",
    "_sources",
]


def _validate_run_request(workspace, provider, plan, options):
    """Return ``(opts, section_notes)`` for a run of ``plan``, or refuse the run.

    A run may change execution settings. The route, format, source policy and
    selected experience are fixed by the plan.
    """
    if (
        not isinstance(plan, dict)
        or plan.get("revision") != REVISION
        or plan.get("plan_digest") != _plan_identity(plan)
    ):
        raise ProductionError("Invalid or modified production plan")
    if provider.identity != plan.get("provider_identity"):
        raise ProductionError(
            "Production plan was made with a different provider identity"
        )
    run_options = dict(options or {})
    section_notes = run_options.pop("section_notes", {})
    if not isinstance(section_notes, dict) or any(
        not isinstance(k, str) for k in section_notes
    ):
        raise ProductionError("section_notes must map section IDs to revision notes")
    if run_options.get("workflow") == "auto":
        run_options.pop("workflow")
    opts = _options({**plan["options"], **run_options})
    if any(
        opts[key] != plan["options"][key]
        for key in (
            "workflow",
            "assignments",
            "retrieval_targets",
            "compare_relations",
            "relation_neighbors",
        )
    ):
        raise ProductionError("Workflow and assignments require a new plan")
    if opts["format"] != plan["options"]["format"]:
        raise ProductionError("Cannot change output format after planning")
    if any(
        opts[key] != plan["options"][key]
        for key in ("source_policy", "observation_ids", "method_family")
    ):
        raise ProductionError(
            "Source policy and selected experience require a new plan"
        )
    _require_unchanged_sources(workspace, plan)
    return opts, section_notes


def _require_unchanged_sources(workspace, plan):
    """The selected sources must still hold the content the plan read."""
    try:
        selected = normalize_production_inputs(
            workspace, [s["id"] for s in plan["sources"]], plan["options"]
        )
    except ValueError as exc:
        raise ProductionError(str(exc)) from exc
    _, all_units = _sources(workspace, selected["source_ids"])
    selected_units = [
        unit
        for unit in all_units
        if unit["source_id"] in set(selected["factual_source_ids"])
    ]
    selected_exemplars = _form_exemplar_context(
        selected["sources"], all_units, selected["form_exemplar_ids"]
    )
    if (
        digest(selected["sources"]) != digest(plan["sources"])
        or digest(selected_units) != digest(plan["units"])
        or digest(selected_exemplars) != digest(plan["form_exemplars"])
        or digest(selected["observations"]) != digest(plan["experience"])
    ):
        raise ProductionError("Selected source content changed; plan again")


def _section_notes(plan, section_notes):
    """Validate operator revision notes against the planned sections."""
    sections = plan["route"]["sections"]
    if set(section_notes) - {s["id"] for s in sections}:
        raise ProductionError("section_notes contains unknown section IDs")
    return {
        sid: _str(note, f"section_notes.{sid}", 8000)
        for sid, note in section_notes.items()
    }


def _section_update(section, draft, findings, position, fmt):
    """The bounded preview a progress listener receives when a section settles."""
    assessment = fmt == "assessment"
    return {
        "stage": "production_section",
        "item": section["id"],
        "status": "completed",
        "section_update": {
            "id": section["id"],
            "title": "Practice question" if assessment else draft["title"],
            "position": position,
            "status": "review" if findings else "provisional",
            "body": draft.get("candidate_body" if assessment else "body", "")[:12000],
            "truncated": len(draft.get("candidate_body" if assessment else "body", ""))
            > 12000,
            "evidence": []
            if assessment
            else [
                {"unit_id": e["unit_id"], "quote": e["quote"][:1000]}
                for e in draft.get("evidence", [])[:8]
            ],
            "scope": "Section checks completed; the complete project may change this result.",
        },
    }


class _Written(NamedTuple):
    """Finished sections, their findings and the speech lane's report."""

    authored: list
    initial_findings: dict
    remaining: dict
    first_useful_ms: float | None
    speech_report: dict | None


def _section_pipeline(calls, context_index, speech, progress, started):
    """Write, review, repair and recheck every section in one shared pool.

    Each section is announced to the progress listener and handed to the
    speech lane as soon as its checks settle.
    """
    opts, tracker = calls.opts, calls.tracker
    first_useful_ms = None

    def section_available(section, draft, findings):
        nonlocal first_useful_ms
        if first_useful_ms is None:
            first_useful_ms = round((time.monotonic() - started) * 1000, 3)
        speech.submit(section, draft)
        if progress:
            progress(
                _section_update(
                    section,
                    draft,
                    findings,
                    context_index["positions"][section["id"]],
                    opts["format"],
                )
            )

    try:
        authored, initial_findings, remaining = section_pipeline(
            calls.plan["route"]["sections"],
            calls.write,
            calls.review,
            calls.repair,
            writers=opts["writer_workers"],
            reviewers=opts["review_workers"],
            workers=opts["workers"],
            write_many=lambda rows: calls.many("production_write", rows),
            review_many=lambda rows: calls.many("production_review", rows),
            batch_size=opts["sections_per_request"],
            on_section=section_available,
        )
    except Exception as exc:
        exc.metrics = tracker.metrics()
        speech.close()
        raise
    speech_report = speech.close()
    return _Written(
        authored, initial_findings, remaining, first_useful_ms, speech_report
    )


def _document_checks(workspace, provider, plan, authored, opts, tracker):
    """Model consistency checks across the finished sections."""
    from .verification import check_document_sections
    from .source_reading import envelope

    def consistency_call(stage, item, instruction, shape, data, checker):
        items = len(data["sections"])
        _require_workload(provider, stage, opts, items)
        return tracker.call(
            workspace,
            provider,
            stage,
            item,
            instruction,
            shape,
            data,
            lambda raw: validated(checker, raw),
            request_limit(opts),
            workload_items=items,
        )

    def consistency_fits(stage, instruction, shape, data):
        items = len(data["sections"])
        return _require_workload(provider, stage, opts, items).fits(
            envelope(stage, instruction, shape, data, workload_items=items)
        )

    return check_document_sections(
        plan,
        authored,
        consistency_call,
        consistency_fits,
        workers=min(opts["workers"], opts["review_workers"]),
        include_adjacency=True,
    )


def _assemble_receipt(
    plan, opts, provider, tracker, started, written, rendered, document_checks
):
    """The run receipt: rendered outputs, findings, status and run metrics."""
    authored = written.authored
    by_section_episode = {
        row["id"]: row["episode"]
        for row in plan["route"]["sections"]
        if row.get("episode") is not None
    }
    metrics = tracker.metrics()
    unresolved_reads = (plan.get("planning") or {}).get("unresolved_reads") or []
    metrics.update(
        {
            "wall_ms": round((time.monotonic() - started) * 1000, 3),
            "sections": len(authored),
            "first_useful_output_ms": written.first_useful_ms,
            "unresolved_reader_windows": len(unresolved_reads),
            "execution_capacity": {
                "engine_workers": opts["workers"],
                "sections_per_request": opts["sections_per_request"],
                "provider_concurrency": getattr(provider, "max_concurrency", None),
            },
            "initial_flagged_sections": len(written.initial_findings),
            "remaining_flagged_sections": len(written.remaining),
            "output_bytes": len(rendered["markdown"].encode("utf-8")),
            **(
                {"speech_prefetch": written.speech_report}
                if written.speech_report
                else {}
            ),
            "retrieval_targets": (
                len(plan["retrieval_targets"]["targets"])
                if plan.get("retrieval_targets")
                else 0
            ),
        }
    )
    return {
        "schema_version": "1.0",
        "revision": REVISION,
        "status": (
            "review"
            if written.remaining
            or unresolved_reads
            or (document_checks and document_checks["status"] == "review")
            or (plan.get("planning", {}).get("evidence_relations") or {}).get(
                "unresolved_groups", 0
            )
            else "ready"
        ),
        "unresolved_reads": unresolved_reads,
        "document_checks": document_checks,
        "quality": plan["quality"],
        "format": opts["format"],
        "title": rendered["route"]["title"],
        "markdown": rendered["markdown"],
        "candidate_markdown": (
            rendered["markdown"] if opts["format"] == "assessment" else None
        ),
        "examiner_markdown": rendered["examiner_markdown"],
        "sections": [
            {**row, "episode": by_section_episode[row["id"]]}
            if row["id"] in by_section_episode
            else row
            for row in authored
        ],
        "episodes": (
            episode_scripts(rendered["route"], authored)
            if opts["format"] == "podcast-script"
            else None
        ),
        "retrieval_targets": plan.get("retrieval_targets"),
        "retrieval_markdown": rendered["retrieval_markdown"],
        "initial_findings": written.initial_findings,
        "findings": written.remaining,
        "sources": plan["sources"],
        "plan_digest": plan["plan_digest"],
        "metrics": metrics,
        "scope": "Source-grounded model output and model review; no independent truth, mastery, audio, or delivery verification.",
    }


def _check_assessment(workspace, provider, plan, receipt, opts, progress, started):
    # Imported here because assessment_checks validates a production plan
    # against this module. Every assessment path (CLI, Python, local app)
    # crosses the same blind-solve/judge boundary before completion.
    from .assessment_checks import check_assessment

    try:
        checks = check_assessment(
            workspace,
            provider,
            plan,
            receipt,
            workers=min(opts["workers"], opts["review_workers"]),
            progress=progress,
        )
    except Exception as exc:
        receipt["status"] = "review"
        receipt["assessment_checks"] = {
            "status": "failed",
            "metrics": getattr(exc, "metrics", {}),
        }
        exc.partial_results = {
            **getattr(exc, "partial_results", {}),
            "production_receipt": receipt,
        }
        raise
    receipt["assessment_checks"] = checks
    if checks["status"] == "review":
        receipt["status"] = "review"
    receipt["metrics"]["assessment_check_wall_ms"] = checks["metrics"]["wall_ms"]
    receipt["metrics"]["wall_ms"] = round((time.monotonic() - started) * 1000, 3)


def _attach_coverage_and_geometry(receipt, plan, authored, provider, opts):
    """Plan coverage, calibration status and the run's schedule geometry."""
    from .verification import coverage_report

    receipt["coverage"] = coverage_report(plan, authored)
    from .calibration import quality_status

    receipt["quality_control"] = quality_status(
        provider,
        (
            "production_read",
            "production_route",
            "production_write",
            "production_review",
            "production_repair",
        ),
    )
    from .geometry import combine

    metrics = receipt["metrics"]
    receipt["geometry"] = combine(
        plan.get("geometry"),
        metrics["requests"],
        workers=opts["workers"],
        wall_ms=metrics["wall_ms"],
        source_bytes=_source_bytes(plan["units"]),
        timing=getattr(provider, "timing_label", "measured"),
    )


def run_production(
    workspace: Workspace,
    provider,
    plan: dict,
    options: dict | None = None,
    progress: Callable[[dict], None] | None = None,
    *,
    audio_provider=None,
    audio_output=None,
) -> dict:
    """Write sections in parallel, review them, repair only flagged sections once.

    With ``audio_provider`` and ``audio_output`` on a podcast script, each
    section is synthesized on a speech lane the moment it leaves review, so
    delivery assembles cached segments instead of starting speech after the
    last section finishes.
    """
    started = time.monotonic()
    opts, section_notes = _validate_run_request(workspace, provider, plan, options)
    tracker = _Tracker(progress, max_attempts=opts["max_attempts"])
    if opts["workflow"] == "sweep":
        if section_notes:
            raise ProductionError(
                "Card decks are written directly by readers and have no section "
                "writer to revise. Change the brief or the sources and plan again."
            )
        from .sweep import publish_sweep

        return publish_sweep(plan, opts, provider, started)
    section_notes = _section_notes(plan, section_notes)
    context_index, contexts = section_contexts(plan, provider, opts)
    calls = SectionCalls(
        workspace, provider, plan, opts, contexts, section_notes, tracker
    )
    speech = SpeechLane(workspace, audio_provider, audio_output, opts, progress)
    written = _section_pipeline(calls, context_index, speech, progress, started)
    rendered = render_outputs(plan, opts, written.authored)
    document_checks = (
        _document_checks(workspace, provider, plan, written.authored, opts, tracker)
        if opts["document_review"]
        else None
    )
    receipt = _assemble_receipt(
        plan, opts, provider, tracker, started, written, rendered, document_checks
    )
    if opts["format"] == "assessment":
        _check_assessment(workspace, provider, plan, receipt, opts, progress, started)
    _attach_coverage_and_geometry(receipt, plan, written.authored, provider, opts)
    return receipt


def build_production(
    workspace: Workspace,
    provider,
    brief: str | dict,
    source_ids: list[str],
    options: dict | None = None,
    progress: Callable[[dict], None] | None = None,
    *,
    audio_provider=None,
    audio_output=None,
) -> dict:
    """Convenience route for one goal-to-artifact build; returns plan and receipt."""
    started = time.monotonic()
    plan = plan_production(workspace, provider, brief, source_ids, options, progress)
    try:
        receipt = run_production(
            workspace,
            provider,
            plan,
            progress=progress,
            audio_provider=audio_provider,
            audio_output=audio_output,
        )
    except Exception as exc:
        exc.partial_results = {**getattr(exc, "partial_results", {}), "plan": plan}
        raise
    receipt["plan"] = plan
    receipt["metrics"]["end_to_end_wall_ms"] = round(
        (time.monotonic() - started) * 1000, 3
    )
    return receipt
