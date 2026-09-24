"""Deterministic protocol fixtures: these test ownership and budgets, not model quality."""

from collections import defaultdict
import copy
import json
import re

import pytest

from lamina.call_runtime import CallTracker
from lamina.planning import compact_cards, plan_bounded, request_size, target_bounded
from lamina.production_contract import ProductionError, validated
from lamina.store import Workspace


def corpus(count=32, sources=8, topics=8):
    ideas, units = [], []
    for source in range(sources):
        for number in range(source, count, sources):
            topic = (number + number // sources) % topics
            # Both agreement and contradictions appear in multiple source files.
            condition = (
                "at high wind speeds" if number % 3 else "only at low wind speeds"
            )
            text = f"Topic {topic} turbine {number}: pitch control applies {condition}."
            uid = f"source_{source}_unit_{number}"
            units.append({"id": uid, "source_id": f"source_{source}", "text": text})
            ideas.append(
                {
                    "id": f"idea_{number}",
                    "title": f"Topic {topic} turbine behavior",
                    "explanation": text
                    + " Preserve this operating condition and do not replace it with an unconditional claim.",
                    "unit_ids": [uid],
                    "evidence": [{"unit_id": uid, "quote": text}],
                }
            )
    return ideas, units


def topic(card):
    return int(re.search(r"Topic (\d+)", card["title"])[1])


def section(number, ids, *, merge=False):
    return {
        "id": f"topic_{number}",
        "title": f"Topic {number}",
        "purpose": f"Explain topic {number} with its different operating conditions.",
        "idea_ids": ids,
        "context_section_ids": [],
        "candidate_context_ids": [],
        "representation": {
            "kind": "variant" if merge else "comparison",
            "rationale": "Keep conditional differences visible.",
            "requirements": ["Preserve operating conditions."],
        },
    }


class ScriptedPlanner:
    def __init__(self, *, inject=None, recover=False):
        self.calls = []
        self.inject = inject
        self.recover = recover
        self.validation_errors = []

    def __call__(self, stage, item, instruction, shape, data, checker):
        self.calls.append(
            {
                "stage": stage,
                "item": item,
                "instruction": instruction,
                "shape": shape,
                "data": copy.deepcopy(data),
                "request_bytes": request_size(stage, instruction, shape, data),
            }
        )
        raw = self.response(stage, instruction, data)
        if self.inject == stage:
            self.inject = None
            broken = copy.deepcopy(raw)
            if stage == "production_assign":
                broken["assignments"][0]["idea_ids"].pop()
            elif stage == "production_route":
                broken["sections"][0]["idea_ids"].append(
                    broken["sections"][0]["idea_ids"][0]
                )
            else:
                broken["groups"][0]["member_ids"].pop()
            try:
                return checker(broken)
            except ProductionError as exc:
                self.validation_errors.append(str(exc))
                if not self.recover:
                    raise
        return checker(raw)

    def response(self, stage, instruction, data):
        if stage == "production_group":
            grouped = defaultdict(list)
            for card in data["cards"]:
                grouped[topic(card)].append(card["id"])
            return {
                "groups": [
                    {
                        "id": f"group_{number}",
                        "title": f"Topic {number}",
                        "explanation": "Sources contain different operating conditions; keep their qualifications and disagreements.",
                        "member_ids": ids,
                    }
                    for number, ids in sorted(grouped.items())
                ]
            }
        if stage == "production_route":
            grouped = defaultdict(list)
            for card in data["ideas"]:
                grouped[topic(card)].append(card["id"])
            return {
                "title": "Turbine conditions",
                "summary": "Preserve the operating context.",
                "sections": [
                    section(
                        number, ids, merge="canonical retrieval target" in instruction
                    )
                    for number, ids in sorted(grouped.items())
                ],
                "omitted": [],
                "shared_context": [],
            }
        if stage == "production_assign":
            grouped = defaultdict(list)
            for card in data["ideas"]:
                grouped[topic(card)].append(card["id"])
            return {
                "assignments": [
                    {"section_id": f"topic_{number}", "idea_ids": ids}
                    for number, ids in sorted(grouped.items())
                ],
                "omitted": [],
                "shared_context": [],
            }
        if stage == "production_targets":
            return {
                "targets": [
                    {
                        "id": f"target_{index}",
                        "title": idea["title"],
                        "prompt": f"Explain {idea['title']}.",
                        "context": "Operating conditions",
                        "membership_relation": "unique",
                        "member_idea_ids": [idea["id"]],
                        "answer_groups": [
                            {
                                "label": "Conditions",
                                "items": [
                                    {
                                        "text": idea["evidence"][0]["quote"],
                                        "supports_idea_ids": [idea["id"]],
                                        "evidence": idea["evidence"],
                                    }
                                ],
                            }
                        ],
                    }
                    for index, idea in enumerate(data["ideas"])
                ],
                "relations": [],
            }
        raise AssertionError(stage)


def test_fitting_plan_keeps_full_qualifiers_without_duplicate_quote_text():
    ideas, units = corpus(8)
    provider = ScriptedPlanner()
    route, report = plan_bounded(
        ideas, units, {"goal": "Compare wind turbines"}, provider, max_bytes=30_000
    )
    assert report["mode"] == "compact"
    assert len(provider.calls) == 1
    sent = provider.calls[0]["data"]["ideas"]
    assert {row["id"]: row["explanation"] for row in sent} == {
        row["id"]: row["explanation"] for row in ideas
    }
    assert all("quote" not in ref for row in sent for ref in row["evidence_refs"])
    assert sorted(
        iid for sec in route["sections"] for iid in sec["idea_ids"]
    ) == sorted(idea["id"] for idea in ideas)


def test_over_1500_ideas_remain_exactly_owned_after_bounded_cross_source_planning():
    ideas, units = corpus(1600, topics=8)
    provider = ScriptedPlanner()
    route, report = plan_bounded(
        ideas,
        units,
        {"goal": "Compare operating conditions across eight sources"},
        provider,
        max_bytes=12_000,
        workers=4,
    )
    assert report["mode"] == "hierarchical"
    assert report["hierarchy_levels"] >= 2
    assert all(call["request_bytes"] <= 12_000 for call in provider.calls)
    assigned = [iid for sec in route["sections"] for iid in sec["idea_ids"]]
    assert len(assigned) == len(set(assigned)) == 1600
    assert set(assigned) == {idea["id"] for idea in ideas}
    original_by_id = {idea["id"]: idea for idea in ideas}
    seen = []
    for call in provider.calls:
        if call["stage"] == "production_assign":
            for card in call["data"]["ideas"]:
                assert card["explanation"] == original_by_id[card["id"]]["explanation"]
                seen.append(card["id"])
    assert set(seen) == set(assigned) and len(seen) == len(assigned)
    # A topic receives contradictory cards from several files; code never merges
    # their source propositions into a fabricated consensus.
    for sec in route["sections"]:
        members = [original_by_id[iid] for iid in sec["idea_ids"]]
        assert len({idea["unit_ids"][0].split("_unit_")[0] for idea in members}) > 1
        conditions = [idea["explanation"] for idea in members]
        assert any("only at low" in text for text in conditions)
        assert any("at high" in text for text in conditions)


def test_duplicate_owner_gets_precise_error_and_no_silent_first_owner_policy():
    ideas, units = corpus(8)
    provider = ScriptedPlanner(inject="production_route")
    with pytest.raises(ProductionError, match="duplicate=.*idea_"):
        plan_bounded(
            ideas, units, {"goal": "Compare conditions"}, provider, max_bytes=30_000
        )
    assert len(provider.calls) == 1


def test_empty_route_section_retry_explains_how_to_preserve_overview(tmp_path):
    ideas, units = corpus(8)

    class EmptyOverview:
        identity = "empty-overview-retry"

        def __init__(self):
            self.script = ScriptedPlanner()
            self.requests = []

        def call(self, stage, payload):
            self.requests.append(copy.deepcopy(payload))
            raw = self.script.response(stage, payload["instruction"], payload["input"])
            if stage == "production_route" and "validation_feedback" not in payload:
                raw["sections"].insert(0, section(99, []))
            return raw

    provider, tracker = EmptyOverview(), CallTracker(max_attempts=2)
    workspace = Workspace(tmp_path)

    def invoke(stage, item, instruction, shape, data, checker):
        return tracker.call(
            workspace,
            provider,
            stage,
            item,
            instruction,
            shape,
            data,
            lambda raw: validated(checker, raw),
            31_000,
            workload_items=len(data.get("cards", data.get("ideas", []))),
        )

    route, _ = plan_bounded(
        ideas, units, {"goal": "Compare conditions"}, invoke, max_bytes=30_000
    )

    route_requests = [
        request for request in provider.requests if request["stage"] == "production_route"
    ]
    assert len(route_requests) == 2
    message = route_requests[1]["validation_feedback"]["message"]
    assert "must own at least one supplied card" in message
    assert "overview relationships in shared_context" in message
    assert sum(len(row["idea_ids"]) for row in route["sections"]) == len(ideas)


def test_missing_assignment_is_repaired_only_by_callers_explicit_validation_policy():
    ideas, units = corpus(300)
    provider = ScriptedPlanner(inject="production_assign", recover=True)
    route, report = plan_bounded(
        ideas, units, {"goal": "Compare conditions"}, provider, max_bytes=12_000
    )
    assert (
        provider.validation_errors
        and "missing=['idea_" in provider.validation_errors[0]
    )
    assert sum(len(s["idea_ids"]) for s in route["sections"]) == len(ideas)
    # The planner itself added no hidden correction stage or guessed ownership.
    assert len(report["requests"]) == len(provider.calls)


def test_summary_outline_forbids_references_and_retry_gets_actionable_feedback(tmp_path):
    ideas, units = corpus(300)

    class ReferencingSummaryOutline:
        identity = "summary-outline-retry"

        def __init__(self):
            self.script = ScriptedPlanner()
            self.requests = []
            self.invalid_outline_sent = False

        def call(self, stage, payload):
            self.requests.append(copy.deepcopy(payload))
            raw = self.script.response(stage, payload["instruction"], payload["input"])
            if stage == "production_route" and not self.invalid_outline_sent:
                self.invalid_outline_sent = True
                raw["shared_context"] = [
                    {
                        "statement": "The summary groups are related.",
                        "section_ids": [raw["sections"][0]["id"]],
                        "evidence_refs": [
                            {
                                "idea_id": payload["input"]["ideas"][0]["id"],
                                "evidence_index": 0,
                            }
                        ],
                    }
                ]
            return raw

    provider, tracker = ReferencingSummaryOutline(), CallTracker(max_attempts=2)
    workspace = Workspace(tmp_path)

    def invoke(stage, item, instruction, shape, data, checker):
        return tracker.call(
            workspace,
            provider,
            stage,
            item,
            instruction,
            shape,
            data,
            lambda raw: validated(checker, raw),
                13_000,
            workload_items=len(data.get("cards", data.get("ideas", []))),
        )

    route, report = plan_bounded(
        ideas, units, {"goal": "Compare conditions"}, invoke, max_bytes=12_000
    )

    assert report["mode"] == "hierarchical"
    outline_requests = [
        request for request in provider.requests if request["stage"] == "production_route"
    ]
    assert len(outline_requests) == 2
    assert outline_requests[0]["expected_shape"]["shared_context"] == []
    assert outline_requests[1]["validation_feedback"]["message"] == (
        "Summary cards have no source references; return shared_context: []; "
        "later assignment adds relationships"
    )
    assert sum(len(section["idea_ids"]) for section in route["sections"]) == len(ideas)
    assignment_shapes = [
        request["expected_shape"]
        for request in provider.requests
        if request["stage"] == "production_assign"
    ]
    assert assignment_shapes
    assert assignment_shapes[0]["shared_context"][0]["evidence_refs"]


def test_noncontracting_summary_fails_explicitly():
    ideas, units = corpus(80)

    class Repeater(ScriptedPlanner):
        def response(self, stage, instruction, data):
            if stage == "production_group":
                return {
                    "groups": [
                        {
                            "id": card["id"],
                            "title": card["title"],
                            "explanation": "Unhelpful repetition. " * 150,
                            "member_ids": [card["id"]],
                        }
                        for card in data["cards"]
                    ]
                }
            return super().response(stage, instruction, data)

    with pytest.raises(ProductionError, match="did not reduce"):
        plan_bounded(
            ideas, units, {"goal": "Compare conditions"}, Repeater(), max_bytes=12_000
        )


def test_budget_callback_can_reject_requests_below_byte_ceiling():
    ideas, units = corpus(300)
    provider = ScriptedPlanner()
    seen = []

    def model_budget(stage, instruction, shape, data):
        length = request_size(stage, instruction, shape, data)
        seen.append(length)
        return length <= 12_000

    route, report = plan_bounded(
        ideas,
        units,
        {"goal": "Compare"},
        provider,
        max_bytes=100_000,
        fits=model_budget,
    )
    assert report["mode"] == "hierarchical"
    assert all(call["request_bytes"] <= 12_000 for call in provider.calls)
    assert any(size > 12_000 for size in seen)


def test_evidence_handles_restore_exact_source_without_model_retyping():
    ideas, units = corpus(8)

    class Citing(ScriptedPlanner):
        def response(self, stage, instruction, data):
            raw = super().response(stage, instruction, data)
            raw["shared_context"] = [
                {
                    "statement": "Operating conditions differ.",
                    "evidence_refs": [
                        {"idea_id": ideas[0]["id"], "evidence_index": 0},
                        {"idea_id": ideas[1]["id"], "evidence_index": 0},
                    ],
                }
            ]
            return raw

    route, _ = plan_bounded(
        ideas, units, {"goal": "Compare"}, Citing(), max_bytes=30_000
    )
    assert route["shared_context"][0]["evidence"] == [
        ideas[0]["evidence"][0],
        ideas[1]["evidence"][0],
    ]


def test_indivisible_card_fails_before_model_call():
    ideas, units = corpus(1, sources=1, topics=1)
    ideas[0]["explanation"] = "Dense conditions " * 5_000
    provider = ScriptedPlanner()
    with pytest.raises(ProductionError, match="indivisible card"):
        plan_bounded(ideas, units, {"goal": "Compare"}, provider, max_bytes=12_000)
    assert provider.calls == []


def test_target_reconciliation_preserves_every_original_answer_and_source():
    ideas, units = corpus(48, topics=4)
    provider = ScriptedPlanner()
    catalog, report = target_bounded(
        ideas,
        units,
        {"goal": "Build retrieval questions"},
        provider,
        shared={"format": "guide"},
        max_bytes=12_000,
    )
    assert report["mode"] == "reconciled"
    assert report["local_batches"] > 1
    assert len(catalog["targets"]) == 4
    assert all(call["request_bytes"] <= 12_000 for call in provider.calls)
    assert sorted(
        iid for t in catalog["targets"] for iid in t["member_idea_ids"]
    ) == sorted(i["id"] for i in ideas)
    answers = [
        item
        for t in catalog["targets"]
        for group in t["answer_groups"]
        for item in group["items"]
    ]
    assert len(answers) == len(ideas)
    assert {e["unit_id"] for item in answers for e in item["evidence"]} == {
        u["id"] for u in units
    }


def test_plan_of_targets_keeps_target_answer_groups_indivisible():
    ideas, units = corpus(8)
    provider = ScriptedPlanner()
    catalog, _ = target_bounded(
        ideas, units, {"goal": "Build questions"}, provider, max_bytes=30_000
    )
    route, _ = plan_bounded(
        ideas,
        units,
        {"goal": "Order questions"},
        provider,
        max_bytes=30_000,
        catalog=catalog,
    )
    target_by_id = {target["id"]: target for target in catalog["targets"]}
    for sec in route["sections"]:
        assert set(sec["idea_ids"]) == {
            iid
            for tid in sec["target_ids"]
            for iid in target_by_id[tid]["member_idea_ids"]
        }


def test_refinement_uses_writer_context_and_rewrites_candidate_dependencies():
    from lamina.planning import refine_sections

    ideas, units = corpus(16, topics=1)
    source_bytes = {
        idea["id"]: len(units[index]["text"].encode())
        for index, idea in enumerate(ideas)
    }
    before = section(0, [idea["id"] for idea in ideas[:8]])
    after = section(1, [idea["id"] for idea in ideas[8:]])
    after["candidate_context_ids"] = [before["id"]]
    route = {
        "title": "Wind",
        "summary": "Operating conditions",
        "sections": [before, after],
        "omitted": [],
        "shared_context": [],
    }

    class Subdivider(ScriptedPlanner):
        def response(self, stage, instruction, data):
            if stage == "production_route":
                cards = data["ideas"]
                middle = len(cards) // 2
                return {
                    "title": "Wind",
                    "summary": "Coherent operating cases",
                    "sections": [
                        section(0, [card["id"] for card in cards[:middle]]),
                        section(1, [card["id"] for card in cards[middle:]]),
                    ],
                    "omitted": [],
                    "shared_context": [],
                }
            return super().response(stage, instruction, data)

    provider = Subdivider()
    observed = []

    def writer_fits(part, current):
        size = sum(source_bytes[iid] for iid in part["idea_ids"])
        observed.append((part["id"], size))
        return size <= 280

    refined, report = refine_sections(
        route,
        ideas,
        units,
        {"goal": "Explain"},
        provider,
        section_fits=writer_fits,
        max_bytes=30_000,
    )
    assert len(refined["sections"]) == 4
    assert report["subdivided_sections"] == 2
    assert all(writer_fits(part, refined) for part in refined["sections"])
    first_ids = [part["id"] for part in refined["sections"][:2]]
    assert all(
        part["candidate_context_ids"] == first_ids for part in refined["sections"][2:]
    )
    assert sorted(
        iid for part in refined["sections"] for iid in part["idea_ids"]
    ) == sorted(idea["id"] for idea in ideas)


def test_refinement_never_silently_splits_indivisible_target_or_drops_context():
    from lamina.planning import refine_sections

    ideas, units = corpus(1, sources=1, topics=1)
    route = {
        "title": "Wind",
        "summary": "Conditions",
        "sections": [section(0, [ideas[0]["id"]])],
        "omitted": [],
        "shared_context": [],
    }
    provider = ScriptedPlanner()
    with pytest.raises(ProductionError, match="indivisible source"):
        refine_sections(
            route,
            ideas,
            units,
            {"goal": "Explain"},
            provider,
            section_fits=lambda *_: False,
            max_bytes=30_000,
        )
    assert provider.calls == []


def test_target_reconciliation_rejects_merging_known_different_contexts():
    ideas, units = corpus(48, topics=4)

    class IncompatibleMerge(ScriptedPlanner):
        def response(self, stage, instruction, data):
            raw = super().response(stage, instruction, data)
            if stage == "production_targets":
                by_topic = defaultdict(list)
                for target in raw["targets"]:
                    by_topic[topic(target)].append(target)
                pair = next(
                    (rows[:2] for rows in by_topic.values() if len(rows) >= 2), None
                )
                if pair:
                    raw["relations"] = [
                        {
                            "from_target_id": pair[0]["id"],
                            "to_target_id": pair[1]["id"],
                            "kind": "different_context",
                            "reason": "These fixture tasks require different operating presentations.",
                        }
                    ]
            return raw

    with pytest.raises(ProductionError, match="different-context"):
        target_bounded(
            ideas,
            units,
            {"goal": "Build questions"},
            IncompatibleMerge(),
            shared={"format": "guide"},
            max_bytes=12_000,
        )


def test_source_authority_follows_cards_through_grouping_and_assignment():
    ideas, units = corpus(300)
    provider = ScriptedPlanner()
    sources = [
        {
            "id": f"source_{n}",
            "title": f"Source {n}",
            "authority": "historical" if n == 0 else "authority",
        }
        for n in range(8)
    ]
    plan_bounded(
        ideas,
        units,
        {"goal": "Compare current and historical operating guidance"},
        provider,
        shared={"sources": sources, "format": "document"},
        max_bytes=12_000,
    )
    assert any(call["stage"] == "production_group" for call in provider.calls)
    for call in provider.calls:
        cards = call["data"].get("ideas", call["data"].get("cards"))
        selected = {sid for card in cards for sid in card["source_ids"]}
        expected = [source for source in sources if source["id"] in selected]
        assert call["data"]["sources"] == expected


def test_identical_answer_dedup_keeps_all_source_support_after_semantic_merge():
    from lamina.planning import _merge_answer_groups

    targets = [
        {
            "answer_groups": [
                {
                    "label": "Pitch",
                    "items": [
                        {
                            "text": "Reduce lift.",
                            "supports_idea_ids": [f"idea_{number}"],
                            "evidence": [
                                {"unit_id": f"unit_{number}", "quote": "Reduce lift."}
                            ],
                        }
                    ],
                }
            ]
        }
        for number in range(1500)
    ]
    groups = _merge_answer_groups(targets)
    assert len(groups) == len(groups[0]["items"]) == 1
    answer = groups[0]["items"][0]
    assert len(answer["supports_idea_ids"]) == len(answer["evidence"]) == 1500


def test_shared_relationship_scope_survives_evidence_restoration_and_subdivision():
    from lamina.planning import refine_sections

    ideas, units = corpus(8, topics=1)
    before = section(0, [idea["id"] for idea in ideas])
    relation = {
        "statement": "Conditions differ within this section.",
        "section_ids": [before["id"]],
        "evidence": [ideas[0]["evidence"][0]],
    }
    route = {
        "title": "Wind",
        "summary": "Conditions",
        "sections": [before],
        "omitted": [],
        "shared_context": [relation],
    }

    class ScopedSubdivider(ScriptedPlanner):
        def response(self, stage, instruction, data):
            raw = super().response(stage, instruction, data)
            if stage == "production_route":
                cards = data["ideas"]
                middle = len(cards) // 2
                raw["sections"] = [
                    section(0, [card["id"] for card in cards[:middle]]),
                    section(1, [card["id"] for card in cards[middle:]]),
                ]
                raw["shared_context"] = [
                    {
                        "statement": "One scoped operating condition.",
                        "section_ids": ["topic_1"],
                        "evidence_refs": [
                            {"idea_id": cards[-1]["id"], "evidence_index": 0}
                        ],
                    }
                ]
            return raw

    refined, _ = refine_sections(
        route,
        ideas,
        units,
        {"goal": "Explain"},
        ScopedSubdivider(),
        section_fits=lambda part, _: len(part["idea_ids"]) <= 4,
        max_bytes=30_000,
    )
    child_ids = [part["id"] for part in refined["sections"]]
    assert refined["shared_context"][0]["section_ids"] == child_ids
    assert refined["shared_context"][1]["section_ids"] == [child_ids[1]]


def test_target_batches_scope_many_file_metadata_under_stage_budget():
    ideas, units = corpus(90, sources=90, topics=4)
    sources = [
        {
            "id": f"source_{n}",
            "title": f"Operating guidance from source {n}",
            "filename": f"manufacturing-and-operation-notes-for-site-{n}-"
            + "source-filename-" * 8
            + ".pdf",
            "sha256": f"{n:064x}",
            "role": "teaching",
            "policy": "historical" if n % 3 == 0 else "authority",
        }
        for n in range(90)
    ]
    provider = ScriptedPlanner()

    # Heterogeneous stages: a small target extraction model and a larger planner.
    # Repeating every source header exceeded the extraction budget even for one idea.
    def fits(stage, instruction, shape, data):
        return request_size(stage, instruction, shape, data) <= (
            6_000 if stage == "production_targets" else 120_000
        )

    catalog, report = target_bounded(
        ideas,
        units,
        {"goal": "Preserve source-specific operating conditions"},
        provider,
        shared={"format": "guide", "sources": sources},
        max_bytes=120_000,
        fits=fits,
    )
    assert report["mode"] == "reconciled" and report["local_batches"] > 1
    assert {
        iid for target in catalog["targets"] for iid in target["member_idea_ids"]
    } == {idea["id"] for idea in ideas}
    target_calls = [
        call for call in provider.calls if call["stage"] == "production_targets"
    ]
    assert all(call["request_bytes"] <= 6_000 for call in target_calls)
    for call in target_calls:
        selected = {sid for card in call["data"]["ideas"] for sid in card["source_ids"]}
        assert call["data"]["sources"] == [
            source for source in sources if source["id"] in selected
        ]
        assert len(call["data"]["sources"]) < len(sources)
