"""Read the selected sources and plan the sections a production will write.

Planning chooses a route (direct, assigned, planned or sweep), reads sources
when the route needs ideas, plans and refines sections within the declared
writing capacity, and returns a plan whose digest covers every semantic input.
``run_production`` refuses a plan whose digest or source content changed.
"""

from __future__ import annotations

import time
from typing import Callable

from .call_runtime import CallTracker as _Tracker
from .production_contract import (
    REVISION,
    ProductionError,
    _brief,
    _options,
    request_limit,
    validated,
)
from .section_context import (
    _context_index,
    _require_workload,
    _section_capacity,
    _section_context,
)
from .source_policy import normalize_production_inputs
from .store import Workspace, digest


def _sources(
    workspace: Workspace, source_ids: list[str]
) -> tuple[list[dict], list[dict]]:
    if (
        not isinstance(source_ids, list)
        or not source_ids
        or len(source_ids) > 2048
        or any(not isinstance(x, str) for x in source_ids)
    ):
        raise ProductionError(
            "source_ids must be a nonempty list of at most 2048 source IDs"
        )
    if len(set(source_ids)) != len(source_ids):
        raise ProductionError("source_ids must be unique")
    by_id = {s["id"]: s for s in workspace.sources()}
    for sid in source_ids:
        if sid not in by_id or by_id[sid].get("role") != "teaching":
            raise ProductionError(
                f"Source {sid} is missing or is not a teaching source"
            )
    sources = [
        {k: by_id[sid][k] for k in ("id", "title", "filename", "sha256", "role")}
        for sid in source_ids
    ]
    selected = set(source_ids)
    source_order = {sid: index for index, sid in enumerate(source_ids)}
    units = [
        {
            **{
                k: u[k]
                for k in (
                    "content_id",
                    "heading_path",
                    "section_id",
                    "kind",
                    "structural_group",
                    "page",
                    "slide",
                    "section_index",
                    "shape",
                    "reference_context",
                )
                if k in u
            },
            **{
                k: u[k]
                for k in (
                    "id",
                    "source_id",
                    "heading",
                    "text",
                    "locator",
                    "ordinal",
                    "role",
                )
            },
        }
        for u in workspace.units("teaching", source_ids)
        if u["source_id"] in selected
    ]
    units.sort(key=lambda u: (source_order[u["source_id"]], u["ordinal"]))
    if not units or any(
        sid not in {u["source_id"] for u in units} for sid in source_ids
    ):
        raise ProductionError(
            "Every selected source must contain readable teaching units"
        )
    return sources, units


