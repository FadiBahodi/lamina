"""Canonical retrieval ownership: true duplicates versus repeated answers in new contexts."""

from __future__ import annotations

import copy

import pytest

from lamina.production import plan_production, run_production
from lamina.retrieval_targets import RetrievalTargetError, validate_retrieval_targets
from lamina.production_example import fixture_request_budget
from lamina.store import Workspace

TEXTS = [
    "A stale write is rejected by a fencing token.",
    "A stale write is rejected by a fencing token.",
    "A stale write is rejected by a fencing token.",
    "A retry obtains a new token before it writes.",
]


def _workspace(tmp_path):
    ws = Workspace(tmp_path)
    for index, text in enumerate(TEXTS, 1):
        sid = f"source_{index}"
        ws.put_source(
            {
                "id": sid,
                "title": f"Engineering note {index}",
                "filename": f"note-{index}.md",
                "sha256": f"hash-{index}",
                "role": "teaching",
            }
        )
        ws.put_units(
            [
                {
                    "id": f"unit_{index}",
                    "source_id": sid,
                    "role": "teaching",
                    "ordinal": 0,
                    "heading": f"Context {index}",
                    "locator": "line 1",
                    "text": text,
                }
            ]
        )
    return ws


def _catalog(ideas):
    ids = [idea["id"] for idea in ideas]

    def item(text, members, indexes):
        return {
            "text": text,
            "supports_idea_ids": members,
            "evidence": [
                {"unit_id": f"unit_{n}", "quote": TEXTS[n - 1]} for n in indexes
            ],
        }

    return {
        "targets": [
            {
                "id": "duplicate-stale-write",
                "title": "Stale writes under the normal worker lease",
                "prompt": "What rejects a stale write during an ordinary worker handoff?",
                "context": "Normal worker handoff",
                "member_idea_ids": ids[:2],
                "membership_relation": "equivalent",
                "answer_groups": [
                    {"label": "Guard", "items": [item(TEXTS[0], ids[:2], [1, 2])]}
                ],
            },
            {
                "id": "recovery-stale-write",
                "title": "Stale writes during recovery",
                "prompt": "What rejects a stale write after a recovery retry?",
                "context": "Recovery after a process restart",
                "member_idea_ids": [ids[2]],
                "membership_relation": "unique",
                "answer_groups": [
                    {"label": "Guard", "items": [item(TEXTS[2], [ids[2]], [3])]}
                ],
            },
            {
                "id": "fresh-retry-token",
                "title": "Fresh retry token",
                "prompt": "What must a retry obtain before writing?",
                "context": "A new worker retry",
                "member_idea_ids": [ids[3]],
                "membership_relation": "unique",
                "answer_groups": [
                    {"label": "Prerequisite", "items": [item(TEXTS[3], [ids[3]], [4])]}
                ],
            },
        ],
        "relations": [
            {
                "from_target_id": "duplicate-stale-write",
                "to_target_id": "recovery-stale-write",
                "kind": "different_context",
                "reason": "The answer recurs in a different presentation.",
            },
            {
                "from_target_id": "duplicate-stale-write",
                "to_target_id": "fresh-retry-token",
                "kind": "variant",
                "reason": "Both involve fencing but ask different actions.",
            },
        ],
    }


