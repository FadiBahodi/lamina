"""Budgeted planning with exact ownership and recoverable source evidence.

Transport batches have no editorial meaning. When a collection needs a summary
hierarchy, a second pass assigns every original card against the resulting
outline. The hierarchy suggests a structure; it never silently owns the source.
"""

from __future__ import annotations

import copy
from collections import Counter, defaultdict, deque
from typing import Callable

from .execution import bounded_map
from .production_contract import (
    REVISION,
    ProductionError,
    _BASE,
    _FORM,
    _SHAPES,
    _route_check,
    _str,
)
from .retrieval_targets import TARGET_REVISION, TARGET_SHAPE, validate_retrieval_targets
from .store import canonical, digest

Invoke = Callable[[str, str, str, dict, dict, Callable], dict]

GROUP_SHAPE = {
    "groups": [
        {
            "id": "local group id",
            "title": "str",
            "explanation": "relationships, conditions, exceptions and disagreements",
            "member_ids": ["input card id"],
        }
    ]
}
ASSIGN_SHAPE = {
    "assignments": [
        {"section_id": "outline section id", "idea_ids": ["input card id"]}
    ],
    "omitted": [
        {
            "idea_id": "input card id",
            "reason": "explicit editorial reason or missing outline distinction",
        }
    ],
    "shared_context": [
        {
            "statement": "cross-section relationship",
            "section_ids": ["affected outline section id"],
            "evidence_refs": [{"idea_id": "input card id", "evidence_index": 0}],
        }
    ],
}
GROUP_INSTRUCTION = (
    "Group the supplied cards by relationships relevant to the brief, across source boundaries. "
    "These are provisional navigation groups, not assertions of equivalence or final source ownership. "
    "Assign every supplied card ID exactly once. Keep conflicting values, conditions, exceptions, "
    "presentation differences and uncertainty explicit in each group's explanation. Do not infer "
    "agreement from similar titles. Choose natural groups; do not impose a group count. "
    "The next level needs descriptions of the relationships, not a repeat of member IDs or literal quotes."
)
ROUTE_INSTRUCTION = (
    "Design the artifact's sections from the brief and supplied cards. Group across files by meaning. "
    "Assign each supplied card ID once or explicitly omit it with a reason. Preserve conditions, "
    "exceptions, uncertainty, and disagreements. Choose the representation that serves each section. "
    "Request earlier source context only where needed; candidate_context_ids are earlier candidate "
    "prompts needed to answer an assessment, never examiner material. For shared context, cite "
    "evidence_refs using an original idea_id and its evidence_index; the engine restores exact quotes. "
    "Give each shared relationship explicit section_ids naming the affected sections. "
    "For summary cards, original evidence references are unavailable: leave shared_context empty; "
    "the later assignment pass receives original cards and supplies anchored relationships. "
    "Source authority, supplemental material, historical material and form exemplars have distinct roles. "
    "A form exemplar cannot support factual claims. Selected observations are reference judgments."
)
ASSIGN_INSTRUCTION = (
    "Assign every original card to exactly one section of the supplied outline, or explicitly omit "
    "it with a reason. Reconsider its COMPLETE explanation and qualifications, independently of "
    "any provisional grouping. Related cards from different sources may belong together; contradictory "
    "cards must retain their disagreement. Any section may own a card. If the outline lacks an essential "
    "distinction, report an omission explaining that defect rather than conceal it. Add anchored shared "
    "context for cross-section relationships, with section_ids naming affected outline sections. "
    "Evidence references name a supplied idea_id and index. "
    "No ID may occur twice, including between assignments and omissions."
)
TARGET_INSTRUCTION = (
    "Create canonical retrieval targets from factual ideas. Decide equivalence and variants by task "
    "meaning and use context. Keep genuinely different presentations separate. Assign every idea "
    "exactly once. Preserve each member's answer material as exact substrings of cited source quotes. "
    "Each answer item names its supported member ideas and their own exact evidence."
)
TARGET_MERGE_INSTRUCTION = (
    "Each input card is an existing retrieval target with its full prompt, context and answer items. "
    "Make each section one canonical retrieval target. Merge only equivalent tasks or compatible variants "
    "in the same use context. Different contexts remain separate even when the answer overlaps. "
    "Do not omit any input target. Use the section title for the canonical title, purpose for its complete "
    "self-contained retrieval prompt, and representation.rationale for its use context. Set "
    "representation.kind to unique, equivalent, or variant. Existing different_context relations "
    "are constraints: their endpoints must remain separate. All original answer items are retained "
    "mechanically, so no answer may be discarded to make a merge easier."
)