def _form_exemplar_context(
    sources: list[dict],
    units: list[dict],
    exemplar_ids: list[str],
    *,
    max_chars: int = 24000,
    max_units: int = 32,
) -> list[dict]:
    """Bound form-only excerpts while preserving their original source identity."""
    by_id = {source["id"]: source for source in sources}
    remaining_chars = max_chars
    remaining_units = max_units
    result = []
    for sid in exemplar_ids:
        remaining_chars = max_chars // max(1, len(exemplar_ids))
        remaining_units = max(1, max_units // max(1, len(exemplar_ids)))
        chosen = []
        all_source_units = [unit for unit in units if unit["source_id"] == sid]
        for unit in all_source_units:
            if remaining_units <= 0 or remaining_chars <= 0:
                break
            text = unit["text"][:remaining_chars]
            chosen.append(
                {
                    "id": unit["id"],
                    "heading": unit["heading"],
                    "locator": unit["locator"],
                    "text": text,
                    "truncated": len(text) < len(unit["text"]),
                }
            )
            remaining_chars -= len(text)
            remaining_units -= 1
        result.append(
            {
                "source": by_id[sid],
                "units": chosen,
                "truncated": len(chosen) < len(all_source_units)
                or any(row["truncated"] for row in chosen),
            }
        )
    return result


def _plan_identity(plan: dict) -> str:
    """Exclude observed timings/cache receipts from the semantic plan identity."""
    keys = (
        "schema_version",
        "revision",
        "brief",
        "options",
        "quality",
        "provider_identity",
        "sources",
        "factual_source_ids",
        "form_exemplar_ids",
        "form_exemplars",
        "experience",
        "units",
        "windows",
        "ideas",
        "retrieval_targets",
        "route",
    )
    try:
        return digest(
            {**{key: plan[key] for key in keys}, "duplicates": plan.get("duplicates")}
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ProductionError("Invalid production plan structure") from exc


def _source_bytes(units) -> int:
    return sum(len((unit.get("text") or "").encode("utf-8")) for unit in units)


def _planning_calls(workspace, provider, opts, tracker):
    """The grouping, target and refinement stages' call and capacity check."""
    from .source_reading import envelope
    from .retrieval_targets import RetrievalTargetError
    from .production_contract import ProductionValidationError

    def invoke(stage, item, instruction, shape, data, checker, after=()):
        items = len(data.get("cards", data.get("ideas", [])))
        _require_workload(provider, stage, opts, items)

        def check(raw):
            try:
                return validated(checker, raw)
            except RetrievalTargetError as exc:
                raise ProductionValidationError(str(exc)) from exc

        return tracker.call(
            workspace,
            provider,
            stage,
            item,
            instruction,
            shape,
            data,
            check,
            request_limit(opts),
            workload_items=items,
            after=after,
        )

    def fits(stage, instruction, shape, data):
        items = len(data.get("cards", data.get("ideas", [])))
        return _require_workload(provider, stage, opts, items).fits(
            envelope(stage, instruction, shape, data, workload_items=items)
        )

    return invoke, fits


def _section_fit_check(
    provider, task, opts, selection, sources, units, ideas, form_exemplars, catalog
):
    """Whether a proposed section's complete write/review/repair requests fit.

    Refinement asks once per section of each candidate route; the context
    index is rebuilt only when the route object changes.
    """
    fit_route, fit_plan, fit_index = None, None, None

    def section_fits(section, current_route):
        nonlocal fit_route, fit_plan, fit_index
        if fit_route is not current_route:
            fit_route = current_route
            fit_plan = {
                "brief": task,
                "options": opts,
                "sources": sources,
                "units": units,
                "ideas": ideas,
                "route": current_route,
                "retrieval_targets": catalog,
                "factual_source_ids": selection["factual_source_ids"],
                "form_exemplars": form_exemplars,
                "experience": selection["observations"],
            }
            fit_index = _context_index(fit_plan)
        context = _section_context(fit_plan, section, fit_index)
        return _section_capacity(fit_plan, section, provider, opts, context)["fits"]

    return section_fits


def _with_evidence_relations(ideas, relations):
    by_idea = {idea["id"]: [] for idea in ideas}
    for relation in relations:
        if relation["kind"] != "unrelated":
            for iid in relation["member_idea_ids"]:
                by_idea[iid].append(relation)
    return [{**idea, "evidence_relations": by_idea[idea["id"]]} for idea in ideas]


def _read_and_plan(
    workspace, provider, task, opts, selection, sources, units, form_exemplars, tracker
):
    from .source_reading import read_sources

    # Validate the downstream policy before paying to read a corpus.
    if opts["compare_relations"]:
        _require_workload(provider, "production_compare", opts, None)
    for stage in (
        "production_route",
        "production_write",
        "production_review",
        "production_repair",
    ):
        _require_workload(provider, stage, opts, None)

    from .planning import plan_bounded, plan_streaming, target_bounded, refine_sections
    from .production_contract import podcast_plan

    invoke, fits = _planning_calls(workspace, provider, opts, tracker)
    shared = {
        "format": opts["format"],
        "sources": sources,
        "form_exemplars": form_exemplars,
        "experience": selection["observations"],
        **({"podcast": podcast_plan(opts)} if podcast_plan(opts) else {}),
    }
    workers = min(opts["workers"], opts["reader_workers"])
    relation_report = None
    retrieval_catalog, target_report = None, None
    if opts["compare_relations"] or opts["retrieval_targets"]:
        # Comparison and retrieval targets need every idea before planning.
        windows, ideas, unresolved_reads = read_sources(
            workspace, provider, task, opts, sources, units, tracker
        )
        if not ideas:
            raise ProductionError("Readers found no anchored ideas in selected sources")
        if opts["compare_relations"]:
            from .evidence_relations import compare_relations

            relations, relation_report = compare_relations(
                workspace, provider, ideas, units, task, opts, tracker
            )
            ideas = _with_evidence_relations(ideas, relations)
        if opts["retrieval_targets"]:
            retrieval_catalog, target_report = target_bounded(
                ideas,
                units,
                task,
                invoke,
                max_bytes=request_limit(opts),
                shared=shared,
                workers=workers,
                fits=fits,
            )
        route, planning_report = plan_bounded(
            ideas,
            units,
            task,
            invoke,
            max_bytes=request_limit(opts),
            shared=shared,
            workers=workers,
            fits=fits,
            catalog=retrieval_catalog,
        )
    else:
        # The default planned route: grouping starts as reads complete.
        def read(on_batch):
            return read_sources(
                workspace, provider, task, opts, sources, units, tracker, on_batch=on_batch
            )

        windows, ideas, unresolved_reads, route, planning_report = plan_streaming(
            read,
            units,
            task,
            invoke,
            max_bytes=request_limit(opts),
            shared=shared,
            workers=workers,
            fits=fits,
        )

    route, refinement = refine_sections(
        route,
        ideas,
        units,
        task,
        invoke,
        section_fits=_section_fit_check(
            provider,
            task,
            opts,
            selection,
            sources,
            units,
            ideas,
            form_exemplars,
            retrieval_catalog,
        ),
        max_bytes=request_limit(opts),
        shared=shared,
        workers=workers,
        fits=fits,
        catalog=retrieval_catalog,
    )
    return (
        windows,
        ideas,
        retrieval_catalog,
        route,
        {
            "routing": planning_report,
            "targets": target_report,
            "writing_capacity": refinement,
            "evidence_relations": relation_report,
            # Windows that stayed unresolved under reading_failures="continue".
            # Their source units were considered but produced no ideas; the
            # receipt stays in review until they are read or explicitly waived.
            "unresolved_reads": unresolved_reads,
        },
    )


def _choose_workflow(provider, task, opts, options, selection, units, form_exemplars):
    """Resolve ``workflow="auto"`` and record why the route was chosen."""
    from .source_assignments import source_route

    decision = {"requested": opts["workflow"], "basis": "caller"}
    if opts["workflow"] == "sweep":
        decision = {
            "requested": options.get("workflow", "auto") if options else "auto",
            "selected": "sweep",
            "basis": "cards format reads straight to cards",
        }
    if opts["workflow"] == "auto":
        direct_options = {**opts, "workflow": "direct"}
        direct_ideas, direct_route = source_route(task, units, direct_options)
        candidate = {
            "brief": task,
            "options": direct_options,
            "sources": selection["sources"],
            "units": units,
            "ideas": direct_ideas,
            "route": direct_route,
            "retrieval_targets": None,
            "factual_source_ids": selection["factual_source_ids"],
            "form_exemplars": form_exemplars,
            "experience": selection["observations"],
        }
        capacity = _section_capacity(
            candidate, direct_route["sections"][0], provider, opts
        )
        multi_episode = (
            opts["format"] == "podcast-script"
            and opts["episodes"] != "auto"
            and opts["episodes"] > 1
        )
        selected_workflow = (
            "direct"
            if not opts["retrieval_targets"]
            and not opts["compare_relations"]
            and not multi_episode
            and capacity["fits"]
            else "planned"
        )
        opts = {**opts, "workflow": selected_workflow}
        decision = {
            "requested": "auto",
            "selected": selected_workflow,
            "basis": "declared workload limits and complete request capacity",
            "capacity": capacity,
            "retrieval_targets_require_planning": opts["retrieval_targets"],
        }
    return opts, decision


def _plan_route(
    workspace, provider, task, opts, selection, units, form_exemplars, tracker
):
    """Return ``(windows, ideas, duplicates, retrieval_catalog, route, planning_report)``."""
    sources = selection["sources"]
    duplicates = None
    if opts["workflow"] == "sweep":
        from .sweep import plan_sweep

        try:
            swept = plan_sweep(
                workspace, provider, task, opts, selection, sources, units, tracker
            )
        except Exception as exc:
            exc.metrics = tracker.metrics()
            raise
        windows, ideas, route = swept["windows"], swept["ideas"], swept["route"]
        duplicates, retrieval_catalog = swept["duplicates"], None
        planning_report = swept["planning"]
    elif opts["workflow"] in {"direct", "assigned"}:
        from .source_assignments import source_route

        ideas, route = source_route(task, units, opts)
        windows, retrieval_catalog, planning_report = (
            [],
            None,
            {"routing": {"mode": "supplied"}},
        )
    else:
        try:
            windows, ideas, retrieval_catalog, route, planning_report = _read_and_plan(
                workspace,
                provider,
                task,
                opts,
                selection,
                sources,
                units,
                form_exemplars,
                tracker,
            )
        except Exception as exc:
            exc.metrics = tracker.metrics()
            raise
    return windows, ideas, duplicates, retrieval_catalog, route, planning_report


def _plan_metrics(plan, tracker, started):
    """Counts for the plan receipt, read back from the plan it describes."""
    opts, route = plan["options"], plan["route"]
    retrieval_catalog = plan["retrieval_targets"]
    return {
        **tracker.metrics(),
        "wall_ms": round((time.monotonic() - started) * 1000, 3),
        "selected_sources": len(plan["sources"]),
        "factual_sources": len(plan["factual_source_ids"]),
        "form_exemplar_sources": len(plan["form_exemplar_ids"]),
        "selected_observations": len(plan["experience"]),
        "source_units": len(plan["units"]),
        "reader_windows": len(plan["windows"]),
        "unresolved_reader_windows": len(
            plan["planning"].get("unresolved_reads") or []
        ),
        "workflow": opts["workflow"],
        "extracted_ideas": (
            len(plan["ideas"]) if opts["workflow"] in {"planned", "sweep"} else 0
        ),
        "source_references": (
            len(plan["ideas"]) if opts["workflow"] not in {"planned", "sweep"} else 0
        ),
        "suppressed_duplicates": len(plan["duplicates"] or {}),
        "assigned_ideas": sum(len(s["idea_ids"]) for s in route["sections"]),
        "omitted_ideas": (
            sum(
                len(
                    next(
                        t
                        for t in retrieval_catalog["targets"]
                        if t["id"] == row["target_id"]
                    )["member_idea_ids"]
                )
                for row in route["omitted"]
            )
            if retrieval_catalog
            else len(route["omitted"])
        ),
        "retrieval_target_count": (
            len(retrieval_catalog["targets"]) if retrieval_catalog else 0
        ),
    }


def plan_production(
    workspace: Workspace,
    provider,
    brief: str | dict,
    source_ids: list[str],
    options: dict | None = None,
    progress: Callable[[dict], None] | None = None,
) -> dict:
    """Read selected sources and plan within the configured model capacities."""
    started = time.monotonic()
    try:
        selection = normalize_production_inputs(workspace, source_ids, options)
    except ValueError as exc:
        raise ProductionError(str(exc)) from exc
    opts, task = _options(selection["options"]), _brief(brief)
    sources = selection["sources"]
    _, all_units = _sources(workspace, source_ids)
    factual_ids = set(selection["factual_source_ids"])
    units = [unit for unit in all_units if unit["source_id"] in factual_ids]
    form_exemplars = _form_exemplar_context(
        sources, all_units, selection["form_exemplar_ids"]
    )
    opts, decision = _choose_workflow(
        provider, task, opts, options, selection, units, form_exemplars
    )
    tracker = _Tracker(progress, max_attempts=opts["max_attempts"])
    windows, ideas, duplicates, retrieval_catalog, route, planning_report = (
        _plan_route(
            workspace, provider, task, opts, selection, units, form_exemplars, tracker
        )
    )
    result = {
        "schema_version": "1.0",
        "revision": REVISION,
        "workflow_decision": decision,
        "quality": {
            "semantic_recall": "unmeasured",
            "reading": opts["reading"],
            "reusable_extraction": (
                "explicit opt-in; recall unmeasured"
                if opts["reading"] == "reusable"
                else "disabled"
            ),
            "scope": "Workload limits bound requests. Valid references and assignment accounting do not prove factual completeness.",
        },
        "planning": planning_report,
        "brief": task,
        "options": opts,
        "provider_identity": provider.identity,
        "sources": sources,
        "factual_source_ids": selection["factual_source_ids"],
        "form_exemplar_ids": selection["form_exemplar_ids"],
        "form_exemplars": form_exemplars,
        "experience": selection["observations"],
        "units": units,
        "windows": windows,
        "ideas": ideas,
        "duplicates": duplicates,
        "retrieval_targets": retrieval_catalog,
        "route": route,
    }
    result["metrics"] = _plan_metrics(result, tracker, started)
    result["plan_digest"] = _plan_identity(result)
    from .geometry import analyse

    result["geometry"] = analyse(
        result["metrics"]["requests"],
        workers=opts["workers"],
        wall_ms=result["metrics"]["wall_ms"],
        source_bytes=_source_bytes(units),
        timing=getattr(provider, "timing_label", "measured"),
    )
    return result
