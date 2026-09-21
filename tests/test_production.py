from __future__ import annotations

import threading
import time

import pytest

from lamina.production import (
    ProductionError,
    build_production,
    plan_production,
    run_production,
)
from lamina.store import Workspace


def workspace(tmp_path):
    ws = Workspace(tmp_path)
    for sid, title in (("s1", "Operations"), ("s2", "Reliability")):
        ws.put_source(
            {
                "id": sid,
                "title": title,
                "filename": sid + ".md",
                "sha256": sid,
                "role": "teaching",
            }
        )
    units = [
        ("u1", "s1", "A lease expires after thirty seconds. " * 14),
        ("u2", "s1", "The old worker may still run after expiry. " * 14),
        ("u3", "s2", "A fencing token rejects stale writes. " * 14),
        ("u4", "s2", "A retry uses the current token. " * 14),
    ]
    for ordinal, (uid, sid, body) in enumerate(units):
        ws.put_units(
            [
                {
                    "id": uid,
                    "source_id": sid,
                    "role": "teaching",
                    "ordinal": ordinal,
                    "heading": uid,
                    "locator": f"line {ordinal + 1}",
                    "text": body,
                }
            ]
        )
    return ws


class FixtureProvider:
    """Deterministic adapter fixture; its responses are not model-quality evidence."""

    identity = "fixture-production-v1"

    def __init__(self, *, bad_quote=False, review_issue=False, check_issue=False, delay=0):
        self.bad_quote = bad_quote
        self.review_issue = review_issue
        self.check_issue = check_issue
        self.delay = delay
        self.requests = []
        self.lock = threading.Lock()

    def call(self, stage, payload):
        assert payload["protocol"] == "lamina-stage-1"
        assert payload["stage"] == stage
        with self.lock:
            self.requests.append((stage, payload))
        if self.delay:
            time.sleep(self.delay)
        data = payload["input"]
        if stage == "production_read":
            core = data["core"]
            return {
                "ideas": [
                    {
                        "title": unit["heading"],
                        "explanation": unit["text"].split(". ")[0],
                        "unit_ids": [unit["id"]],
                        "evidence": [
                            {
                                "unit_id": unit["id"],
                                "quote": (
                                    "invented"
                                    if self.bad_quote
                                    else unit["text"].split(". ")[0] + "."
                                ),
                            }
                        ],
                    }
                    for unit in core
                ]
            }
        if stage == "production_route":
            ideas = data["ideas"]
            return {
                "title": "Lease safety",
                "summary": "Expiry and fencing",
                "sections": [
                    {
                        "id": f"sec_{i}",
                        "title": idea["title"],
                        "purpose": "Explain the source fact",
                        "idea_ids": [idea["id"]],
                        "context_section_ids": [f"sec_{i-1}"] if i > 1 else [],
                        "representation": {
                            "kind": "mechanism" if i == 2 else "reference",
                            "rationale": "Show the source distinction clearly",
                            "requirements": ["Preserve exact condition"],
                        },
                    }
                    for i, idea in enumerate(ideas, 1)
                ],
                "omitted": [],
                "shared_context": [
                    {
                        "statement": "Expiry alone does not stop stale workers.",
                        "evidence": [ideas[1]["evidence"][0]],
                    }
                ],
            }
        if stage in {"production_write", "production_repair"}:
            sec = data["section"]
            quote = data["assigned_ideas"][0]["evidence"][0]
            body = f"{sec['title']}: {quote['quote']}"
            if "operator_revision_note" in data:
                body += " Revision: " + data["operator_revision_note"]
            if stage == "production_repair":
                body += " Repaired: " + data["findings"][0]["repair_instruction"]
            result = {
                "body": body,
                "used_idea_ids": sec["idea_ids"],
                "evidence": [quote],
            }
            if data["format"] == "assessment":
                result.pop("body")
                result.update(
                    {
                        "candidate_body": "What makes a stale write unsafe?",
                        "marking_body": body,
                    }
                )
            return result
        if stage == "production_review":
            if (
                self.review_issue
                and data["section"]["id"] == "sec_2"
                and "Repaired:" not in str(data["draft"])
            ):
                return {
                    "findings": [
                        {
                            "issue": "Needs qualification",
                            "repair_instruction": "State the exception",
                            "evidence": [data["assigned_ideas"][0]["evidence"][0]],
                        }
                    ]
                }
            return {"findings": []}
        if stage == "assessment_blind_solve":
            assert set(data) == {"current_candidate_body", "prior_candidate_bodies"}
            return {"answer": "Check the fencing token.", "uncertainties": []}
        if stage == "assessment_judge":
            if self.check_issue:
                return {"findings": [{"kind": "unanswerable", "issue": "The candidate prompt lacks the condition.",
                                      "repair_instruction": "Add the condition to the candidate prompt.",
                                      "evidence": [data["evidence"][0]]}]}
            return {"findings": []}
        raise AssertionError(stage)