def request_size(stage, instruction, shape, data):
    """Measure the actual production envelope, including fixed prompt overhead."""
    return len(
        canonical(
            {
                "protocol": "lamina-stage-1",
                "revision": REVISION,
                "stage": stage,
                "instruction": _BASE + instruction,
                "expected_shape": shape,
                "input": data,
            }
        ).encode("utf-8")
    )


def compact_cards(ideas, units):
    """Remove duplicate quote text; preserve full explanations and evidence handles."""
    source_by_unit = {unit["id"]: unit.get("source_id", "") for unit in units}
    return [
        {
            "id": idea["id"],
            "title": idea["title"],
            "explanation": idea.get("explanation", ""),
            "source_ids": list(
                dict.fromkeys(
                    source_by_unit.get(uid, "") for uid in idea.get("unit_ids", [])
                )
            ),
            "evidence_refs": [
                {
                    "idea_id": idea["id"],
                    "evidence_index": n,
                    "unit_id": citation["unit_id"],
                }
                for n, citation in enumerate(idea.get("evidence", []))
            ],
        }
        for idea in ideas
    ]


def _interleave(cards):
    """Mix source queues without assigning semantic ownership to a file."""
    queues = defaultdict(deque)
    for card in cards:
        sources = card.get("source_ids", [])
        queues[tuple(sources)].append(card)
    result = []
    active = deque(queues.values())
    while active:
        queue = active.popleft()
        result.append(queue.popleft())
        if queue:
            active.append(queue)
    return result


def _ownership(expected, owned, label):
    counts = Counter(owned)
    missing = sorted(expected - counts.keys())
    foreign = sorted(counts.keys() - expected)
    duplicate = sorted(key for key, count in counts.items() if count > 1)
    if missing or foreign or duplicate:
        raise ProductionError(
            f"{label} ownership invalid; missing={missing}; duplicate={duplicate}; foreign={foreign}"
        )


def _group_check(raw, cards):
    if (
        not isinstance(raw, dict)
        or not isinstance(raw.get("groups"), list)
        or not raw["groups"]
    ):
        raise ProductionError("grouping must return a nonempty groups list")
    expected = {card["id"] for card in cards}
    groups, ids, owned = [], set(), []
    for row in raw["groups"]:
        if not isinstance(row, dict):
            raise ProductionError("each provisional group must be an object")
        gid = _str(row.get("id"), "group.id", 100)
        members = row.get("member_ids")
        if (
            gid in ids
            or not isinstance(members, list)
            or not members
            or any(not isinstance(x, str) for x in members)
        ):
            raise ProductionError("group IDs must be unique with nonempty member_ids")
        ids.add(gid)
        owned.extend(members)
        groups.append(
            {
                "id": gid,
                "title": _str(row.get("title"), "group.title", 300),
                "explanation": _str(row.get("explanation"), "group.explanation", 5000),
                "member_ids": members,
            }
        )
    _ownership(expected, owned, "group")
    return {"groups": groups}


def _restore_shared(raw, ideas):
    """Resolve explicit handles; model-written quote text cannot replace the source."""
    result = copy.deepcopy(raw)
    idea_map = {idea["id"]: idea for idea in ideas}
    checked = []
    for row in result.get("shared_context", []):
        if not isinstance(row, dict):
            raise ProductionError("shared_context must contain objects")
        refs = row.get("evidence_refs")
        if not isinstance(refs, list) or not refs:
            raise ProductionError(
                "shared_context needs evidence_refs naming supplied ideas"
            )
        evidence, seen = [], set()
        for ref in refs:
            if not isinstance(ref, dict):
                raise ProductionError("evidence_ref needs idea_id and evidence_index")
            iid, index = ref.get("idea_id"), ref.get("evidence_index")
            if (
                not isinstance(iid, str)
                or iid not in idea_map
                or type(index) is not int
                or not 0 <= index < len(idea_map[iid].get("evidence", []))
            ):
                raise ProductionError(f"unknown evidence reference: {ref}")
            citation = idea_map[iid]["evidence"][index]
            key = (citation["unit_id"], citation["quote"])
            if key not in seen:
                seen.add(key)
                evidence.append(copy.deepcopy(citation))
        checked.append(
            {
                "statement": row.get("statement"),
                "evidence": evidence,
                **(
                    {"section_ids": copy.deepcopy(row["section_ids"])}
                    if "section_ids" in row
                    else {}
                ),
            }
        )
    result["shared_context"] = checked
    return result


