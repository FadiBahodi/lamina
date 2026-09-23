"""Source-grounded, task-shaped production with parallel local reading and writing.

Models choose the content and topology. This module owns source boundaries,
evidence identity, concurrency, cached jobs, and an inspectable receipt.
"""

from __future__ import annotations

import copy
import time
from .execution import section_pipeline
from typing import Callable

from .source_policy import normalize_production_inputs
from .store import Workspace, digest
from .retrieval_targets import render_retrieval_targets

from .production_contract import (
    REVISION,
    FORMATS,
    ProductionError,
    _BASE,
    _FORM,
    _SHAPES,
    _str,
    _options,
    _brief,
    _evidence,
    _read_check,
    _route_check,
    _authored_check,
    _review_check,
    validated,
    request_limit,
)


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


def _windows(units: list[dict], core_words: int, halo_units: int) -> list[dict]:
    groups, count = [], 0
    by_source, positions = {}, {}
    for unit in units:
        local = by_source.setdefault(unit["source_id"], [])
        positions[unit["id"]] = len(local)
        local.append(unit)
        # A byte ceiling also bounds dense text without whitespace. Whole
        # structured units stay intact; request preflight rejects oversized ones.
        size = max(1, len(unit["text"].split()), (len(unit["text"].encode()) + 5) // 6)
        if (
            not groups
            or groups[-1][-1]["source_id"] != unit["source_id"]
            or groups[-1][-1]["heading"] != unit["heading"]
            or count + size > core_words
        ):
            groups.append([])
            count = 0
        groups[-1].append(unit)
        count += size
    windows = []
    for core in groups:
        local = by_source[core[0]["source_id"]]
        a, b = positions[core[0]["id"]], positions[core[-1]["id"]]
        windows.append(
            {
                "id": "window_"
                + digest([core[0]["source_id"], [u["id"] for u in core]])[:12],
                "source_id": core[0]["source_id"],
                "core": core,
                "before": local[max(0, a - halo_units) : a],
                "after": local[b + 1 : b + 1 + halo_units],
            }
        )
    return windows


from .call_runtime import CallTracker as _Tracker


def _require_workload(provider, stage, options, items):
    """Require an explicit policy before combining independent work items."""
    from .source_reading import request_budget

    budget = request_budget(provider, stage, options)
    if (items is None or items > 1) and budget.workload is None:
        raise ProductionError(
            f"{stage} combines independent items and needs an explicit workload profile. "
            "Configure workload.max_items or workload.max_input_tokens for this stage; "
            "choose the limit from your task evaluation. Context capacity alone does "
            "not establish a suitable workload."
        )
    return budget


def _section_items(section):
    return len(section.get("unit_ids", section["idea_ids"]))


def _section_scope(section, data, units):
    """Unprofiled eligibility includes visible context, beyond owned work."""
    return max(
        _section_items(section),
        len(units)
        + len(data.get("form_exemplars", []))
        + len(data.get("experience", [])),
    )


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
        return digest({key: plan[key] for key in keys})
    except (KeyError, TypeError, ValueError) as exc:
        raise ProductionError("Invalid production plan structure") from exc


def _read_and_plan(
    workspace, provider, task, opts, selection, sources, units, form_exemplars, tracker
):
    from .source_reading import read_sources

    # Validate the downstream policy before paying to read a corpus.
    for stage in (
        "production_route",
        "production_write",
        "production_review",
        "production_repair",
    ):
        _require_workload(provider, stage, opts, None)

    legacy = (
        _windows(units, opts["core_words"], opts["halo_units"])
        if opts["core_words"] is not None
        else None
    )
    windows, ideas = read_sources(
        workspace, provider, task, opts, sources, units, tracker, legacy
    )
    if not ideas:
        raise ProductionError("Readers found no anchored ideas in selected sources")
    from .planning import plan_bounded, target_bounded, refine_sections
    from .source_reading import request_budget, envelope
    from .retrieval_targets import RetrievalTargetError
    from .production_contract import ProductionValidationError

    def invoke(stage, item, instruction, shape, data, checker):
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
        )

    def fits(stage, instruction, shape, data):
        items = len(data.get("cards", data.get("ideas", [])))
        return _require_workload(provider, stage, opts, items).fits(
            envelope(stage, instruction, shape, data, workload_items=items)
        )

    shared = {
        "format": opts["format"],
        "sources": sources,
        "form_exemplars": form_exemplars,
        "experience": selection["observations"],
    }
    retrieval_catalog, target_report = None, None
    workers = min(opts["workers"], opts["reader_workers"])
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
                "retrieval_targets": retrieval_catalog,
                "factual_source_ids": selection["factual_source_ids"],
                "form_exemplars": form_exemplars,
                "experience": selection["observations"],
            }
            fit_index = _context_index(fit_plan)
        context = _section_context(fit_plan, section, fit_index)
        return _section_capacity(fit_plan, section, provider, opts, context)["fits"]

    route, refinement = refine_sections(
        route,
        ideas,
        units,
        task,
        invoke,
        section_fits=section_fits,
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
        },
    )


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
    from .source_assignments import source_route
    from .source_reading import envelope, request_budget

    decision = {"requested": opts["workflow"], "basis": "caller"}
    if opts["workflow"] == "auto":
        direct_options = {**opts, "workflow": "direct"}
        direct_ideas, direct_route = source_route(task, units, direct_options)
        candidate = {
            "brief": task,
            "options": direct_options,
            "sources": sources,
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
        selected_workflow = (
            "direct"
            if not opts["retrieval_targets"] and capacity["fits"]
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

    tracker = _Tracker(progress, max_attempts=opts["max_attempts"])
    if opts["workflow"] in {"direct", "assigned"}:
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
        "retrieval_targets": retrieval_catalog,
        "route": route,
        "metrics": {
            **tracker.metrics(),
            "wall_ms": round((time.monotonic() - started) * 1000, 3),
            "selected_sources": len(sources),
            "factual_sources": len(selection["factual_source_ids"]),
            "form_exemplar_sources": len(selection["form_exemplar_ids"]),
            "selected_observations": len(selection["observations"]),
            "source_units": len(units),
            "reader_windows": len(windows),
            "workflow": opts["workflow"],
            "extracted_ideas": len(ideas) if opts["workflow"] == "planned" else 0,
            "source_references": len(ideas) if opts["workflow"] != "planned" else 0,
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
        },
    }
    result["plan_digest"] = _plan_identity(result)
    return result


def _context_index(plan):
    sections = plan["route"]["sections"]
    scoped, global_rows = {section["id"]: [] for section in sections}, []
    for row in plan["route"]["shared_context"]:
        if "section_ids" in row:
            for sid in row["section_ids"]:
                scoped[sid].append(row)
        else:
            global_rows.append(row)
    catalog = plan.get("retrieval_targets") or {"targets": [], "relations": []}
    relations = {row["id"]: [] for row in catalog["targets"]}
    for number, row in enumerate(catalog["relations"]):
        for key in ("from_target_id", "to_target_id"):
            relations[row[key]].append((number, row))
    structures = {}
    for unit in plan["units"]:
        if unit.get("structural_group"):
            structures.setdefault(
                (unit["source_id"], unit["structural_group"]), []
            ).append(unit["id"])
    return {
        "structures": structures,
        "ideas": {i["id"]: i for i in plan["ideas"]},
        "units": {u["id"]: u for u in plan["units"]},
        "sections": {s["id"]: s for s in sections},
        "positions": {s["id"]: n for n, s in enumerate(sections)},
        "targets": {row["id"]: row for row in catalog["targets"]},
        "relations": relations,
        "shared": scoped,
        "global_shared": global_rows,
        "sources": {row["id"]: row for row in plan["sources"]},
        "source_positions": {row["id"]: n for n, row in enumerate(plan["sources"])},
    }


def _section_context(
    plan: dict, section: dict, index=None
) -> tuple[dict, dict[str, dict]]:
    index = index or _context_index(plan)
    idea_map, units = index["ideas"], index["units"]
    chosen = [idea_map[i] for i in section["idea_ids"]]
    own_units = {uid: units[uid] for idea in chosen for uid in idea["unit_ids"]}
    route = plan["route"]
    retrieval_catalog = plan.get("retrieval_targets")
    target_by_id = index["targets"]
    assigned_targets = [target_by_id[tid] for tid in section.get("target_ids", [])]
    links = dict(
        pair
        for tid in section.get("target_ids", [])
        for pair in index["relations"][tid]
    )
    target_relations = [links[n] for n in sorted(links)]
    related_ids = {
        relation[key]
        for relation in target_relations
        for key in ("from_target_id", "to_target_id")
    } - set(section.get("target_ids", []))
    related_targets = [
        {key: target_by_id[tid][key] for key in ("id", "title", "prompt", "context")}
        for tid in sorted(related_ids)
    ]
    position = index["positions"].get(section["id"], 0)
    visible_sections = {section["id"], *section["context_section_ids"]}
    for n in (position - 1, position + 1):
        if 0 <= n < len(route["sections"]):
            visible_sections.add(route["sections"][n]["id"])
    route_outline = [
        {k: row[k] for k in ("id", "title", "purpose")}
        for row in (
            index["sections"][sid]
            for sid in sorted(visible_sections, key=index["positions"].get)
        )
    ]
    prior = [
        idea_map[i]
        for sid in section["context_section_ids"]
        for i in index["sections"][sid]["idea_ids"]
    ]
    prior_units = {
        uid: units[uid]
        for idea in prior
        for uid in idea["unit_ids"]
        if uid not in own_units
    }
    prior_units.update(
        {
            uid: units[uid]
            for uid in section.get("context_unit_ids", [])
            if uid not in own_units
        }
    )
    shared_context = index["global_shared"] + index["shared"][section["id"]]
    shared_units = {
        e["unit_id"]: units[e["unit_id"]]
        for row in shared_context
        for e in row["evidence"]
        if e["unit_id"] not in own_units and e["unit_id"] not in prior_units
    }
    # Parser-declared companions (e.g. slide text, table and notes) remain
    # context even when an idea cites only one component. Ownership is unchanged.
    structure_keys = list(
        dict.fromkeys(
            (unit["source_id"], unit["structural_group"])
            for group in (own_units, prior_units, shared_units)
            for unit in group.values()
            if unit.get("structural_group")
        )
    )
    source_structures = []
    for key in structure_keys:
        members = index["structures"][key]
        source_structures.append(
            {
                "unit_ids": members,
                "relationship": "components of the same source structure",
            }
        )
        for uid in members:
            if uid not in own_units and uid not in prior_units:
                shared_units[uid] = units[uid]
    data = {
        "source_structures": source_structures,
        "brief": plan["brief"],
        "format": plan["options"]["format"],
        "title": route["title"],
        "factual_sources": [
            index["sources"][sid]
            for sid in sorted(
                {
                    u["source_id"]
                    for group in (own_units, prior_units, shared_units)
                    for u in group.values()
                },
                key=index["source_positions"].get,
            )
        ],
        "section": section,
        "assigned_ideas": chosen,
        **(
            {
                "assigned_targets": assigned_targets,
                "target_relations": target_relations,
                "related_targets": related_targets,
            }
            if retrieval_catalog
            else {}
        ),
        "assigned_units": list(own_units.values()),
        "shared_route": route_outline,
        "shared_context": shared_context,
        "earlier_planned_ideas": prior,
        "earlier_evidence_units": list(prior_units.values()),
        "shared_evidence_units": list(shared_units.values()),
        "scope": "Earlier ideas are planned context with exact sources, not completed prose; this section owns only assigned ideas.",
    }
    if "unit_ids" in section:
        data.pop("assigned_ideas")
        data.pop("earlier_planned_ideas")
        data["form_exemplars"] = plan["form_exemplars"]
        data["experience"] = plan["experience"]
        data["scope"] = (
            "Write from assigned_units. Other units are context only. Account for each assigned unit as used or explicitly omitted."
        )
    return data, {**prior_units, **shared_units, **own_units}


def _markdown(route: dict, sections: list[dict], fmt: str) -> str:
    if fmt == "assessment":
        candidate = "\n\n".join(
            "## Question " + str(index) + "\n\n" + s["candidate_body"]
            for index, s in enumerate(sections, 1)
        )
        return "# Practice assessment\n\n" + candidate + "\n"
    title = "# " + route["title"]
    return (
        title
        + "\n\n"
        + "\n\n".join("## " + s["title"] + "\n\n" + s["body"] for s in sections)
        + "\n"
    )


def _write_request(plan, section, context=None, note=None):
    opts = plan["options"]
    data, units = context or _section_context(plan, section)
    if note:
        data = {**data, "operator_revision_note": note}
    shape = copy.deepcopy(_SHAPES["production_write"])
    if "unit_ids" in section:
        shape.pop("used_idea_ids")
        shape.update(
            title="document title",
            used_unit_ids=["assigned source unit id"],
            omitted_units=[
                {"unit_id": "unused assigned unit id", "reason": "why excluded"}
            ],
        )
    if plan.get("retrieval_targets"):
        shape["used_target_ids"] = ["assigned canonical target id"]
    if opts["format"] == "assessment":
        shape.pop("body")
        shape.update(candidate_body="Markdown str", marking_body="Markdown str")
    instruction = (
        "Write the finished section from its assigned sources or ideas. The outline contains this section, "
        "its neighbors and declared dependencies; other writers' future prose is unavailable. "
        + _FORM[opts["format"]]
        + " Follow the planned representation and requirements. Preserve qualifications and conflicting source "
        "claims. Return claims linking exact body spans to supporting original quotes; account for assigned "
        "material. Historical source claims remain historical; supplements cannot silently override authority. "
        + (
            "Preserve each assigned retrieval target's prompt and answer groups. Report used_target_ids exactly. "
            if plan.get("retrieval_targets")
            else ""
        )
    )
    return instruction, shape, data, units


_REVIEW_INSTRUCTION = (
    "Check the drafted section against its assignment and original source text. "
    "Compare the actual body with every assigned idea/source, including conditions, quantities, "
    "omissions and contradictions. used_idea_ids and claims are writer reports; inspect their "
    "meaning and support. Flag unsupported claims, missing assignment meaning, broken conditions, "
    "answer leakage and unanswerable prompts. Preserve candidate/marking boundaries. "
)


def _section_capacity(plan, section, provider, options, context=None):
    """Measure canonical writing and empty-draft review/repair envelopes.

    The eventual draft and findings are unknown. Their actual complete requests
    are checked at execution; the receipt retains any unperformed verification.
    A byte ceiling alone establishes no model context or output allowance.
    """
    from .context_binding import bind_context
    from .source_reading import envelope, request_budget

    instruction, shape, data, units = _write_request(plan, section, context)
    bound, _, _ = bind_context(data, units)
    items = _section_items(section)
    requests = {
        "production_write": envelope(
            "production_write", instruction, shape, bound, workload_items=items
        ),
        "production_review": envelope(
            "production_review",
            _REVIEW_INSTRUCTION + _FORM[options["format"]],
            _SHAPES["production_review"],
            {**bound, "draft": {}},
            workload_items=items,
        ),
        "production_repair": envelope(
            "production_repair",
            "Repair this section's concrete findings. Preserve supported work and update claim links. "
            + _FORM[options["format"]],
            shape,
            {
                **bound,
                "draft": {},
                "findings": [],
                "scope": "Repair only this section's concrete findings; preserve supported work.",
            },
            workload_items=items,
        ),
    }
    checks = {}
    for stage, request in requests.items():
        budget = _require_workload(
            provider, stage, options, _section_scope(section, data, units)
        )
        measured = budget.measure(request)
        checks[stage] = {**measured.__dict__, "fits": budget.accepts(measured)}
    return {
        "fits": all(row["fits"] for row in checks.values()),
        "stages": checks,
        "scope": "Full writing request and review/repair source context; future draft and findings checked when available.",
    }


def run_production(
    workspace: Workspace,
    provider,
    plan: dict,
    options: dict | None = None,
    progress: Callable[[dict], None] | None = None,
) -> dict:
    """Write sections in parallel, review them, repair only flagged sections once."""
    started = time.monotonic()
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
        for key in ("workflow", "assignments", "retrieval_targets")
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
    tracker = _Tracker(progress, max_attempts=opts["max_attempts"])
    sections = plan["route"]["sections"]
    if set(section_notes) - {s["id"] for s in sections}:
        raise ProductionError("section_notes contains unknown section IDs")
    section_notes = {
        sid: _str(note, f"section_notes.{sid}", 8000)
        for sid, note in section_notes.items()
    }
    context_index = _context_index(plan)
    contexts = {s["id"]: _section_context(plan, s, context_index) for s in sections}
    for section in sections:
        data, units = contexts[section["id"]]
        for stage in ("production_write", "production_review", "production_repair"):
            _require_workload(
                provider, stage, opts, _section_scope(section, data, units)
            )

    def section_call(stage, section, instruction, shape, data, units, checker):
        from .context_binding import bind_context, restore_references

        bound, bound_units, reverse = bind_context(data, units)
        result = tracker.call(
            workspace,
            provider,
            stage,
            section["id"],
            instruction,
            shape,
            bound,
            lambda raw: checker(raw, bound["section"], bound_units),
            request_limit(opts),
            workload_items=_section_items(section),
        )
        return restore_references(result, reverse)

    def write(section):
        instruction, shape, data, units = _write_request(
            plan, section, contexts[section["id"]], section_notes.get(section["id"])
        )
        return section_call(
            "production_write",
            section,
            instruction,
            shape,
            data,
            units,
            lambda raw, sec, local: validated(
                _authored_check, raw, sec, local, opts["format"]
            ),
        )

    def review(pair):
        section, draft = pair
        context, units = contexts[section["id"]]
        data = {**context, "draft": draft}
        from .context_budget import ContextBudgetError

        try:
            return section_call(
                "production_review",
                section,
                _REVIEW_INSTRUCTION + _FORM[opts["format"]],
                _SHAPES["production_review"],
                data,
                units,
                lambda raw, sec, local: validated(_review_check, raw, local),
            )
        except ProductionError as exc:
            if not isinstance(exc.__cause__, ContextBudgetError):
                raise
            return {
                "findings": [
                    {
                        "issue": "Review was not performed: " + str(exc),
                        "repair_instruction": "Use a reviewer with sufficient capacity or revise the section boundaries.",
                        "evidence": [],
                        "verification_unperformed": True,
                    }
                ]
            }

    def repair(pair):
        section, draft, findings = pair
        if any(row.get("verification_unperformed") for row in findings):
            return draft
        context, units = contexts[section["id"]]
        data = {
            **context,
            "draft": draft,
            "findings": findings,
            "scope": "Repair only this section's concrete findings; preserve supported work.",
        }
        if section["id"] in section_notes:
            data["operator_revision_note"] = section_notes[section["id"]]
        shape = copy.deepcopy(_SHAPES["production_repair"])
        if "unit_ids" in section:
            shape.pop("used_idea_ids")
            shape.update(
                {
                    "title": "document title",
                    "used_unit_ids": ["assigned source unit id"],
                    "omitted_units": [
                        {"unit_id": "unused assigned unit id", "reason": "why excluded"}
                    ],
                }
            )
        if plan.get("retrieval_targets"):
            shape["used_target_ids"] = ["assigned canonical target id"]
        if opts["format"] == "assessment":
            shape.pop("body")
            shape.update(
                {"candidate_body": "Markdown str", "marking_body": "Markdown str"}
            )
        return section_call(
            "production_repair",
            section,
            "Repair this section's concrete findings. Preserve supported work and update claim links. "
            + _FORM[opts["format"]],
            shape,
            data,
            units,
            lambda raw, sec, local: validated(
                _authored_check, raw, sec, local, opts["format"]
            ),
        )

    try:
        authored, initial_findings, remaining = section_pipeline(
            sections,
            write,
            review,
            repair,
            writers=opts["writer_workers"],
            reviewers=opts["review_workers"],
            workers=opts["workers"],
        )
    except Exception as exc:
        exc.metrics = tracker.metrics()
        raise

    output_route = plan["route"]
    if opts["workflow"] == "direct" and opts["format"] != "assessment":
        output_route = {
            **output_route,
            "title": authored[0].get("document_title", output_route["title"]),
        }
        markdown = "# " + output_route["title"] + "\n\n" + authored[0]["body"] + "\n"
    else:
        markdown = _markdown(output_route, authored, opts["format"])
    retrieval_markdown = None
    if plan.get("retrieval_targets"):
        selected_ids = {
            tid
            for section in plan["route"]["sections"]
            for tid in section["target_ids"]
        }
        selected_catalog = {
            "targets": [
                target
                for target in plan["retrieval_targets"]["targets"]
                if target["id"] in selected_ids
            ],
            "relations": [
                link
                for link in plan["retrieval_targets"]["relations"]
                if link["from_target_id"] in selected_ids
                and link["to_target_id"] in selected_ids
            ],
        }
        if selected_catalog["targets"]:
            retrieval_markdown = render_retrieval_targets(selected_catalog)
    examiner_markdown = None
    if opts["format"] == "assessment":
        examiner_markdown = (
            "# "
            + plan["route"]["title"]
            + " — Answer and marking guide\n\n"
            + "\n\n".join(
                "## " + s["title"] + "\n\n" + s["marking_body"] for s in authored
            )
            + "\n"
        )
        if retrieval_markdown:
            examiner_markdown += "\n" + retrieval_markdown
    elif retrieval_markdown:
        markdown += "\n" + retrieval_markdown
    document_checks = None
    if opts["document_review"]:
        from .verification import check_document_sections
        from .source_reading import request_budget, envelope

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

        document_checks = check_document_sections(
            plan,
            authored,
            consistency_call,
            consistency_fits,
            workers=min(opts["workers"], opts["review_workers"]),
            include_adjacency=True,
        )
    metrics = tracker.metrics()
    metrics.update(
        {
            "wall_ms": round((time.monotonic() - started) * 1000, 3),
            "sections": len(authored),
            "initial_flagged_sections": len(initial_findings),
            "remaining_flagged_sections": len(remaining),
            "output_bytes": len(markdown.encode("utf-8")),
            "retrieval_targets": (
                len(plan["retrieval_targets"]["targets"])
                if plan.get("retrieval_targets")
                else 0
            ),
        }
    )
    receipt = {
        "schema_version": "1.0",
        "revision": REVISION,
        "status": (
            "review"
            if remaining or (document_checks and document_checks["status"] == "review")
            else "ready"
        ),
        "document_checks": document_checks,
        "quality": plan["quality"],
        "format": opts["format"],
        "title": output_route["title"],
        "markdown": markdown,
        "candidate_markdown": markdown if opts["format"] == "assessment" else None,
        "examiner_markdown": examiner_markdown,
        "sections": authored,
        "retrieval_targets": plan.get("retrieval_targets"),
        "retrieval_markdown": retrieval_markdown,
        "initial_findings": initial_findings,
        "findings": remaining,
        "sources": plan["sources"],
        "plan_digest": plan["plan_digest"],
        "metrics": metrics,
        "scope": "Source-grounded model output and model review; no independent truth, mastery, audio, or delivery verification.",
    }
    if opts["format"] == "assessment":
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
    from .verification import coverage_report

    receipt["coverage"] = coverage_report(plan, authored)
    return receipt


def build_production(
    workspace: Workspace,
    provider,
    brief: str | dict,
    source_ids: list[str],
    options: dict | None = None,
    progress: Callable[[dict], None] | None = None,
) -> dict:
    """Convenience route for one goal-to-artifact build; returns plan and receipt."""
    started = time.monotonic()
    plan = plan_production(workspace, provider, brief, source_ids, options, progress)
    try:
        receipt = run_production(workspace, provider, plan, progress=progress)
    except Exception as exc:
        exc.partial_results = {**getattr(exc, "partial_results", {}), "plan": plan}
        raise
    receipt["plan"] = plan
    receipt["metrics"]["end_to_end_wall_ms"] = round(
        (time.monotonic() - started) * 1000, 3
    )
    return receipt
