from __future__ import annotations

import copy
import threading
import time

import pytest

from lamina.assessment_checks import AssessmentCheckError, check_assessment
from lamina.production import plan_production, run_production
from test_production import FixtureProvider, workspace


class CheckProvider:
    identity = "fixture-assessment-check-v1"

    def __init__(self, *, faulty_citation=False, report_issue=False, delay=0):
        self.faulty_citation = faulty_citation
        self.report_issue = report_issue
        self.delay = delay
        self.requests = []
        self.lock = threading.Lock()

    def call(self, stage, payload):
        assert payload["protocol"] == "lamina-stage-1"
        assert payload["stage"] == stage
        with self.lock:
            self.requests.append((stage, copy.deepcopy(payload)))
        if self.delay:
            time.sleep(self.delay)
        if stage == "assessment_blind_solve":
            data = payload["input"]
            assert set(data) == {"current_candidate_body", "prior_candidate_bodies"}
            return {
                "answer": "A stale write needs a current fencing token.",
                "uncertainties": [],
            }
        if stage == "assessment_judge":
            data = payload["input"]
            assert "marking_body" in data and "evidence" in data
            if self.faulty_citation:
                return {
                    "findings": [
                        {
                            "kind": "miskeyed",
                            "issue": "Key mismatch",
                            "repair_instruction": "Correct the key",
                            "evidence": [
                                {"unit_id": "made_up", "quote": "not a source"}
                            ],
                        }
                    ]
                }
            if self.report_issue:
                return {
                    "findings": [
                        {
                            "kind": "ambiguous",
                            "issue": "Two readings are possible",
                            "repair_instruction": "Specify the intended condition",
                            "evidence": [data["evidence"][0]],
                        }
                    ]
                }
            return {"findings": []}
        raise AssertionError(stage)


def assessment(tmp_path):
    ws = workspace(tmp_path)
    producer = FixtureProvider()
    plan = plan_production(
        ws,
        producer,
        "Test lease safety",
        ["s1", "s2"],
        {"format": "assessment", "core_words": 100},
    )
    receipt = run_production(ws, producer, plan)
    assert len(receipt["sections"]) == 4
    return ws, plan, receipt


def test_blind_boundary_parallel_calls_and_cache(tmp_path):
    ws, plan, receipt = assessment(tmp_path)
    for section in receipt["sections"]:
        section["marking_body"] += " MARKING SECRET: never send to blind solve."
    provider = CheckProvider(delay=0.02)
    events = []
    result = check_assessment(
        ws, provider, plan, receipt, workers=4, progress=events.append
    )
    assert result["status"] == "passed"
    assert len(result["checks"]) == 4
    assert result["metrics"]["cache_misses"] == 8
    assert result["metrics"]["peak_provider_calls"]["assessment_blind_solve"] > 1
    assert result["metrics"]["peak_provider_calls"]["assessment_judge"] > 1
    assert len(events) == 16
    solves = [
        payload["input"]
        for stage, payload in provider.requests
        if stage == "assessment_blind_solve"
    ]
    assert len(solves) == 4
    assert {len(s["prior_candidate_bodies"]) for s in solves} == {0, 1, 2, 3}
    for data in solves:
        assert "MARKING SECRET" not in str(data)
        assert "marking_body" not in str(data)
        assert "evidence" not in str(data)
        assert "section" not in str(data)
    before = len(provider.requests)
    cached = check_assessment(ws, provider, plan, receipt, workers=4)
    assert cached["metrics"]["cache_hits"] == 8
    assert cached["metrics"]["cache_misses"] == 0
    assert len(provider.requests) == before


def test_revision_reruns_changed_and_downstream_candidate_context(tmp_path):
    ws, plan, receipt = assessment(tmp_path)
    provider = CheckProvider()
    check_assessment(ws, provider, plan, receipt)
    revised = copy.deepcopy(receipt)
    revised["sections"][2]["candidate_body"] += "\nAdditional candidate clue."
    count = len(provider.requests)
    result = check_assessment(ws, provider, plan, revised)
    assert result["metrics"]["cache_hits"] == 4  # first two solve+judge calls
    assert result["metrics"]["cache_misses"] == 4  # changed and later section
    assert len(provider.requests) - count == 4
    changed = [
        payload["input"]
        for stage, payload in provider.requests[count:]
        if stage == "assessment_blind_solve"
    ]
    assert len(changed) == 2
    assert any(
        "Additional candidate clue" in x["current_candidate_body"] for x in changed
    )
    assert any(
        "Additional candidate clue" in str(x["prior_candidate_bodies"]) for x in changed
    )


def test_judge_findings_are_typed_and_source_exact(tmp_path):
    ws, plan, receipt = assessment(tmp_path)
    provider = CheckProvider(faulty_citation=True)
    with pytest.raises(AssessmentCheckError, match="outside the section"):
        check_assessment(ws, provider, plan, receipt)

    valid = check_assessment(ws, CheckProvider(report_issue=True), plan, receipt)
    assert valid["status"] == "review"
    assert valid["metrics"]["flagged_sections"] == 4
    assert valid["checks"][0]["findings"][0]["id"].startswith("acf_")
    assert (
        valid["checks"][0]["findings"][0]["evidence"]
        == receipt["sections"][0]["evidence"]
    )


def test_requires_assessment_and_matching_source_plan(tmp_path):
    ws, plan, receipt = assessment(tmp_path)
    provider = CheckProvider()
    altered = copy.deepcopy(plan)
    altered["brief"]["goal"] = "Changed behind the plan digest"
    with pytest.raises(AssessmentCheckError, match="modified production plan"):
        check_assessment(ws, provider, altered, receipt)
    mismatched = copy.deepcopy(receipt)
    mismatched["plan_digest"] = "wrong"
    with pytest.raises(AssessmentCheckError, match="does not match plan"):
        check_assessment(ws, provider, plan, mismatched)
