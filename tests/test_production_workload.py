"""Production must choose work limits before spending model calls."""

from dataclasses import replace

import pytest

from lamina.context_budget import RequestBudget
from lamina.production import (
    ProductionError,
    build_production,
    plan_production,
    run_production,
)
from lamina.workload_profiles import WorkloadProfile
from test_production import workspace
from test_source_workflows import SourceWriter


class Unprofiled(SourceWriter):
    def budget_for(self, stage):
        return RequestBudget(10_000_000)


@pytest.mark.parametrize("workflow", ["auto", "planned"])
def test_missing_workload_policy_fails_before_paid_calls(tmp_path, workflow):
    provider = Unprofiled()
    with pytest.raises(ProductionError, match="explicit workload profile"):
        plan_production(
            workspace(tmp_path),
            provider,
            "Explain",
            ["s1", "s2"],
            {"workflow": workflow},
        )
    assert provider.requests == []


def test_workload_limit_changes_auto_route_despite_large_transport(tmp_path):
    class Limited(SourceWriter):
        def budget_for(self, stage):
            budget = super().budget_for(stage)
            if stage in {"production_write", "production_review", "production_repair"}:
                return replace(budget, workload=WorkloadProfile(stage, max_items=2))
            return budget

    provider = Limited()
    result = build_production(
        workspace(tmp_path), provider, "Explain", ["s1", "s2"], {"workflow": "auto"}
    )
    decision = result["plan"]["workflow_decision"]
    assert decision["selected"] == "planned"
    assert decision["capacity"]["stages"]["production_write"]["workload_items"] == 4
    assert (
        decision["capacity"]["stages"]["production_write"]["request_bytes"] < 1_500_000
    )
    for stage, payload in provider.requests:
        if stage in {"production_write", "production_review", "production_repair"}:
            assert payload["workload_items"] <= 2
    assert result["quality"]["semantic_recall"] == "unmeasured"


def test_quality_metadata_cannot_be_relabelled_in_saved_plan(tmp_path):
    ws, provider = workspace(tmp_path), SourceWriter()
    plan = plan_production(ws, provider, "Explain", ["s1"], {"workflow": "direct"})
    plan["quality"]["semantic_recall"] = "certified"
    with pytest.raises(ProductionError, match="modified production plan"):
        run_production(ws, provider, plan)
    assert provider.requests == []


def test_context_units_cannot_bypass_unprofiled_writer_guard(tmp_path):
    from test_source_workflows import assignments

    ws, provider = workspace(tmp_path), Unprofiled()
    spec = assignments()
    spec["sections"] = [
        {**spec["sections"][0], "id": f"section-{index}", "unit_ids": [uid]}
        for index, uid in enumerate(("u1", "u2", "u3", "u4"))
    ]
    spec["sections"][0]["context_unit_ids"] = ["u2", "u3", "u4"]
    plan = plan_production(
        ws,
        provider,
        "Explain",
        ["s1", "s2"],
        {"workflow": "assigned", "assignments": spec},
    )
    with pytest.raises(ProductionError, match="explicit workload profile"):
        run_production(ws, provider, plan)
    assert provider.requests == []


def test_warm_receipt_retains_policy_without_reporting_provider_usage(tmp_path):
    ws, provider = workspace(tmp_path), SourceWriter()
    result = build_production(ws, provider, "Explain", ["s1"], {"workflow": "direct"})
    warm = run_production(ws, provider, result["plan"])
    for record in warm["metrics"]["requests"]:
        assert record["cache"] == "hit"
        assert record["attempts"] == []
        assert record["usage"] == {}
        assert record["workload_status"] == "configured"
        assert record["workload_profile"].startswith("workload:")
        assert record["workload_items"] == 2
        assert (
            record["max_workload_items"]
            == provider.budget_for(record["stage"]).workload.max_items
        )
        assert record["provider_request_bytes"] == 0