class RetrievalFixture:
    identity = "original-retrieval-fixture-v1"

    def __init__(self, omit_recovery=False):
        self.requests = []
        self.omit_recovery = omit_recovery

    def budget_for(self, stage):
        return fixture_request_budget(stage, max_items=16)

    def call(self, stage, request):
        self.requests.append((stage, request))
        data = request["input"]
        if stage == "production_read":
            return {
                "ideas": [
                    {
                        "title": unit["heading"],
                        "explanation": "".join(s["text"] for s in unit["spans"]),
                        "unit_ids": [unit["id"]],
                        "evidence_refs": [
                            {
                                "span_id": unit["spans"][0]["id"],
                                "end_span_id": unit["spans"][-1]["id"],
                            }
                        ],
                    }
                    for unit in data["core"]
                ]
            }
        if stage == "production_targets":
            return _catalog(data["ideas"])
        if stage == "production_route":
            targets = data["ideas"]
            assert all(
                "evidence_refs" in target and "explanation" in target
                for target in targets
            )
            chosen = [
                t
                for t in targets
                if not (self.omit_recovery and t["id"] == "recovery-stale-write")
            ]
            return {
                "title": "Worker retrieval guide",
                "summary": "Three distinct questions",
                "sections": [
                    {
                        "id": "s1",
                        "title": "Worker handoff and recovery",
                        "purpose": "Answer the owned retrieval tasks",
                        "idea_ids": [t["id"] for t in chosen],
                        "context_section_ids": [],
                        "representation": {
                            "kind": "question-and-answer",
                            "rationale": "Direct retrieval",
                            "requirements": ["Keep recovery context separate"],
                        },
                    }
                ],
                "omitted": (
                    [
                        {
                            "idea_id": "recovery-stale-write",
                            "reason": "Out of this guide's scope",
                        }
                    ]
                    if self.omit_recovery
                    else []
                ),
                "shared_context": [],
            }
        if stage in {"production_write", "production_repair"}:
            targets = data["assigned_targets"]
            evidence = [
                e
                for target in targets
                for group in target["answer_groups"]
                for item in group["items"]
                for e in item["evidence"]
            ]
            result = {
                "used_idea_ids": data["section"]["idea_ids"],
                "used_target_ids": data["section"]["target_ids"],
                "evidence": evidence,
            }
            if data["format"] == "assessment":
                result.update(
                    {
                        "candidate_body": "What keeps a retry safe?",
                        "marking_body": "Use a fresh fencing token.",
                    }
                )
            else:
                result["body"] = "\n\n".join(t["prompt"] for t in targets)
            return result
        if stage == "production_review":
            return {"findings": []}
        if stage == "assessment_blind_solve":
            assert set(data) == {"current_candidate_body", "prior_candidate_bodies"}
            return {"answer": "Use a fresh fencing token.", "uncertainties": []}
        if stage == "assessment_judge":
            return {"findings": []}
        raise AssertionError(stage)


def test_semantic_ownership_and_artifact_consumer(tmp_path):
    ws = _workspace(tmp_path)
    provider = RetrievalFixture()
    ids = [f"source_{n}" for n in range(1, 5)]
    plan = plan_production(
        ws,
        provider,
        "Make a worker retrieval guide",
        ids,
        {"workflow": "planned", **({"format": "guide", "retrieval_targets": True})},
    )
    catalog = plan["retrieval_targets"]
    assert len(catalog["targets"]) == 3
    assert catalog["targets"][0]["member_idea_ids"] == [
        i["id"] for i in plan["ideas"][:2]
    ]
    assert catalog["targets"][0]["membership_relation"] == "equivalent"
    assert catalog["relations"][0]["kind"] == "different_context"
    assert len(plan["route"]["sections"][0]["idea_ids"]) == 4
    receipt = run_production(ws, provider, plan)
    assert receipt["status"] == "ready"
    assert receipt["sections"][0]["used_target_ids"] == [
        t["id"] for t in catalog["targets"]
    ]
    assert receipt["retrieval_targets"] == catalog
    assert (
        "What rejects a stale write during an ordinary worker handoff?"
        in receipt["markdown"]
    )
    assert "What rejects a stale write after a recovery retry?" in receipt["markdown"]
    assert (
        receipt["markdown"].count(TEXTS[0]) >= 2
    )  # same exact answer, distinct retrieval contexts
    writers = [
        r["input"] for stage, r in provider.requests if stage == "production_write"
    ]
    assert len(writers) == 1 and len(writers[0]["assigned_targets"]) == 3
    assert receipt["metrics"]["retrieval_targets"] == 3
    second = plan_production(
        ws,
        provider,
        "Make a worker retrieval guide",
        ids,
        {"workflow": "planned", **({"format": "guide", "retrieval_targets": True})},
    )
    assert second["metrics"]["cache_misses"] == 0


