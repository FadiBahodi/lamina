"""What each section's writer, reviewer and repairer may see.

A section owns its assigned ideas, or its assigned source units on the direct
and assigned routes. Its request also carries the neighbouring outline, the
planned ideas of declared earlier sections, shared cross-section statements,
exact supporting evidence and parser-declared source structures. This module
assembles those requests and measures them against the configured workload and
request capacity. It makes no model calls.
"""

from __future__ import annotations

import copy

from .production_contract import ProductionError, _FORM, _SHAPES


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


def _target_context(section, index):
    """Assigned retrieval targets, their relations and the related targets' prompts."""
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
    return {
        "assigned_targets": assigned_targets,
        "target_relations": target_relations,
        "related_targets": related_targets,
    }


def _visible_outline(section, index, route):
    """This section, its declared dependencies and its immediate neighbours, in route order."""
    position = index["positions"].get(section["id"], 0)
    visible_sections = {section["id"], *section["context_section_ids"]}
    for n in (position - 1, position + 1):
        if 0 <= n < len(route["sections"]):
            visible_sections.add(route["sections"][n]["id"])
    return [
        {k: row[k] for k in ("id", "title", "purpose")}
        for row in (
            index["sections"][sid]
            for sid in sorted(visible_sections, key=index["positions"].get)
        )
    ]


def _section_context(
    plan: dict, section: dict, index=None
) -> tuple[dict, dict[str, dict]]:
    index = index or _context_index(plan)
    idea_map, units = index["ideas"], index["units"]
    chosen = [idea_map[i] for i in section["idea_ids"]]
    own_units = {uid: units[uid] for idea in chosen for uid in idea["unit_ids"]}
    route = plan["route"]
    retrieval_catalog = plan.get("retrieval_targets")
    targets = _target_context(section, index)
    route_outline = _visible_outline(section, index, route)
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
    evidence_relations = list(
        {
            row["id"]: row
            for idea in chosen + prior
            for row in idea.get("evidence_relations", [])
        }.values()
    )
    for row in evidence_relations:
        for evidence in row["evidence"]:
            uid = evidence["unit_id"]
            if uid not in own_units and uid not in prior_units:
                shared_units[uid] = units[uid]
    # Ownership prevents duplicate extraction; it must not limit the evidence
    # needed to interpret an owned claim. Include exact visible support in the
    # semantic request (and therefore its cache key), including prior ideas.
    for idea in chosen + prior:
        for evidence in idea["evidence"]:
            uid = evidence["unit_id"]
            if uid not in own_units and uid not in prior_units:
                shared_units[uid] = units[uid]
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
        **(targets if retrieval_catalog else {}),
        "assigned_units": list(own_units.values()),
        "shared_route": route_outline,
        "shared_context": shared_context,
        "evidence_relations": evidence_relations,
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


def section_contexts(plan, provider, options):
    """Every section's visible context, with its workload checked before any call."""
    sections = plan["route"]["sections"]
    index = _context_index(plan)
    contexts = {s["id"]: _section_context(plan, s, index) for s in sections}
    for section in sections:
        data, units = contexts[section["id"]]
        for stage in ("production_write", "production_review", "production_repair"):
            _require_workload(
                provider, stage, options, _section_scope(section, data, units)
            )
    return index, contexts


def _authored_shape(stage, plan, section, fmt):
    """Writing and repair return the same contract, shaped by ownership and format."""
    shape = copy.deepcopy(_SHAPES[stage])
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
    if fmt == "assessment":
        shape.pop("body_marked")
        shape.update(
            candidate_body_marked="Markdown str with source markers; markers are removed before candidate export",
            marking_body_marked="Markdown str with source markers; markers are removed before examiner export",
        )
    return shape


def _write_request(plan, section, context=None, note=None):
    opts = plan["options"]
    data, units = context or _section_context(plan, section)
    if note:
        data = {**data, "operator_revision_note": note}
    shape = _authored_shape("production_write", plan, section, opts["format"])
    instruction = (
        "Write the finished section from its assigned sources or ideas. The outline contains this section, "
        "its neighbors and declared dependencies; other writers' future prose is unavailable. "
        + _FORM[opts["format"]]
        + (
            " This section belongs to episode "
            f"{section.get('episode', 1)} and should take about {section['target_words']} spoken words; "
            "write for the ear, with a clear opening and a landing, and no headings inside the body. "
            if opts["format"] == "podcast-script" and section.get("target_words")
            else ""
        )
        + " Follow the planned representation and requirements. Preserve qualifications and conflicting source "
        "claims. Source passages are prefixed with compact span aliases such as [s3]. Add [s3] or a same-unit "
        "range such as [s3-s5] immediately after each source-supported statement. "
        "Use only s-number source aliases inside markers. Put idea IDs only in used_idea_ids, never in citations. "
        "Escape literal bracket text that resembles a source marker with a Markdown backslash. "
        "Return body_marked (or both "
        "candidate_body_marked and marking_body_marked for an assessment); Lamina removes markers and derives "
        "claim links and exact quotations. Account for assigned "
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
    'Return {"findings": []} when there is no material defect. Each finding must identify '
    "a specific change needed; keep approval statements and style preferences out of findings. "
)

_REPAIR_INSTRUCTION = (
    "Repair this section's concrete findings. Preserve supported work and update inline source markers. "
)

_REPAIR_SCOPE = "Repair only this section's concrete findings; preserve supported work."


def _review_text_context(bound, bound_units):
    """Show reviewers the exact text their quote contract validates.

    Writers and repairers need inline span aliases for marker output. Reviewers
    still return legacy exact quotations, so exposing alias-injected text asks
    them to copy a string that the validator will reject. Unit IDs remain local
    and canonical; only the source-text presentation differs by stage.
    """
    for key in ("assigned_units", "earlier_evidence_units", "shared_evidence_units"):
        for row in bound.get(key, []):
            unit = bound_units[row["id"]]
            row["text"] = unit["text"]
            row.pop("addressed_text", None)
    return bound


def _section_capacity(plan, section, provider, options, context=None):
    """Measure canonical writing and empty-draft review/repair envelopes.

    The eventual draft and findings are unknown. Their actual complete requests
    are checked at execution; the receipt retains any unperformed verification.
    A byte ceiling alone establishes no model context or output allowance.
    """
    from .context_binding import bind_context
    from .source_reading import envelope

    instruction, shape, data, units = _write_request(plan, section, context)
    bound, bound_units, _ = bind_context(data, units)
    review_bound = _review_text_context(copy.deepcopy(bound), bound_units)
    items = _section_items(section)
    requests = {
        "production_write": envelope(
            "production_write", instruction, shape, bound, workload_items=items
        ),
        "production_review": envelope(
            "production_review",
            _REVIEW_INSTRUCTION + _FORM[options["format"]],
            _SHAPES["production_review"],
            {**review_bound, "draft": {}},
            workload_items=items,
        ),
        "production_repair": envelope(
            "production_repair",
            _REPAIR_INSTRUCTION + _FORM[options["format"]],
            shape,
            {
                **bound,
                "draft": {},
                "findings": [],
                "scope": _REPAIR_SCOPE,
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