def _route_shape():
    shape = copy.deepcopy(_SHAPES["production_route"])
    shape["shared_context"] = copy.deepcopy(ASSIGN_SHAPE["shared_context"])
    return shape


class _Budget:
    def __init__(self, invoke, max_bytes, fits):
        self.invoke, self.max_bytes, self.fits = invoke, max_bytes, fits
        self.records = []

    def allows(self, stage, instruction, shape, data):
        return request_size(stage, instruction, shape, data) <= self.max_bytes and (
            self.fits is None or self.fits(stage, instruction, shape, data)
        )

    def call(self, stage, item, instruction, shape, data, checker):
        if not self.allows(stage, instruction, shape, data):
            raise ProductionError(
                f"{stage} {item} cannot fit the declared model/request budget; no content was truncated"
            )
        self.records.append(
            {
                "stage": stage,
                "item": item,
                "request_bytes": request_size(stage, instruction, shape, data),
            }
        )
        return self.invoke(stage, item, instruction, shape, data, checker)

    def pack(self, cards, stage, instruction, shape, data_for):
        # Exponential search bounds each candidate by nearby fitting work. Starting
        # every binary search at all remaining cards would serialize O(N²) content.
        batches, start = [], 0
        while start < len(cards):
            if not self.allows(
                stage, instruction, shape, data_for(cards[start : start + 1])
            ):
                raise ProductionError(
                    f"{stage}: indivisible card {cards[start]['id']} or shared context exceeds the declared budget"
                )
            remaining = len(cards) - start
            lo, hi = 1, min(2, remaining)
            while hi < remaining and self.allows(
                stage, instruction, shape, data_for(cards[start : start + hi])
            ):
                lo, hi = hi, min(hi * 2, remaining)
            while lo < hi:
                middle = (lo + hi + 1) // 2
                if self.allows(
                    stage, instruction, shape, data_for(cards[start : start + middle])
                ):
                    lo = middle
                else:
                    hi = middle - 1
            batches.append(cards[start : start + lo])
            start += lo
        return batches


def _shared_for_cards(shared, cards):
    sources = {sid for card in cards for sid in card.get("source_ids", [])}
    context = dict(shared)
    for key in ("sources", "factual_sources"):
        if isinstance(context.get(key), list):
            context[key] = [
                source for source in context[key] if source.get("id") in sources
            ]
    return context


def _route_data(shared, brief, cards):
    return {**_shared_for_cards(shared, cards), "brief": brief, "ideas": cards}


def _outline(cards, shared, brief, budget, workers, instruction, report):
    """Return a model-chosen outline, with a complete tree retained in the report."""
    current = cards
    level = 0
    shape = _route_shape()
    route_data = lambda rows: _route_data(shared, brief, rows)
    while not budget.allows(
        "production_route", instruction, shape, route_data(current)
    ):
        data_for = lambda rows: {
            **_shared_for_cards(shared, rows),
            "brief": brief,
            "purpose": instruction,
            "cards": rows,
        }
        batches = budget.pack(
            _interleave(current),
            "production_group",
            GROUP_INSTRUCTION,
            GROUP_SHAPE,
            data_for,
        )

        def group(job):
            index, batch = job
            return budget.call(
                "production_group",
                f"level_{level}_batch_{index}",
                GROUP_INSTRUCTION,
                GROUP_SHAPE,
                data_for(batch),
                lambda raw: _group_check(raw, batch),
            )

        grouped = bounded_map(group, list(enumerate(batches)), workers)
        next_cards = []
        current_by_id = {card["id"]: card for card in current}
        for batch_index, result in enumerate(grouped):
            for row in result["groups"]:
                gid = "group_" + digest([level, batch_index, row["member_ids"]])[:20]
                report["groups"].append({**row, "id": gid, "level": level})
                next_cards.append(
                    {
                        "id": gid,
                        "title": row["title"],
                        "explanation": row["explanation"],
                        "evidence_refs": [],
                        "source_ids": list(
                            dict.fromkeys(
                                sid
                                for cid in row["member_ids"]
                                for sid in current_by_id[cid].get("source_ids", [])
                            )
                        ),
                    }
                )
        if len(canonical(next_cards).encode()) >= len(canonical(current).encode()):
            raise ProductionError(
                "The grouping descriptions did not reduce the planning input. Increase the declared "
                "model budget or supply a narrower task/explicit assignments; no source was dropped."
            )
        current = next_cards
        level += 1
    report["hierarchy_levels"] = level
    expected = {card["id"] for card in current}

    def check(raw):
        restored = _restore_shared(raw, [])
        _diagnose_route(restored, expected)
        return _route_check(restored, expected, {})

    return budget.call(
        "production_route", "outline", instruction, shape, route_data(current), check
    )


