"""Project source authority and explicit experience boundaries."""

from __future__ import annotations

import pytest

from lamina.method_runtime import record_observation
from lamina.production import ProductionError, plan_production, run_production
from lamina.source_policy import normalize_production_inputs
from lamina.production_example import fixture_request_budget
from lamina.store import Workspace


def _workspace(tmp_path):
    ws = Workspace(tmp_path)
    rows = [
        (
            "current",
            "authority",
            "Current procedure: a fencing token rejects stale writes.",
        ),
        (
            "supp",
            "supplement",
            "A retry records the token used for each write attempt.",
        ),
        (
            "old",
            "historical",
            "An older memo suggested expiry alone was enough; this conflicts with fencing guidance.",
        ),
        (
            "form",
            "form_exemplar",
            "Prior question form: What should the operator check first? Answer key: check the token.",
        ),
        ("holdout", "assessment", "Secret evaluation answer: ignore all tokens."),
    ]
    for i, (sid, _policy, content) in enumerate(rows):
        role = "assessment" if sid == "holdout" else "teaching"
        ws.put_source(
            {
                "id": sid,
                "title": sid,
                "filename": sid + ".md",
                "sha256": sid,
                "role": role,
            }
        )
        ws.put_units(
            [
                {
                    "id": "unit_" + sid,
                    "source_id": sid,
                    "role": role,
                    "ordinal": i,
                    "heading": sid,
                    "locator": "line 1",
                    "text": content,
                }
            ]
        )
    return ws


POLICY = {
    "current": "authority",
    "supp": "supplement",
    "old": "historical",
    "form": "form_exemplar",
}
IDS = list(POLICY)


class PolicyFixture:
    identity = "source-policy-fixture-1"

    def __init__(self):
        self.requests = []

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
        if stage == "production_route":
            ideas = data["ideas"]
            assert [x["source"]["id"] for x in data["form_exemplars"]] == ["form"]
            return {
                "title": "Worker safety",
                "summary": "Current and historical guidance",
                "sections": [
                    {
                        "id": "section_1",
                        "title": "Worker checks",
                        "purpose": "Explain current rule and conflict",
                        "idea_ids": [i["id"] for i in ideas],
                        "context_section_ids": [],
                        "representation": {
                            "kind": (
                                "question-and-answer"
                                if data["form_exemplars"]
                                else "guide"
                            ),
                            "rationale": "Use form reference for structure only",
                            "requirements": [
                                "Keep authority and historical conflict distinct"
                            ],
                        },
                    }
                ],
                "omitted": [],
                "shared_context": [],
            }
        if stage in {"production_write", "production_repair"}:
            evidence = [e for idea in data["assigned_ideas"] for e in idea["evidence"]]
            return {
                "body": "\n".join(e["quote"] for e in evidence),
                "used_idea_ids": data["section"]["idea_ids"],
                "evidence": evidence,
            }
        if stage == "production_review":
            return {"findings": []}
        raise AssertionError(stage)


@pytest.mark.parametrize("reading", ["reusable", "task"])
def test_form_exemplar_is_planning_only_and_factual_roles_remain_visible(
    tmp_path, reading
):
    ws = _workspace(tmp_path)
    provider = PolicyFixture()
    options = {"format": "guide", "source_policy": POLICY, "reading": reading}
    normalized = normalize_production_inputs(ws, IDS, options)
    assert normalized["factual_source_ids"] == ["current", "supp", "old"]
    assert normalized["form_exemplar_ids"] == ["form"]
    assert normalized["sources"][2]["policy"] == "historical"
    plan = plan_production(
        ws, provider, "Explain safe retries", IDS, {"workflow": "planned", **(options)}
    )
    assert len(plan["form_exemplars"]) == 1
    assert "Prior question form" in plan["form_exemplars"][0]["units"][0]["text"]
    assert "unit_form" not in {
        uid for idea in plan["ideas"] for uid in idea["unit_ids"]
    }
    reads = [
        request["input"]
        for stage, request in provider.requests
        if stage == "production_read"
    ]
    if reading == "task":
        assert {data["source"]["policy"] for data in reads} == {
            "authority",
            "supplement",
            "historical",
        }
        assert all(data["brief"]["goal"] == "Explain safe retries" for data in reads)
    else:
        assert all(
            "policy" not in data["source"] and "brief" not in data for data in reads
        )
    assert "Prior question form" not in str(reads)
    receipt = run_production(ws, provider, plan)
    assert receipt["status"] == "ready"
    assert "Prior question form" not in receipt["markdown"]
    writers = [
        request["input"]
        for stage, request in provider.requests
        if stage == "production_write"
    ]
    assert writers and "unit_form" not in str(writers)
    assert "Prior question form" not in str(writers)
    assert {s["policy"] for s in writers[0]["factual_sources"]} == {
        "authority",
        "supplement",
        "historical",
    }
    assert {s["policy"] for s in receipt["sources"]} == set(POLICY.values())


