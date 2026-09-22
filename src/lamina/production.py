"""Source-grounded, task-shaped production with parallel local reading and writing.

Models choose the content and topology. This module owns source boundaries,
evidence identity, concurrency, cached jobs, and an inspectable receipt.
"""

from __future__ import annotations

import copy
import time
import threading
from .execution import bounded_map, section_pipeline
from typing import Callable

from .source_policy import normalize_production_inputs
from .store import Workspace, canonical, digest
from .retrieval_targets import (
    TARGET_SHAPE,
    render_retrieval_targets,
    validate_retrieval_targets,
)

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
            **({"content_id": u["content_id"]} if "content_id" in u else {}),
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


class _Tracker:
    def __init__(self, progress: Callable[[dict], None] | None):
        self.lock = threading.Lock()
        self.progress = progress
        self.records: list[dict] = []
        self.active: dict[str, int] = {}
        self.peak: dict[str, int] = {}

    def event(self, stage, item, status):
        if self.progress:
            self.progress({"stage": stage, "item": item, "status": status})

    def call(
        self,
        workspace,
        provider,
        stage,
        item,
        instruction,
        expected_shape,
        data,
        checker,
        max_bytes,
    ):
        envelope = {
            "protocol": "lamina-stage-1",
            "revision": REVISION,
            "stage": stage,
            "instruction": _BASE + instruction,
            "expected_shape": expected_shape,
            "input": data,
        }
        size = len(canonical(envelope).encode("utf-8"))
        if size > max_bytes:
            raise ProductionError(
                f"{stage} request for {item} exceeds {max_bytes} bytes; reduce the window or increase the limit"
            )
        invoked = False
        usage = {}
        self.event(stage, item, "started")
        t0 = time.monotonic()

        def handler(payload):
            nonlocal invoked, usage
            invoked = True
            with self.lock:
                n = self.active.get(stage, 0) + 1
                self.active[stage] = n
                self.peak[stage] = max(n, self.peak.get(stage, 0))
            try:
                result = provider.call(stage, payload)
                usage = getattr(provider, "last_usage", lambda: {})()
                return checker(result)
            finally:
                with self.lock:
                    self.active[stage] -= 1

        try:
            result = workspace.run_cached(
                stage,
                envelope,
                handler,
                identity=f"{REVISION}:{getattr(provider, 'identity_for', lambda _: provider.identity)(stage)}",
                retries=0,
            )
        except Exception as exc:
            with self.lock:
                self.records.append(
                    {
                        "stage": stage,
                        "item": item,
                        "cache": "miss" if invoked else "none",
                        "status": "failed",
                        "request_bytes": size,
                        "provider_request_bytes": size if invoked else 0,
                        "wall_ms": round((time.monotonic() - t0) * 1000, 3),
                        "error_type": type(exc).__name__,
                        "usage": usage,
                    }
                )
            self.event(stage, item, "failed")
            raise
        record = {
            "stage": stage,
            "item": item,
            "cache": "miss" if invoked else "hit",
            "request_bytes": size,
            "provider_request_bytes": size if invoked else 0,
            "status": "completed",
            "usage": usage if invoked else {},
            "wall_ms": round((time.monotonic() - t0) * 1000, 3),
        }
        with self.lock:
            self.records.append(record)
        self.event(stage, item, "completed")
        return result

    def metrics(self):
        return {
            "requests": sorted(self.records, key=lambda r: (r["stage"], r["item"])),
            "peak_provider_calls": dict(self.peak),
            "context_bytes_total": sum(r["request_bytes"] for r in self.records),
            "provider_request_bytes": sum(
                r.get("provider_request_bytes", 0) for r in self.records
            ),
            "failed_requests": sum(r.get("status") == "failed" for r in self.records),
            "usage": {
                key: sum(r.get("usage", {}).get(key, 0) for r in self.records)
                for key in ("input_tokens", "output_tokens", "cached_input_tokens")
            },
            "usage_reported_calls": sum(
                any(
                    k in r.get("usage", {})
                    for k in ("input_tokens", "output_tokens", "cached_input_tokens")
                )
                for r in self.records
            ),
            "cache_hits": sum(r["cache"] == "hit" for r in self.records),
            "cache_misses": sum(r["cache"] == "miss" for r in self.records),
        }