def _diagnose_route(raw, expected):
    if not isinstance(raw, dict):
        raise ProductionError("route must be an object")
    if not isinstance(raw.get("sections"), list) or not isinstance(
        raw.get("omitted", []), list
    ):
        raise ProductionError("route requires sections and omitted lists")
    owned = []
    for row in raw.get("sections", []):
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("idea_ids"), list)
            or any(not isinstance(x, str) for x in row["idea_ids"])
        ):
            raise ProductionError("route sections require idea_ids lists")
        owned.extend(row["idea_ids"])
    for row in raw.get("omitted", []):
        if not isinstance(row, dict) or not isinstance(row.get("idea_id"), str):
            raise ProductionError("route omissions require idea_id")
        owned.append(row["idea_id"])
    _ownership(expected, owned, "route")


def _assign_check(raw, cards, sections, original):
    if (
        not isinstance(raw, dict)
        or not isinstance(raw.get("assignments"), list)
        or not isinstance(raw.get("omitted", []), list)
    ):
        raise ProductionError("assignment needs assignments and omitted lists")
    owned, assigned = [], []
    section_ids = {section["id"] for section in sections}
    for row in raw["assignments"]:
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("section_id"), str)
            or row["section_id"] not in section_ids
        ):
            raise ProductionError("assignment names an unknown outline section")
        ids = row.get("idea_ids")
        if not isinstance(ids, list) or any(not isinstance(i, str) for i in ids):
            raise ProductionError("assignment idea_ids must be a list of IDs")
        owned.extend(ids)
        assigned.append({"section_id": row["section_id"], "idea_ids": ids})
    omitted = []
    for row in raw.get("omitted", []):
        if not isinstance(row, dict) or not isinstance(row.get("idea_id"), str):
            raise ProductionError("each omission must name an idea_id")
        owned.append(row["idea_id"])
        omitted.append(
            {
                "idea_id": row["idea_id"],
                "reason": _str(row.get("reason"), "omission.reason", 2000),
            }
        )
    _ownership({card["id"] for card in cards}, owned, "assignment")
    allowed = {card["id"] for card in cards}
    restored = _restore_shared(
        raw, [idea for idea in original if idea["id"] in allowed]
    )
    for relationship in restored["shared_context"]:
        if "section_ids" in relationship:
            scope = relationship["section_ids"]
            if (
                not isinstance(scope, list)
                or not scope
                or any(not isinstance(sid, str) for sid in scope)
                or len(scope) != len(set(scope))
                or set(scope) - section_ids
            ):
                raise ProductionError(
                    "shared_context.section_ids must name unique affected outline sections"
                )
    return {
        "assignments": assigned,
        "omitted": omitted,
        "shared_context": restored["shared_context"],
    }