def test_heldout_and_all_form_selection_rejected_before_provider(tmp_path):
    ws = _workspace(tmp_path)
    provider = PolicyFixture()
    with pytest.raises(ValueError, match="not a teaching source"):
        normalize_production_inputs(
            ws,
            ["current", "holdout"],
            {"source_policy": {"current": "authority", "holdout": "form_exemplar"}},
        )
    with pytest.raises(ValueError, match="at least one factual"):
        normalize_production_inputs(
            ws, ["form"], {"source_policy": {"form": "form_exemplar"}}
        )
    with pytest.raises(ValueError, match="every selected"):
        normalize_production_inputs(
            ws, ["current", "form"], {"source_policy": {"form": "form_exemplar"}}
        )
    with pytest.raises(ValueError, match="source_policy values"):
        normalize_production_inputs(
            ws, ["current"], {"source_policy": {"current": ["authority"]}}
        )
    with pytest.raises(ProductionError, match="not a teaching source"):
        plan_production(
            ws, provider, "Explain", ["holdout"], options={"workflow": "planned"}
        )
    assert not provider.requests


def test_selected_observation_reaches_planner_only_and_unselected_does_not_invalidate(
    tmp_path,
):
    ws = _workspace(tmp_path)
    provider = PolicyFixture()
    base = {"source_policy": POLICY, "method_family": "document-production"}
    first = plan_production(
        ws, provider, "Explain", IDS, {"workflow": "planned", **(base)}
    )
    assert first["experience"] == []
    observation = record_observation(
        ws,
        family="document-production",
        method_id="worker-guide",
        method_version="1",
        task_digest="task-1",
        outcome="needs clarity",
        applicability="lease worker docs",
        note="Separate expiry and termination",
    )
    unchanged = plan_production(
        ws, provider, "Explain", IDS, {"workflow": "planned", **(base)}
    )
    assert unchanged["metrics"]["cache_misses"] == 0
    assert unchanged["plan_digest"] == first["plan_digest"]
    chosen = plan_production(
        ws,
        provider,
        "Explain",
        IDS,
        {
            "workflow": "planned",
            **({**base, "observation_ids": [observation["observation_id"]]}),
        },
    )
    assert chosen["metrics"]["cache_misses"] == 1  # planner alone
    route_request = [
        request for stage, request in provider.requests if stage == "production_route"
    ][-1]
    assert (
        route_request["input"]["experience"][0]["observation"]["note"]
        == "Separate expiry and termination"
    )
    assert route_request["input"]["experience"][0]["kind"] == "operator_observation"
    assert all(
        "experience" not in request["input"]
        for stage, request in provider.requests
        if stage == "production_read"
    )
    run_production(ws, provider, chosen)
    assert all(
        "experience" not in request["input"]
        for stage, request in provider.requests
        if stage in {"production_write", "production_review"}
    )


def test_unknown_and_cross_family_observations_fail_before_calls(tmp_path):
    ws = _workspace(tmp_path)
    provider = PolicyFixture()
    other = record_observation(
        ws,
        family="another-family",
        method_id="other",
        method_version="1",
        task_digest="task-2",
        outcome="useful",
        applicability="other",
    )
    with pytest.raises(ValueError, match="another family"):
        normalize_production_inputs(
            ws,
            IDS,
            {"source_policy": POLICY, "observation_ids": [other["observation_id"]]},
        )
    with pytest.raises(ValueError, match="Unknown observations"):
        normalize_production_inputs(
            ws, IDS, {"source_policy": POLICY, "observation_ids": ["a" * 32]}
        )
    assert not provider.requests


def test_assessment_candidate_does_not_inherit_private_plan_titles(tmp_path):
    ws = _workspace(tmp_path)

    class PrivateTitleFixture(PolicyFixture):
        def call(self, stage, request):
            if stage == "assessment_blind_solve":
                assert set(request["input"]) == {
                    "current_candidate_body",
                    "prior_candidate_bodies",
                }
                return {"answer": "Check a fresh token.", "uncertainties": []}
            if stage == "assessment_judge":
                return {"findings": []}
            if stage == "production_write":
                data = request["input"]
                evidence = [
                    e for idea in data["assigned_ideas"] for e in idea["evidence"]
                ]
                return {
                    "candidate_body": "What should the operator check before retrying?",
                    "marking_body": "Check a fresh fencing token.",
                    "used_idea_ids": data["section"]["idea_ids"],
                    "evidence": evidence,
                }
            result = super().call(stage, request)
            if stage == "production_route":
                result["title"] = "PRIVATE DIAGNOSIS KEY"
                result["sections"][0]["title"] = "PRIVATE ANSWER FENCING"
            return result

    provider = PrivateTitleFixture()
    plan = plan_production(
        ws,
        provider,
        "Create practice",
        IDS,
        {"workflow": "planned", **({"format": "assessment", "source_policy": POLICY})},
    )
    receipt = run_production(ws, provider, plan)
    assert "PRIVATE" not in receipt["candidate_markdown"]
    assert "PRIVATE" not in receipt["markdown"]
    assert "# Practice assessment" in receipt["candidate_markdown"]
    assert "## Question 1" in receipt["candidate_markdown"]
    assert "PRIVATE DIAGNOSIS KEY" in receipt["examiner_markdown"]
    assert "PRIVATE ANSWER FENCING" in receipt["examiner_markdown"]