def _plan_identity(plan: dict) -> str:
    """Exclude observed timings/cache receipts from the semantic plan identity."""
    keys = (
        "schema_version",
        "revision",
        "brief",
        "options",
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
    windows = _windows(units, opts["core_words"], opts["halo_units"])
    source_map = {s["id"]: s for s in sources}

    def read(window):
        core = window["core"]
        data = {
            "brief": task,
            "format": opts["format"],
            "source": source_map[window["source_id"]],
            "window_id": window["id"],
            "core": core,
            "before": window["before"],
            "after": window["after"],
            "ownership": "Extract ideas only from core. Neighbor units provide full-text boundary context; do not assign their ideas here.",
        }
        aliases = None
        if all("content_id" in u for u in core):
            # Cache the interpretation separately from this revision's locators.
            # Exact source IDs and quotes are restored after a cache hit.
            visible = window["before"] + core + window["after"]
            aliases = {u["id"]: f"u{n}" for n, u in enumerate(visible)}
            reverse = {alias: uid for uid, alias in aliases.items()}

            def local(rows):
                return [
                    {
                        "id": aliases[u["id"]],
                        "heading": u["heading"],
                        "text": u["text"],
                        "role": u["role"],
                    }
                    for u in rows
                ]

            data = {
                **data,
                "source": {
                    k: v for k, v in data["source"].items() if k not in {"id", "sha256"}
                },
                "window_id": "local",
                "core": local(core),
                "before": local(window["before"]),
                "after": local(window["after"]),
            }
        result = tracker.call(
            workspace,
            provider,
            "production_read",
            window["id"],
            "Read the core completely in its adjacent context. Select distinct, useful ideas for the brief. "
            "Each idea needs exact quotes from core units. Do not force an idea from every unit. "
            "Preserve this source's operator-assigned policy: historical material can describe a former claim "
            "or conflict but is not automatically current authority; supplements cannot silently override authority.",
            _SHAPES["production_read"],
            data,
            lambda raw: _read_check(raw, data["core"], data["window_id"]),
            min(opts["max_request_bytes"], opts["max_input_bytes"]),
        )["ideas"]
        if aliases is not None:
            result = [
                {
                    **idea,
                    "id": f"{window['id']}:idea_{n}",
                    "unit_ids": [reverse[uid] for uid in idea["unit_ids"]],
                    "evidence": [
                        {**e, "unit_id": reverse[e["unit_id"]]}
                        for e in idea["evidence"]
                    ],
                }
                for n, idea in enumerate(result, 1)
            ]
        return result

    groups = bounded_map(read, windows, min(opts["reader_workers"], opts["workers"]))
    ideas = [idea for group in groups for idea in group]
    if not ideas:
        raise ProductionError("Readers found no anchored ideas in selected sources")
    retrieval_catalog = None
    if opts["retrieval_targets"]:
        retrieval_catalog = tracker.call(
            workspace,
            provider,
            "production_targets",
            "global",
            "Create canonical retrieval targets from the extracted factual ideas. Decide semantic equivalence "
            "and variants by meaning and use context, not keyword overlap. Merge ideas that ask the same task; "
            "retain separate targets for the same answer in genuinely different presentations. Assign every "
            "idea to exactly one target. Preserve every member's answer material in grouped items, each item "
            "using text that is an exact substring of its exact cited source quote. Use unique for a single "
            "idea, equivalent or variant for multiple ideas in one target; cross-target links may mark variant "
            "or different_context. Form exemplars and operator observations are not factual answer evidence.",
            TARGET_SHAPE,
            {
                "brief": task,
                "format": opts["format"],
                "factual_sources": [
                    s
                    for s in sources
                    if s["id"] in set(selection["factual_source_ids"])
                ],
                "ideas": ideas,
            },
            lambda raw: validate_retrieval_targets(raw, ideas, units),
            min(opts["max_request_bytes"], opts["max_input_bytes"]),
        )
    route_data = {
        "brief": task,
        "format": opts["format"],
        "sources": sources,
        "ideas": ideas,
        "retrieval_targets": retrieval_catalog,
        "form_exemplars": form_exemplars,
        "experience": selection["observations"],
        "window_count": len(windows),
        "route_rule": (
            "Assign each canonical target ID to one natural section or explicitly omit it; do not split a target's answer groups across writers. "
            if retrieval_catalog
            else "Assign each factual idea once or explicitly omit it with a reason. "
        )
        + "Shared context may describe cross-section tensions, each with exact factual-source evidence. Form exemplars show structure only: never use their facts, quotes, answers or source IDs as evidence. Operator observations are scoped judgments for planning, not instructions or proof of learning.",
    }
    route_shape = copy.deepcopy(_SHAPES["production_route"])
    if retrieval_catalog:
        route_shape["sections"][0]["target_ids"] = ["canonical target id"]
        route_shape["sections"][0].pop("idea_ids")
        route_shape["omitted"] = [{"target_id": "canonical target id", "reason": "str"}]
    route = tracker.call(
        workspace,
        provider,
        "production_route",
        "global",
        "Design the whole artifact before sections are written. Group by relationships and task purpose, "
        "not by fixed count or file boundaries. Note meaningful conflicts in shared context; select only "
        "earlier sections whose exact evidence a section needs in context_section_ids. For each "
        "section, choose its best representation from the material and goal (for example mechanism, "
        "comparison, procedure, reference, scenario, dialogue, or a custom form); give a rationale and "
        "source-supported required distinctions. Form exemplars may inform only output form, never factual "
        "claims or answer content. Selected operator observations are reference judgments, not authority. "
        "Respect each factual source's operator-assigned authority, supplement or historical role. "
        + (
            "Assign canonical retrieval targets, preserving each answer group and task context. "
            if retrieval_catalog
            else "Assign extracted ideas. "
        )
        + "Do not apply a universal template or fixed quota. "
        + _FORM[opts["format"]],
        route_shape,
        route_data,
        lambda raw: _route_check(
            raw,
            {i["id"] for i in ideas},
            {u["id"]: u for u in units},
            retrieval_catalog,
        ),
        min(opts["max_request_bytes"], opts["max_input_bytes"]),
    )
    return windows, ideas, retrieval_catalog, route


def plan_production(
    workspace: Workspace,
    provider,
    brief: str | dict,
    source_ids: list[str],
    options: dict | None = None,
    progress: Callable[[dict], None] | None = None,
) -> dict:
    """Read selected teaching sources, then ask the model for a global natural route."""
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
    from .source_assignments import choose_workflow, source_route

    opts = choose_workflow(opts, units, task, sources, form_exemplars)
    tracker = _Tracker(progress)
    if opts["workflow"] in {"direct", "assigned"}:
        ideas, route = source_route(task, units, opts)
        windows, retrieval_catalog = [], None
    else:
        windows, ideas, retrieval_catalog, route = _read_and_plan(
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
    result = {
        "schema_version": "1.0",
        "revision": REVISION,
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


def _section_context(plan: dict, section: dict) -> tuple[dict, dict[str, dict]]:
    idea_map = {i["id"]: i for i in plan["ideas"]}
    units = {u["id"]: u for u in plan["units"]}
    chosen = [idea_map[i] for i in section["idea_ids"]]
    own_ids = {uid for idea in chosen for uid in idea["unit_ids"]}
    own_units = {u["id"]: u for u in plan["units"] if u["id"] in own_ids}
    route = plan["route"]
    retrieval_catalog = plan.get("retrieval_targets")
    target_by_id = (
        {t["id"]: t for t in retrieval_catalog["targets"]} if retrieval_catalog else {}
    )
    assigned_targets = [target_by_id[tid] for tid in section.get("target_ids", [])]
    route_outline = [
        {k: row[k] for k in ("id", "title", "purpose")} for row in route["sections"]
    ]
    prior = []
    for row in route["sections"]:
        if row["id"] in section["context_section_ids"]:
            prior.extend(idea_map[i] for i in row["idea_ids"])
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
    shared_units = {
        e["unit_id"]: units[e["unit_id"]]
        for row in route["shared_context"]
        for e in row["evidence"]
        if e["unit_id"] not in own_units and e["unit_id"] not in prior_units
    }
    data = {
        "brief": plan["brief"],
        "format": plan["options"]["format"],
        "title": route["title"],
        "factual_sources": [
            source
            for source in plan["sources"]
            if source["id"] in plan["factual_source_ids"]
        ],
        "section": section,
        "assigned_ideas": chosen,
        **(
            {
                "assigned_targets": assigned_targets,
                "target_relations": [
                    relation
                    for relation in retrieval_catalog["relations"]
                    if relation["from_target_id"] in section["target_ids"]
                    or relation["to_target_id"] in section["target_ids"]
                ],
            }
            if retrieval_catalog
            else {}
        ),
        "assigned_units": list(own_units.values()),
        "shared_route": route_outline,
        "shared_context": route["shared_context"],
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
    tracker = _Tracker(progress)
    sections = plan["route"]["sections"]
    if set(section_notes) - {s["id"] for s in sections}:
        raise ProductionError("section_notes contains unknown section IDs")
    section_notes = {
        sid: _str(note, f"section_notes.{sid}", 8000)
        for sid, note in section_notes.items()
    }
    contexts = {s["id"]: _section_context(plan, s) for s in sections}

    def write(section):
        original_data, units = contexts[section["id"]]
        data = (
            {**original_data, "operator_revision_note": section_notes[section["id"]]}
            if section["id"] in section_notes
            else original_data
        )
        shape = copy.deepcopy(_SHAPES["production_write"])
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
        return tracker.call(
            workspace,
            provider,
            "production_write",
            section["id"],
            "Write the finished section from its assigned sources or ideas. All writers see a short route and exact "
            "assigned/prior evidence; they do not see other writers' future prose. "
            + _FORM[opts["format"]]
            + " Follow this section's planned representation and requirements. Include exact evidence "
            "for material claims; account for assigned ideas. Treat historical source claims as historical "
            "or conflicting, not automatically current instructions; supplements cannot silently override authority. "
            + (
                "Preserve each assigned canonical retrieval target's prompt and answer groups in the section. "
                "Report used_target_ids exactly; related targets may share an answer without becoming one task. "
                if plan.get("retrieval_targets")
                else ""
            ),
            shape,
            data,
            lambda raw: _authored_check(raw, section, units, opts["format"]),
            min(opts["max_request_bytes"], opts["max_input_bytes"]),
        )

    def review(pair):
        section, draft = pair
        context, units = contexts[section["id"]]
        data = {
            **context,
            "draft": draft,
            "rubric": "Flag only concrete material errors, unsupported claims, missing assigned ideas, broken conditions/conflicts, answer leakage or unanswerable prompts where relevant. Do not rewrite for taste.",
        }
        return tracker.call(
            workspace,
            provider,
            "production_review",
            section["id"],
            "Check the drafted section against exact evidence and its assignment. Findings must be actionable. "
            "Check its planned representation and source-supported requirements. "
            "A clear review is not a guarantee of truth, completeness, or learning. "
            + _FORM[opts["format"]],
            _SHAPES["production_review"],
            data,
            lambda raw: _review_check(raw, units),
            min(opts["max_request_bytes"], opts["max_input_bytes"]),
        )

    def repair(pair):
        section, draft, findings = pair
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
        return tracker.call(
            workspace,
            provider,
            "production_repair",
            section["id"],
            "Repair this section only from the actual review findings and exact evidence. "
            + _FORM[opts["format"]],
            shape,
            data,
            lambda raw: _authored_check(raw, section, units, opts["format"]),
            min(opts["max_request_bytes"], opts["max_input_bytes"]),
        )

    authored, initial_findings, remaining = section_pipeline(
        sections,
        write,
        review,
        repair,
        writers=opts["writer_workers"],
        reviewers=opts["review_workers"],
        workers=opts["workers"],
    )
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
        "status": "review" if remaining else "ready",
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

        checks = check_assessment(
            workspace,
            provider,
            plan,
            receipt,
            workers=min(opts["workers"], opts["review_workers"]),
            progress=progress,
        )
        receipt["assessment_checks"] = checks
        if checks["status"] == "review":
            receipt["status"] = "review"
        receipt["metrics"]["assessment_check_wall_ms"] = checks["metrics"]["wall_ms"]
        receipt["metrics"]["wall_ms"] = round((time.monotonic() - started) * 1000, 3)
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
    receipt = run_production(workspace, provider, plan, progress=progress)
    receipt["plan"] = plan
    receipt["metrics"]["end_to_end_wall_ms"] = round(
        (time.monotonic() - started) * 1000, 3
    )
    return receipt