def plan_bounded(
    ideas,
    units,
    brief,
    invoke: Invoke,
    *,
    max_bytes,
    shared=None,
    workers=8,
    fits=None,
    catalog=None,
    instruction=None,
    allow_omissions=True,
    route_validator=None,
):
    """Plan bounded requests; return ``(validated_route, planning_report)``.

    ``fits(stage, instruction, shape, data)`` may enforce a model token budget in
    addition to the byte limit. ``invoke`` owns retries/cache/metrics. This module
    raises precise validation errors and adds no hidden retry policy.
    """
    shared = dict(shared or {})
    fmt = shared.get("format", "document")
    instruction = (instruction or ROUTE_INSTRUCTION) + " " + _FORM[fmt]
    if not ideas:
        raise ProductionError("planning requires ideas")
    idea_map = {idea["id"]: idea for idea in ideas}
    if len(idea_map) != len(ideas):
        raise ProductionError("planning input idea IDs must be unique")
    # A retrieval target is indivisible at the writer-assignment boundary.
    objects = ideas
    if catalog:
        objects = [
            {
                "id": target["id"],
                "title": target["title"],
                "explanation": canonical(
                    {
                        "prompt": target["prompt"],
                        "context": target["context"],
                        "answer_groups": [
                            {
                                "label": group["label"],
                                "items": [item["text"] for item in group["items"]],
                            }
                            for group in target["answer_groups"]
                        ],
                    }
                ),
                "unit_ids": list(
                    dict.fromkeys(
                        uid
                        for iid in target["member_idea_ids"]
                        for uid in idea_map[iid]["unit_ids"]
                    )
                ),
                "evidence": list(
                    {
                        (e["unit_id"], e["quote"]): e
                        for iid in target["member_idea_ids"]
                        for e in idea_map[iid]["evidence"]
                    }.values()
                ),
            }
            for target in catalog["targets"]
        ]
    cards = compact_cards(objects, units)
    unit_map = {unit["id"]: unit for unit in units}
    expected = {card["id"] for card in cards}
    budget = _Budget(invoke, max_bytes, fits)
    report = {
        "mode": "compact",
        "original_cards": len(cards),
        "hierarchy_levels": 0,
        "groups": [],
        "requests": budget.records,
    }
    shape = _route_shape()
    data = _route_data(shared, brief, cards)

    def check(raw):
        restored = _restore_shared(raw, objects)
        if not allow_omissions and restored.get("omitted"):
            raise ProductionError(
                "This reconciliation must preserve every input object; omissions are forbidden"
            )
        _diagnose_route(restored, expected)
        checked = _route_check(restored, expected, unit_map)
        if route_validator:
            route_validator(checked)
        return checked

    if budget.allows("production_route", instruction, shape, data):
        route = budget.call(
            "production_route", "global", instruction, shape, data, check
        )
    else:
        report["mode"] = "hierarchical"
        outline = _outline(cards, shared, brief, budget, workers, instruction, report)
        sections = [
            {key: value for key, value in section.items() if key != "idea_ids"}
            for section in outline["sections"]
        ]
        assignment_for = lambda rows: {
            **_shared_for_cards(shared, rows),
            "brief": brief,
            "format": fmt,
            "outline": {
                "title": outline["title"],
                "summary": outline["summary"],
                "sections": sections,
            },
            "ideas": rows,
        }
        batches = budget.pack(
            _interleave(cards),
            "production_assign",
            ASSIGN_INSTRUCTION,
            ASSIGN_SHAPE,
            assignment_for,
        )

        def check_assignment(raw, batch):
            checked = _assign_check(raw, batch, sections, objects)
            if not allow_omissions and checked["omitted"]:
                raise ProductionError(
                    "This reconciliation must preserve every input object; omissions are forbidden"
                )
            return checked

        def assign(job):
            index, batch = job
            return budget.call(
                "production_assign",
                f"batch_{index}",
                ASSIGN_INSTRUCTION,
                ASSIGN_SHAPE,
                assignment_for(batch),
                lambda raw: check_assignment(raw, batch),
            )

        results = bounded_map(assign, list(enumerate(batches)), workers)
        by_section = defaultdict(list)
        omitted, shared_context = [], []
        for result in results:
            for row in result["assignments"]:
                by_section[row["section_id"]].extend(row["idea_ids"])
            omitted.extend(result["omitted"])
            shared_context.extend(result["shared_context"])
        retained = {section["id"] for section in sections if by_section[section["id"]]}
        empty_dependencies = [
            (section["id"], dep)
            for section in sections
            if section["id"] in retained
            for key in ("context_section_ids", "candidate_context_ids")
            for dep in section[key]
            if dep not in retained
        ]
        if empty_dependencies:
            raise ProductionError(
                f"Outline dependencies reference sections with no assigned material: {empty_dependencies}"
            )
        route = {
            "title": outline["title"],
            "summary": outline["summary"],
            "sections": [
                {**section, "idea_ids": by_section[section["id"]]}
                for section in sections
                if section["id"] in retained
            ],
            "omitted": omitted,
            "shared_context": shared_context,
        }
        _diagnose_route(route, expected)
        route = _route_check(route, expected, unit_map)
        if route_validator:
            route_validator(route)
        report["assignment_batches"] = len(batches)
        report["outline_omissions"] = outline["omitted"]
    if catalog:
        translated = copy.deepcopy(route)
        for section in translated["sections"]:
            section["target_ids"] = section.pop("idea_ids")
        translated["omitted"] = [
            {"target_id": row["idea_id"], "reason": row["reason"]}
            for row in translated["omitted"]
        ]
        route = _route_check(translated, set(idea_map), unit_map, catalog)
    return route, report


