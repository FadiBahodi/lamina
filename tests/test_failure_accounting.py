"""A failed run must retain the work completed after its first error."""

import threading

import pytest

from lamina.production import plan_production, run_production
from test_source_workflows import SourceWriter, assignments, workspace


def test_failed_section_reports_settled_sibling_work(tmp_path):
    sibling_started, failure_recorded = threading.Event(), threading.Event()

    class Provider(SourceWriter):
        def call(self, stage, payload):
            if stage == "production_write":
                if payload["input"]["section"]["id"] == "expiry":
                    assert sibling_started.wait(5)
                    raise RuntimeError("intentional unavailable section")
                sibling_started.set()
                assert failure_recorded.wait(5)
            if stage == "production_review":
                return {"findings": []}
            return super().call(stage, payload)

    ws, provider = workspace(tmp_path), Provider()
    plan = plan_production(
        ws,
        provider,
        "Explain",
        ["s1", "s2"],
        {"workflow": "assigned", "assignments": assignments(), "workers": 2},
    )

    def progress(event):
        if event["item"] == "expiry" and event["status"] == "failed":
            failure_recorded.set()

    with pytest.raises(RuntimeError, match="intentional") as failure:
        run_production(ws, provider, plan, progress=progress)
    assert failure.value.metrics["provider_attempts"] == 3
    assert failure.value.metrics["failed_requests"] == 1
    assert [
        row["id"] for row in failure.value.partial_results["completed_sections"]
    ] == ["writes"]
    assert failure.value.partial_results["failed_sections"][0]["section_id"] == "expiry"


def test_assessment_failure_retains_finished_writing_and_both_phase_metrics(tmp_path):
    from lamina.production import build_production

    class Provider(SourceWriter):
        def call(self, stage, payload):
            if stage == "assessment_blind_solve":
                raise RuntimeError("intentional solve failure")
            return super().call(stage, payload)

    with pytest.raises(RuntimeError, match="solve failure") as failure:
        build_production(
            workspace(tmp_path),
            Provider(),
            "Ask a question",
            ["s1"],
            {"workflow": "direct", "format": "assessment"},
        )
    partial = failure.value.partial_results
    assert partial["plan"]["metrics"]["provider_attempts"] == 0
    receipt = partial["production_receipt"]
    assert receipt["status"] == "review"
    assert receipt["sections"][0]["marking_body"]
    assert receipt["metrics"]["provider_attempts"] == 2
    assert receipt["assessment_checks"]["metrics"]["provider_attempts"] == 1
