"""Fictional sources test propagation/invalidation, not clinical or model quality."""

import copy
from dataclasses import replace

import pytest

from lamina.production import build_production
from lamina.production_contract import _read_check, ProductionError
from lamina.workload_profiles import WorkloadProfile
from test_production import FixtureProvider, workspace
from test_source_references import unit, idea


def test_visible_support_does_not_transfer_ownership():
    core = unit("a", "Drug A was stopped.")
    support = unit("b", "The reason was a rash.")
    raw = {
        "ideas": [
            idea(
                {"span_id": "a:s0"},
                evidence_refs=[{"span_id": "a:s0"}, {"span_id": "b:s0"}],
            )
        ]
    }
    row = _read_check(raw, [core], "w", [support])["ideas"][0]
    assert row["unit_ids"] == ["a"]
    assert row["support_unit_ids"] == ["b"]
    assert [e["unit_id"] for e in row["evidence"]] == ["a", "b"]
    with pytest.raises(ProductionError):
        _read_check({"ideas": [idea({"span_id": "b:s0"})]}, [core], "w", [support])
    with pytest.raises(ProductionError):
        _read_check(raw, [core], "w")  # unseen evidence is still forbidden
    raw["ideas"][0]["unit_ids"] = ["a", "b"]
    with pytest.raises(ProductionError):
        _read_check(raw, [core], "w", [support])


class SupportingReader(FixtureProvider):
    def budget_for(self, stage):
        base = super().budget_for(stage)
        if stage == "production_read":
            return replace(base, workload=WorkloadProfile(stage, max_items=1))
        return base

    def call(self, stage, payload):
        data = payload["input"]
        if stage == "production_read" and data["core"][0]["heading"] == "u1":
            self.requests.append((stage, copy.deepcopy(payload)))
            if not data["after"]:
                return {
                    "context_request": {
                        "direction": "after",
                        "reason": "Need the reason for the stop",
                    }
                }
            core, support = data["core"][0], data["after"][0]
            return {
                "ideas": [
                    {
                        "title": "Medication stop",
                        "explanation": "Stop with its documented reason.",
                        "evidence_refs": [
                            {"span_id": core["spans"][0]["id"]},
                            {"span_id": support["spans"][0]["id"]},
                        ],
                    }
                ]
            }
        if stage == "production_route":
            result = super().call(stage, payload)
            result["shared_context"] = []
            for sec in result["sections"]:
                sec["context_section_ids"] = []
                sec["candidate_context_ids"] = []
            return result
        if stage in ("production_write", "production_repair"):
            self.requests.append((stage, copy.deepcopy(payload)))
            evidence = data["assigned_ideas"][0]["evidence"]
            return {
                "body": " ".join(e["quote"] for e in evidence),
                "evidence": evidence,
                "used_idea_ids": data["section"]["idea_ids"],
            }
        return super().call(stage, payload)


def test_support_edit_invalidates_affected_output_and_reuses_unrelated_sections(
    tmp_path,
):
    ws, provider = workspace(tmp_path), SupportingReader()
    texts = [
        "Drug A was stopped in January.",
        "The reason was a rash.",
        "Drug A was restarted in April under monitoring.",
        "Unrelated equipment record.",
    ]
    rows = [
        {**u, "text": text, "content_id": "stable-" + u["id"]}
        for u, text in zip(ws.units("teaching"), texts)
    ]
    ws.import_sources(
        [(s, [u for u in rows if u["source_id"] == s["id"]]) for s in ws.sources()]
    )
    options = {"workflow": "planned"}
    first = build_production(ws, provider, "Explain the events", ["s1", "s2"], options)
    stopped = first["plan"]["ideas"][0]
    assert stopped["unit_ids"] == ["u1"]
    assert stopped["support_unit_ids"] == ["u2"]  # reader aliases restored
    assert texts[1] in first["sections"][0]["body"]
    assert {e["unit_id"] for e in first["sections"][0]["evidence"]} == {"u1", "u2"}
    assert texts[2] in first["markdown"]
    for stage, request in provider.requests:
        if (
            stage in ("production_write", "production_review")
            and request["input"]["section"]["id"] == "sec_1"
        ):
            assert request["input"]["assigned_ideas"][0]["support_unit_ids"] == [
                request["input"]["shared_evidence_units"][0]["id"]
            ]
            assert "rash" in str(request["input"]["shared_evidence_units"])
    rows = [
        {**u, "text": "The reason was hypotension."} if u["id"] == "u2" else u
        for u in ws.units("teaching")
    ]
    ws.import_sources(
        [(s, [u for u in rows if u["source_id"] == s["id"]]) for s in ws.sources()]
    )
    provider.requests.clear()
    second = build_production(ws, provider, "Explain the events", ["s1", "s2"], options)
    assert "hypotension" in second["sections"][0]["body"]
    assert "rash" not in second["sections"][0]["body"]
    assert {
        p["input"]["section"]["id"]
        for s, p in provider.requests
        if s == "production_write"
    } == {"sec_1", "sec_2"}
    assert second["sections"][2:] == first["sections"][2:]