def _merge_answer_groups(targets):
    """Collapse identical answers after the model decides target membership."""
    groups = {}
    for target in targets:
        for group in target["answer_groups"]:
            items = groups.setdefault(group["label"], {})
            for item in group["items"]:
                existing = items.setdefault(
                    item["text"], {"supports": {}, "evidence": {}}
                )
                existing["supports"].update(dict.fromkeys(item["supports_idea_ids"]))
                existing["evidence"].update(
                    {
                        (e["unit_id"], e["quote"]): copy.deepcopy(e)
                        for e in item["evidence"]
                    }
                )
    return [
        {
            "label": label,
            "items": [
                {
                    "text": text,
                    "supports_idea_ids": list(item["supports"]),
                    "evidence": list(item["evidence"].values()),
                }
                for text, item in items.items()
            ],
        }
        for label, items in groups.items()
    ]


def target_bounded(
    ideas, units, brief, invoke: Invoke, *, max_bytes, shared=None, workers=8, fits=None
):
    """Build local exact-answer targets, then reconcile their complete task cards.

    Cross-batch merging is a model decision. Code carries every original member,
    answer item and citation into the merged target, and preserves explicit
    different-context boundaries. This cannot establish semantic completeness.
    """
    shared = dict(shared or {})
    budget = _Budget(invoke, max_bytes, fits)
    source_by_unit = {u["id"]: u.get("source_id", "") for u in units}
    source_cards = [
        {
            **idea,
            "source_ids": list(
                dict.fromkeys(source_by_unit.get(uid, "") for uid in idea["unit_ids"])
            ),
        }
        for idea in ideas
    ]
    data_for = lambda rows: {
        **_shared_for_cards(shared, rows),
        "brief": brief,
        "ideas": rows,
    }
    whole = data_for(source_cards)
    report = {"mode": "single", "requests": budget.records, "local_batches": 1}
    if budget.allows("production_targets", TARGET_INSTRUCTION, TARGET_SHAPE, whole):
        result = budget.call(
            "production_targets",
            "global",
            TARGET_INSTRUCTION,
            TARGET_SHAPE,
            whole,
            lambda raw: validate_retrieval_targets(raw, ideas, units),
        )
        return result, report
    report["mode"] = "reconciled"
    interleaved = _interleave(source_cards)
    batches = budget.pack(
        interleaved, "production_targets", TARGET_INSTRUCTION, TARGET_SHAPE, data_for
    )
    report["local_batches"] = len(batches)

    def build(job):
        index, batch = job
        return budget.call(
            "production_targets",
            f"batch_{index}",
            TARGET_INSTRUCTION,
            TARGET_SHAPE,
            data_for(batch),
            lambda raw: validate_retrieval_targets(raw, batch, units),
        )

    results = bounded_map(build, list(enumerate(batches)), workers)
    targets, relations = [], []
    for result in results:
        names = {
            target["id"]: "target_" + digest(sorted(target["member_idea_ids"]))[:24]
            for target in result["targets"]
        }
        targets.extend(
            {**target, "id": names[target["id"]]} for target in result["targets"]
        )
        relations.extend(
            {
                **relation,
                "from_target_id": names[relation["from_target_id"]],
                "to_target_id": names[relation["to_target_id"]],
            }
            for relation in result["relations"]
        )
    target_map = {target["id"]: target for target in targets}
    related = defaultdict(list)
    for relation in relations:
        related[relation["from_target_id"]].append(relation)
        related[relation["to_target_id"]].append(relation)
    merge_cards = []
    for target in targets:
        evidence = list(
            {
                (e["unit_id"], e["quote"]): e
                for group in target["answer_groups"]
                for item in group["items"]
                for e in item["evidence"]
            }.values()
        )
        merge_cards.append(
            {
                "id": target["id"],
                "title": target["title"],
                "explanation": canonical(
                    {
                        "prompt": target["prompt"],
                        "context": target["context"],
                        "membership_relation": target["membership_relation"],
                        "answer_groups": [
                            {
                                "label": group["label"],
                                "items": [item["text"] for item in group["items"]],
                            }
                            for group in target["answer_groups"]
                        ],
                        "relations": related[target["id"]],
                    }
                ),
                "unit_ids": list(dict.fromkeys(e["unit_id"] for e in evidence)),
                "evidence": evidence,
            }
        )

    def validate_merge(route):
        owners = {}
        for section in route["sections"]:
            if len(section["idea_ids"]) > 1 and section["representation"][
                "kind"
            ] not in {"equivalent", "variant"}:
                raise ProductionError(
                    "Merged retrieval targets must declare equivalent or variant membership"
                )
            for tid in section["idea_ids"]:
                owners[tid] = section["id"]
        for relation in relations:
            if (
                relation["kind"] == "different_context"
                and owners[relation["from_target_id"]]
                == owners[relation["to_target_id"]]
            ):
                raise ProductionError(
                    "Target reconciliation must retain explicitly different-context targets separately"
                )

    route, merge_report = plan_bounded(
        merge_cards,
        units,
        brief,
        invoke,
        max_bytes=max_bytes,
        shared=shared,
        workers=workers,
        fits=fits,
        instruction=ROUTE_INSTRUCTION + " " + TARGET_MERGE_INSTRUCTION,
        allow_omissions=False,
        route_validator=validate_merge,
    )
    report["reconciliation"] = merge_report
    merged, owner = [], {}
    for section in route["sections"]:
        originals = [target_map[tid] for tid in section["idea_ids"]]
        members = [iid for target in originals for iid in target["member_idea_ids"]]
        tid = "target_" + digest(sorted(members))[:24]
        for target in originals:
            owner[target["id"]] = tid
        if len(originals) == 1:
            merged.append({**originals[0], "id": tid})
            continue
        relation = section["representation"]["kind"]
        if relation not in {"equivalent", "variant"}:
            raise ProductionError(
                "merged retrieval targets must declare equivalent or variant membership"
            )
        merged.append(
            {
                "id": tid,
                "title": section["title"],
                "prompt": section["purpose"],
                "context": section["representation"]["rationale"],
                "membership_relation": relation,
                "member_idea_ids": members,
                "answer_groups": _merge_answer_groups(originals),
            }
        )
    merged_relations, seen = [], {}
    for relation in relations:
        left, right = owner[relation["from_target_id"]], owner[relation["to_target_id"]]
        if left == right:
            if relation["kind"] == "different_context":
                raise ProductionError(
                    "target reconciliation merged an explicitly different-context pair"
                )
            continue
        pair = tuple(sorted((left, right)))
        if pair in seen:
            if seen[pair]["kind"] != relation["kind"]:
                raise ProductionError(
                    "target reconciliation produced incompatible cross-target relations"
                )
            continue
        value = {**relation, "from_target_id": left, "to_target_id": right}
        seen[pair] = value
        merged_relations.append(value)
    catalog = validate_retrieval_targets(
        {"targets": merged, "relations": merged_relations}, ideas, units
    )
    return catalog, report


