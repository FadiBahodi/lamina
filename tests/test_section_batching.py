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


def test_accepted_row_reaches_review_before_sibling_retry_returns(tmp_path):
    import threading

    reviewed = threading.Event()
    retry_started = threading.Event()

    class HeldRetry(BatchProvider):
        def call(self, stage, payload):
            data = payload["input"]
            if stage == "production_write" and "section_tasks" not in data:
                assert data["section"]["id"] == "sec_2"
                retry_started.set()
                assert reviewed.wait(3), "accepted sibling was held behind retry"
            if stage == "production_review":
                ids = [row["section_id"] for row in data.get("section_tasks", [])]
                if data.get("section", {}).get("id") == "sec_1" or "sec_1" in ids:
                    assert retry_started.wait(3), "retry did not share the pool"
                    reviewed.set()
            return super().call(stage, payload)

    provider = HeldRetry(corrupt=True)
    result = build_production(
        setup(tmp_path),
        provider,
        "Explain",
        ["s1", "s2"],
        {
            "workflow": "planned",
            "sections_per_request": 6,
            "workers": 4,
            "writer_workers": 2,
            "review_workers": 2,
        },
    )
    assert reviewed.is_set() and retry_started.is_set()
    assert len(result["sections"]) == 6
    assert result["metrics"]["provider_attempts"] == sum(
        stage in {"production_write", "production_review"}
        for stage, _ in provider.physical
    )


def test_failed_retry_keeps_reviewed_siblings_and_reuses_their_cache(tmp_path):
    import threading
    import pytest

    reviewed = threading.Event()

    class FailedRetry(BatchProvider):
        fail = True

        def call(self, stage, payload):
            data = payload["input"]
            if stage == "production_review":
                reviewed.set()
            if (
                self.fail
                and stage == "production_write"
                and "section_tasks" not in data
            ):
                assert reviewed.wait(3), "successful siblings did not progress"
                raise RuntimeError("retry unavailable")
            return super().call(stage, payload)

    ws, provider = setup(tmp_path), FailedRetry(corrupt=True)
    with pytest.raises(RuntimeError, match="retry unavailable") as failure:
        build_production(
            ws,
            provider,
            "Explain",
            ["s1", "s2"],
            {
                "workflow": "planned",
                "sections_per_request": 6,
                "workers": 4,
                "writer_workers": 2,
                "review_workers": 2,
            },
        )
    completed = failure.value.partial_results["completed_sections"]
    assert {row["id"] for row in completed} == {f"sec_{n}" for n in (1, 3, 4, 5, 6)}
    assert failure.value.partial_results["failed_sections"][0]["section_id"] == "sec_2"
    provider.fail = False
    provider.physical.clear()
    resumed = run_production(ws, provider, failure.value.partial_results["plan"])
    writes = [
        payload for stage, payload in provider.physical if stage == "production_write"
    ]
    assert len(writes) == 1
    assert writes[0]["input"]["section"]["id"] == "sec_2"
    assert resumed["status"] == "ready"
    assert resumed["metrics"]["cache_hits"] > 0


def test_budget_children_run_concurrently_in_the_shared_pool(tmp_path):
    from dataclasses import replace
    import threading
    from lamina.workload_profiles import WorkloadProfile

    rendezvous = threading.Barrier(2)
    lock = threading.Lock()
    entered = 0
    active = {"total": 0, "write": 0, "review": 0}
    peak = active.copy()

    class Split(BatchProvider):
        def budget_for(self, stage):
            budget = super().budget_for(stage)
            if stage in {"production_write", "production_review"}:
                return replace(budget, workload=WorkloadProfile(stage, max_items=2))
            return budget

        def call(self, stage, payload):
            nonlocal entered
            if stage not in {"production_write", "production_review"}:
                return super().call(stage, payload)
            lane = "write" if stage == "production_write" else "review"
            with lock:
                for key in ("total", lane):
                    active[key] += 1
                    peak[key] = max(peak[key], active[key])
                paired = stage == "production_write" and entered < 2
                if stage == "production_write":
                    entered += 1
            try:
                if paired:
                    rendezvous.wait(timeout=3)  # Serial child recursion fails.
                return super().call(stage, payload)
            finally:
                with lock:
                    for key in ("total", lane):
                        active[key] -= 1

    provider = Split()
    result = build_production(
        setup(tmp_path),
        provider,
        "Explain",
        ["s1", "s2"],
        {
            "workflow": "planned",
            "sections_per_request": 6,
            "workers": 3,
            "writer_workers": 2,
            "review_workers": 1,
        },
    )
    assert len(result["sections"]) == 6
    assert peak["write"] == 2 and peak["review"] <= 1 and peak["total"] <= 3
    assert all(
        payload["workload_items"] <= 2
        for stage, payload in provider.physical
        if stage in {"production_write", "production_review"}
    )


def test_cached_rows_are_released_before_uncached_revision(tmp_path):
    import threading

    available = threading.Event()

    class Revision(BatchProvider):
        holding = False

        def call(self, stage, payload):
            if self.holding and stage == "production_write":
                assert payload["input"]["section"]["id"] == "sec_2"
                assert available.wait(3), "cached section waited for revised sibling"
            return super().call(stage, payload)

    ws, provider = setup(tmp_path), Revision()
    first = build_production(
        ws,
        provider,
        "Explain",
        ["s1", "s2"],
        {"workflow": "planned", "sections_per_request": 6, "workers": 4},
    )
    provider.holding = True
    provider.physical.clear()

    def progress(event):
        if event.get("stage") == "production_section" and event.get("item") == "sec_1":
            available.set()

    second = run_production(
        ws,
        provider,
        first["plan"],
        {"section_notes": {"sec_2": "Explain more clearly"}},
        progress=progress,
    )
    assert available.is_set()
    assert second["status"] == "ready"
    assert len([s for s, _ in provider.physical if s == "production_write"]) == 1


def test_truncated_group_schedules_individual_children_without_nested_pool(tmp_path):
    import threading

    rendezvous = threading.Barrier(2)
    lock = threading.Lock()
    entered = 0

    class Truncated(RuntimeError):
        code = "output_truncated"

    class SplitTruncated(BatchProvider):
        def call(self, stage, payload):
            nonlocal entered
            if stage == "production_write":
                if "section_tasks" in payload["input"]:
                    raise Truncated("group too long")
                with lock:
                    paired = entered < 2
                    entered += 1
                if paired:
                    rendezvous.wait(timeout=3)
            return super().call(stage, payload)

    result = build_production(
        setup(tmp_path),
        SplitTruncated(),
        "Explain",
        ["s1", "s2"],
        {
            "workflow": "planned",
            "sections_per_request": 6,
            "workers": 3,
            "writer_workers": 2,
            "review_workers": 1,
            "max_attempts": 1,
        },
    )
    assert len(result["sections"]) == 6
    assert result["metrics"]["failed_requests"] == 1