def test_catalog_rejects_hallucinated_answer_missing_owner_and_false_equivalent(
    tmp_path,
):
    ws = _workspace(tmp_path)
    provider = RetrievalFixture()
    plan = plan_production(
        ws,
        provider,
        "Make a guide",
        [f"source_{n}" for n in range(1, 5)],
        {"workflow": "planned", **({"format": "guide", "retrieval_targets": True})},
    )
    ideas, units = plan["ideas"], plan["units"]
    raw = _catalog(ideas)
    invented = copy.deepcopy(raw)
    invented["targets"][0]["answer_groups"][0]["items"][0][
        "text"
    ] = "A magic lock rejects writes."
    with pytest.raises(RetrievalTargetError, match="exact substring"):
        validate_retrieval_targets(invented, ideas, units)
    missing = copy.deepcopy(raw)
    missing["targets"].pop()
    with pytest.raises(RetrievalTargetError, match="partition"):
        validate_retrieval_targets(missing, ideas, units)
    duplicate = copy.deepcopy(raw)
    duplicate["targets"][1]["member_idea_ids"] = [ideas[0]["id"]]
    with pytest.raises(RetrievalTargetError, match="exactly one"):
        validate_retrieval_targets(duplicate, ideas, units)
    false_equivalent = copy.deepcopy(raw)
    false_equivalent["relations"][0]["kind"] = "equivalent"
    with pytest.raises(RetrievalTargetError, match="equivalent targets must be merged"):
        validate_retrieval_targets(false_equivalent, ideas, units)


def test_assessment_keeps_answer_catalog_examiner_only(tmp_path):
    ws = _workspace(tmp_path)
    provider = RetrievalFixture()
    plan = plan_production(
        ws,
        provider,
        "Make questions",
        [f"source_{n}" for n in range(1, 5)],
        {
            "workflow": "planned",
            **({"format": "assessment", "retrieval_targets": True}),
        },
    )
    receipt = run_production(ws, provider, plan)
    assert receipt["status"] == "ready"
    assert "A stale write is rejected" not in receipt["candidate_markdown"]
    assert "What rejects a stale write" not in receipt["candidate_markdown"]
    assert "What rejects a stale write" in receipt["examiner_markdown"]
    assert receipt["assessment_checks"]["status"] == "passed"


def test_route_omission_stays_in_operator_plan_but_not_artifact(tmp_path):
    ws = _workspace(tmp_path)
    provider = RetrievalFixture(omit_recovery=True)
    plan = plan_production(
        ws,
        provider,
        "Make a scoped guide",
        [f"source_{n}" for n in range(1, 5)],
        {"workflow": "planned", **({"format": "guide", "retrieval_targets": True})},
    )
    assert plan["route"]["omitted"] == [
        {"target_id": "recovery-stale-write", "reason": "Out of this guide's scope"}
    ]
    assert len(plan["retrieval_targets"]["targets"]) == 3
    receipt = run_production(ws, provider, plan)
    assert (
        "What rejects a stale write during an ordinary worker handoff?"
        in receipt["retrieval_markdown"]
    )
    assert (
        "What rejects a stale write after a recovery retry?"
        not in receipt["retrieval_markdown"]
    )
    assert (
        "What rejects a stale write after a recovery retry?" not in receipt["markdown"]
    )
    writer = next(
        request for stage, request in provider.requests if stage == "production_write"
    )
    assert len(writer["input"]["assigned_targets"]) == 2


def test_large_aggregate_keeps_exact_support_without_per_call_count_caps():
    count = 1500
    text = "Pitch adjustment reduces lift."
    units = [{"id": f"unit_{n}", "text": text} for n in range(count)]
    ideas = [{"id": f"idea_{n}", "unit_ids": [f"unit_{n}"]} for n in range(count)]
    item = {
        "text": text,
        "supports_idea_ids": [idea["id"] for idea in ideas],
        "evidence": [{"unit_id": unit["id"], "quote": text} for unit in units],
    }
    target = {
        "id": "pitch",
        "title": "Pitch control",
        "prompt": "What changes lift?",
        "context": "Shared operating conditions",
        "member_idea_ids": [idea["id"] for idea in ideas],
        "membership_relation": "equivalent",
        "answer_groups": [{"label": "Control", "items": [item]}],
    }
    catalog = validate_retrieval_targets(
        {"targets": [target], "relations": []}, ideas, units
    )
    assert len(catalog["targets"][0]["member_idea_ids"]) == count
    assert (
        len(catalog["targets"][0]["answer_groups"][0]["items"][0]["evidence"]) == count
    )


