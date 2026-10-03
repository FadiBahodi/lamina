"""Deterministic equal-output transport comparisons, not quality benchmarks."""

import copy

from lamina.production import build_production, run_production
from test_production import FixtureProvider, workspace


class BatchProvider(FixtureProvider):
    def __init__(self, *, corrupt=False, review_issue=False):
        super().__init__(review_issue=review_issue)
        self.physical = []
        self.corrupt = corrupt

    def call(self, stage, payload):
        self.physical.append((stage, copy.deepcopy(payload)))
        if "section_tasks" not in payload["input"]:
            return super().call(stage, payload)
        rows = []
        for task in payload["input"]["section_tasks"]:
            raw = super().call(stage, {**payload, "input": task["input"]})
            if (
                self.corrupt
                and stage == "production_write"
                and task["section_id"] == "sec_2"
            ):
                raw["used_idea_ids"] = ["nonexistent"]
            rows.append({"section_id": task["section_id"], "result": raw})
        return {"sections": rows}


def setup(tmp_path):
    ws = workspace(tmp_path)
    ws.put_units(
        [
            {
                "id": f"u{n}",
                "source_id": "s2",
                "role": "teaching",
                "ordinal": n,
                "heading": f"u{n}",
                "locator": f"line {n}",
                "text": f"Additional condition {n}.",
            }
            for n in (5, 6)
        ]
    )
    return ws


def test_six_sections_use_two_physical_calls_with_identical_outputs(tmp_path):
    normal, grouped = BatchProvider(), BatchProvider()
    ws = setup(tmp_path / "normal")
    first = build_production(
        ws, normal, "Explain", ["s1", "s2"], {"workflow": "planned"}
    )
    other = setup(tmp_path / "grouped")
    second = build_production(
        other,
        grouped,
        "Explain",
        ["s1", "s2"],
        {"workflow": "planned", "sections_per_request": 6},
    )
    assert first["sections"] == second["sections"]
    assert first["markdown"] == second["markdown"]
    assert len(second["sections"]) == 6
    assert [s for s, _ in normal.physical].count("production_write") == 6
    assert [s for s, _ in normal.physical].count("production_review") == 6
    assert [s for s, _ in grouped.physical].count("production_write") == 1
    assert [s for s, _ in grouped.physical].count("production_review") == 1
    assert second["metrics"]["provider_attempts"] == 2
    grouped.physical.clear()
    run_production(
        other,
        grouped,
        second["plan"],
        {"section_notes": {"sec_3": "Explain the boundary"}},
    )
    writes = [p for s, p in grouped.physical if s == "production_write"]
    assert len(writes) == 1
    assert writes[0]["input"]["section"]["id"] == "sec_3"


def test_invalid_row_retries_only_its_section_and_retains_siblings(tmp_path):
    provider = BatchProvider(corrupt=True)
    result = build_production(
        setup(tmp_path),
        provider,
        "Explain",
        ["s1", "s2"],
        {"workflow": "planned", "sections_per_request": 6},
    )
    assert result["status"] == "ready"
    writes = [p for s, p in provider.physical if s == "production_write"]
    assert len(writes) == 2
    assert writes[1]["input"]["section"]["id"] == "sec_2"
    assert len(result["sections"]) == 6


def test_batched_review_retains_individual_repair_and_recheck(tmp_path):
    provider = BatchProvider(review_issue=True)
    result = build_production(
        setup(tmp_path),
        provider,
        "Explain",
        ["s1", "s2"],
        {"workflow": "planned", "sections_per_request": 6},
    )
    assert result["status"] == "ready"
    assert set(result["initial_findings"]) == {"sec_2"}
    repairs = [p for s, p in provider.physical if s == "production_repair"]
    assert len(repairs) == 1
    assert repairs[0]["input"]["section"]["id"] == "sec_2"


def test_grouping_respects_stage_workload_by_splitting(tmp_path):
    from dataclasses import replace
    from lamina.workload_profiles import WorkloadProfile

    class Limited(BatchProvider):
        def budget_for(self, stage):
            budget = super().budget_for(stage)
            if stage in {"production_write", "production_review"}:
                return replace(budget, workload=WorkloadProfile(stage, max_items=2))
            return budget

    provider = Limited()
    result = build_production(
        setup(tmp_path),
        provider,
        "Explain",
        ["s1", "s2"],
        {"workflow": "planned", "sections_per_request": 6},
    )
    assert len(result["sections"]) == 6
    assert all(
        p["workload_items"] <= 2
        for s, p in provider.physical
        if s in {"production_write", "production_review"}
    )


def test_grouped_review_capacity_failure_stays_explicitly_unreviewed(tmp_path):
    from dataclasses import replace

    class NoDraftRoom(BatchProvider):
        def budget_for(self, stage):
            budget = super().budget_for(stage)
            if stage == "production_review":

                def count(payload):
                    return (
                        1000
                        if payload["input"].get("draft")
                        or "section_tasks" in payload["input"]
                        else 1
                    )

                return replace(
                    budget, context_tokens=100, output_tokens=10, count_tokens=count
                )
            return budget

    result = build_production(
        setup(tmp_path),
        NoDraftRoom(),
        "Explain",
        ["s1", "s2"],
        {"workflow": "planned", "sections_per_request": 6},
    )
    assert result["status"] == "review"
    assert len(result["sections"]) == 6
    assert all(
        rows[0]["verification_unperformed"] for rows in result["findings"].values()
    )