def test_boundary_ownership_full_halo_and_parallelism(tmp_path):
    ws = workspace(tmp_path)
    class ConcurrentFixture(FixtureProvider):
        def __init__(self):
            super().__init__()
            self.barriers = {
                "production_read": threading.Barrier(4),
                "production_write": threading.Barrier(4),
            }

        def call(self, stage, payload):
            # Require real overlap rather than hoping a short sleep outlasts
            # SQLite setup and scheduling delays on a shared CI runner.
            if stage in self.barriers:
                self.barriers[stage].wait(timeout=15)
            return super().call(stage, payload)

    provider = ConcurrentFixture()
    receipt = build_production(
        ws,
        provider,
        "Explain lease safety",
        ["s1", "s2"],
        {
            "core_words": 100,
            "halo_units": 1,
            "reader_workers": 8,
            "writer_workers": 8,
            "review_workers": 8,
        },
    )
    plan = receipt["plan"]
    assert len(plan["windows"]) == 4
    assert plan["windows"][0]["after"][0]["text"].startswith("The old worker")
    assert len(plan["windows"][0]["after"][0]["text"]) > 450
    assert plan["windows"][1]["before"][0]["id"] == "u1"
    assert not plan["windows"][1]["after"]  # no cross-source halo
    assert plan["metrics"]["peak_provider_calls"]["production_read"] > 1
    assert receipt["metrics"]["peak_provider_calls"]["production_write"] > 1
    assert len(receipt["sections"]) == 4
    assert receipt["status"] == "ready"
    assert "fencing token" in receipt["markdown"]
    writer_inputs = [
        p["input"] for stage, p in provider.requests if stage == "production_write"
    ]
    assert all(len(x["shared_route"]) == 4 for x in writer_inputs)
    by_section = {x["section"]["id"]: x for x in writer_inputs}
    assert by_section["sec_2"]["earlier_evidence_units"][0]["id"] == "u1"
    assert by_section["sec_2"]["section"]["representation"]["kind"] == "mechanism"
    review_inputs = [
        p["input"] for stage, p in provider.requests if stage == "production_review"
    ]
    assert {x["section"]["representation"]["kind"] for x in review_inputs} == {
        "mechanism",
        "reference",
    }


def test_bad_quote_fails_and_assessment_source_never_reaches_provider(tmp_path):
    ws = workspace(tmp_path)
    ws.put_source(
        {
            "id": "secret",
            "title": "Held out",
            "filename": "secret.md",
            "sha256": "secret",
            "role": "assessment",
        }
    )
    ws.put_units(
        [
            {
                "id": "secret_unit",
                "source_id": "secret",
                "role": "assessment",
                "ordinal": 0,
                "heading": "Key",
                "locator": "line 1",
                "text": "Hidden key",
            }
        ]
    )
    provider = FixtureProvider(bad_quote=True)
    with pytest.raises(ProductionError, match="non-exact quote"):
        plan_production(ws, provider, "Explain", ["s1"], {"core_words": 100})
    with pytest.raises(ProductionError, match="not a teaching source"):
        plan_production(ws, provider, "Explain", ["secret"])
    assert "secret_unit" not in str(provider.requests)


def test_review_repairs_only_flagged_section_and_cache_reuse(tmp_path):
    ws = workspace(tmp_path)
    provider = FixtureProvider(review_issue=True)
    plan = plan_production(ws, provider, "Explain", ["s1", "s2"], {"core_words": 100})
    first = run_production(ws, provider, plan)
    assert first["status"] == "ready"
    assert list(first["initial_findings"]) == ["sec_2"]
    assert not first["findings"]
    assert sum(s == "production_repair" for s, _ in provider.requests) == 1
    count = len(provider.requests)
    repeat = run_production(ws, provider, plan)
    assert len(provider.requests) == count
    assert repeat["metrics"]["cache_misses"] == 0
    assert repeat["sections"] == first["sections"]