def test_answer_cannot_borrow_support_from_another_members_unrelated_quote():
    units = [
        {"id": "u1", "text": "Pitch adjustment reduces lift."},
        {"id": "u2", "text": "Braking stops the rotor."},
    ]
    ideas = [{"id": "i1", "unit_ids": ["u1"]}, {"id": "i2", "unit_ids": ["u2"]}]
    target = {
        "id": "control",
        "title": "Controls",
        "prompt": "What reduces lift?",
        "context": "Rotor operation",
        "member_idea_ids": ["i1", "i2"],
        "membership_relation": "variant",
        "answer_groups": [
            {
                "label": "Answer",
                "items": [
                    {
                        "text": units[0]["text"],
                        "supports_idea_ids": ["i1", "i2"],
                        "evidence": [
                            {"unit_id": unit["id"], "quote": unit["text"]}
                            for unit in units
                        ],
                    }
                ],
            }
        ],
    }
    with pytest.raises(RetrievalTargetError, match="own cited quote containing"):
        validate_retrieval_targets({"targets": [target], "relations": []}, ideas, units)


def test_many_target_relations_are_bounded_by_unique_known_pairs():
    count = 1100
    units = [{"id": "u", "text": "Reduce lift."}]
    ideas = [{"id": f"idea_{n}", "unit_ids": ["u"]} for n in range(count)]
    targets = [
        {
            "id": f"target_{n}",
            "title": f"Context {n}",
            "prompt": "What changes lift?",
            "context": f"Operating context {n}",
            "member_idea_ids": [f"idea_{n}"],
            "membership_relation": "unique",
            "answer_groups": [
                {
                    "label": "Action",
                    "items": [
                        {
                            "text": "Reduce lift.",
                            "supports_idea_ids": [f"idea_{n}"],
                            "evidence": [{"unit_id": "u", "quote": "Reduce lift."}],
                        }
                    ],
                }
            ],
        }
        for n in range(count)
    ]
    relations = [
        {
            "from_target_id": f"target_{n}",
            "to_target_id": f"target_{n + 1}",
            "kind": "different_context",
            "reason": "Distinct fixture operating contexts.",
        }
        for n in range(count - 1)
    ]
    catalog = validate_retrieval_targets(
        {"targets": targets, "relations": relations}, ideas, units
    )
    assert len(catalog["targets"]) == count and len(catalog["relations"]) == count - 1
    with pytest.raises(RetrievalTargetError, match="one relation per target pair"):
        validate_retrieval_targets(
            {"targets": targets, "relations": relations + [relations[0]]}, ideas, units
        )


def test_target_quote_typography_recovery_retains_original_source_span():
    source = "The ‘pitch’ angle changes lift."
    units = [{"id": "u", "text": source}]
    ideas = [{"id": "i", "unit_ids": ["u"]}]
    target = {
        "id": "pitch",
        "title": "Pitch",
        "prompt": "What changes lift?",
        "context": "Rotor",
        "member_idea_ids": ["i"],
        "membership_relation": "unique",
        "answer_groups": [
            {
                "label": "Action",
                "items": [
                    {
                        "text": "angle changes lift.",
                        "supports_idea_ids": ["i"],
                        "evidence": [
                            {"unit_id": "u", "quote": "The 'pitch' angle changes lift."}
                        ],
                    }
                ],
            }
        ],
    }
    catalog = validate_retrieval_targets(
        {"targets": [target], "relations": []}, ideas, units
    )
    quote = catalog["targets"][0]["answer_groups"][0]["items"][0]["evidence"][0][
        "quote"
    ]
    assert quote == source