def refine_sections(
    route,
    ideas,
    units,
    brief,
    invoke: Invoke,
    *,
    section_fits,
    max_bytes,
    shared=None,
    workers=8,
    fits=None,
    catalog=None,
):
    """Subdivide oversized writing assignments using semantic plans.

    ``section_fits(section, route)`` must inspect the actual writer envelope.
    Counts never stand in for source/token size. Context and candidate dependencies
    on a split parent expand to its children; this can reveal a genuinely
    indivisible context requirement, which is reported rather than truncated.
    """
    route = copy.deepcopy(route)
    original_ids = {idea["id"] for idea in ideas}
    idea_by_id = {idea["id"]: idea for idea in ideas}
    unit_map = {unit["id"]: unit for unit in units}
    report = {"rounds": [], "subdivided_sections": 0}
    while True:
        oversized = [
            section for section in route["sections"] if not section_fits(section, route)
        ]
        if not oversized:
            return route, report

        def subdivide(section):
            owned = section.get("target_ids", section["idea_ids"])
            if len(owned) < 2:
                raise ProductionError(
                    f"Section {section['id']} exceeds the writer budget with one indivisible source idea/target "
                    "or its required context. Use a larger model budget or explicitly revise the source/assignment."
                )
            local_ideas = [idea_by_id[iid] for iid in section["idea_ids"]]
            local_catalog = None
            if catalog:
                selected = set(owned)
                local_catalog = {
                    **catalog,
                    "targets": [
                        target
                        for target in catalog["targets"]
                        if target["id"] in selected
                    ],
                    "relations": [
                        link
                        for link in catalog.get("relations", [])
                        if link["from_target_id"] in selected
                        and link["to_target_id"] in selected
                    ],
                }
            context = {
                **(shared or {}),
                "parent_section": {
                    key: section[key] for key in ("title", "purpose", "representation")
                },
                "reason_for_subdivision": "The actual writer request, including source text and required context, exceeds its configured model budget.",
            }
            refined, detail = plan_bounded(
                local_ideas,
                units,
                brief,
                invoke,
                max_bytes=max_bytes,
                shared=context,
                workers=1,
                fits=fits,
                catalog=local_catalog,
                allow_omissions=False,
                instruction=ROUTE_INSTRUCTION
                + " Divide the parent section into smaller coherent writing tasks. "
                "Its complete writer request exceeds the configured model budget. Preserve all owned material "
                "and the applicable parent requirements. Choose meaningful boundaries and necessary earlier "
                "context; every child must own a strictly smaller set. No omissions or artificial equal-sized quotas.",
            )
            children = refined["sections"]
            if len(children) < 2 or any(
                len(child.get("target_ids", child["idea_ids"])) >= len(owned)
                for child in children
            ):
                raise ProductionError(
                    f"Section {section['id']} subdivision did not produce strictly smaller writing assignments"
                )
            names = {
                child["id"]: "section_"
                + digest([section["id"], child["id"], child["idea_ids"]])[:24]
                for child in children
            }
            renamed = []
            for child in children:
                row = {**child, "id": names[child["id"]]}
                for key in ("context_section_ids", "candidate_context_ids"):
                    row[key] = list(
                        dict.fromkeys(
                            section.get(key, []) + [names[cid] for cid in child[key]]
                        )
                    )
                renamed.append(row)
            relationships = copy.deepcopy(refined["shared_context"])
            for relationship in relationships:
                if "section_ids" in relationship:
                    relationship["section_ids"] = [
                        names[sid] for sid in relationship["section_ids"]
                    ]
            return section["id"], renamed, relationships, detail

        results = bounded_map(subdivide, oversized, workers)
        replacements = {sid: children for sid, children, _, _ in results}
        shared_context = list(route["shared_context"])
        shared_seen = {canonical(row) for row in shared_context}
        for _, _, relationships, _ in results:
            for relationship in relationships:
                if canonical(relationship) not in shared_seen:
                    shared_context.append(relationship)
                    shared_seen.add(canonical(relationship))
        sections = []
        for parent in route["sections"]:
            for child in replacements.get(parent["id"], [parent]):
                child = dict(child)
                for key in ("context_section_ids", "candidate_context_ids"):
                    child[key] = list(
                        dict.fromkeys(
                            replacement["id"]
                            for cid in child[key]
                            for replacement in replacements.get(cid, [{"id": cid}])
                        )
                    )
                sections.append(child)
        for relationship in shared_context:
            if "section_ids" in relationship:
                relationship["section_ids"] = list(
                    dict.fromkeys(
                        child["id"]
                        for sid in relationship["section_ids"]
                        for child in replacements.get(sid, [{"id": sid}])
                    )
                )
        route = _route_check(
            {**route, "sections": sections, "shared_context": shared_context},
            original_ids,
            unit_map,
            catalog,
        )
        report["subdivided_sections"] += len(results)
        report["rounds"].append(
            [
                {
                    "parent_section_id": sid,
                    "child_section_ids": [child["id"] for child in children],
                    "planning": detail,
                }
                for sid, children, _, detail in results
            ]
        )