def test_targeted_revision_changes_one_writer_and_review(tmp_path):
    ws = workspace(tmp_path)
    provider = FixtureProvider()
    plan = plan_production(ws, provider, "Explain", ["s1", "s2"], {"core_words": 100})
    first = run_production(ws, provider, plan)
    before = len(provider.requests)
    revised = run_production(
        ws, provider, plan, {"section_notes": {"sec_3": "Add operator context"}}
    )
    new = provider.requests[before:]
    assert [(s, p["input"]["section"]["id"]) for s, p in new] == [
        ("production_write", "sec_3"),
        ("production_review", "sec_3"),
    ]
    assert first["sections"][0] == revised["sections"][0]
    assert first["sections"][2] != revised["sections"][2]
    assert "operator context" in revised["markdown"]
    with pytest.raises(ProductionError, match="unknown section"):
        run_production(ws, provider, plan, {"section_notes": {"nope": "bad"}})


def test_assessment_candidate_artifact_excludes_marking(tmp_path):
    ws = workspace(tmp_path)
    provider = FixtureProvider()
    receipt = build_production(
        ws,
        provider,
        "Create an assessment",
        ["s1"],
        {"format": "assessment", "core_words": 100},
    )
    assert receipt["candidate_markdown"] == receipt["markdown"]
    assert "What makes" in receipt["candidate_markdown"]
    assert "A lease expires" not in receipt["candidate_markdown"]
    assert "A lease expires" in receipt["examiner_markdown"]
    assert "marking_body" in receipt["sections"][0]
    assert receipt["assessment_checks"]["status"] == "passed"


def test_assessment_blind_finding_keeps_output_for_review(tmp_path):
    ws = workspace(tmp_path)
    provider = FixtureProvider(check_issue=True)
    receipt = build_production(ws, provider, "Create an assessment", ["s1"],
                               {"format": "assessment", "core_words": 100})
    assert receipt["status"] == "review"
    assert receipt["assessment_checks"]["status"] == "review"
    assert receipt["assessment_checks"]["checks"][0]["findings"][0]["kind"] == "unanswerable"
    assert "What makes" in receipt["candidate_markdown"]
    solves = [request["input"] for stage, request in provider.requests if stage == "assessment_blind_solve"]
    assert solves and all(set(row) == {"current_candidate_body", "prior_candidate_bodies"} for row in solves)
    assert all("marking_body" not in str(row) for row in solves)


def test_new_source_revision_reuses_unaffected_reader_windows(tmp_path):
    ws = workspace(tmp_path)
    provider = FixtureProvider()
    first = plan_production(ws, provider, "Explain", ["s1", "s2"], {"core_words": 100})
    assert first["metrics"]["cache_misses"] == 5  # four windows plus global route
    ws.put_source(
        {
            "id": "s2_new",
            "title": "Reliability revised",
            "filename": "s2-new.md",
            "sha256": "s2-new",
            "role": "teaching",
        }
    )
    for ordinal, (uid, text) in enumerate(
        (
            ("u3new", "A fencing token rejects stale writes. " * 14),
            ("u4new", "A retry uses the new token. " * 14),
        )
    ):
        ws.put_units(
            [
                {
                    "id": uid,
                    "source_id": "s2_new",
                    "role": "teaching",
                    "ordinal": ordinal,
                    "heading": uid,
                    "locator": f"line {ordinal + 1}",
                    "text": text,
                }
            ]
        )
    before = len(provider.requests)
    revised = plan_production(
        ws, provider, "Explain", ["s1", "s2_new"], {"core_words": 100}
    )
    new_reads = [
        p["input"]["source"]["id"]
        for stage, p in provider.requests[before:]
        if stage == "production_read"
    ]
    assert new_reads == ["s2_new", "s2_new"]
    assert revised["metrics"]["cache_hits"] == 2
    assert revised["metrics"]["cache_misses"] == 3
