"""The measurement must preserve the task and count unsuccessful attempts."""

import argparse
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "execution_comparison", Path(__file__).parents[1] / "benchmarks/compare_execution.py"
)
comparison = importlib.util.module_from_spec(spec)
spec.loader.exec_module(comparison)


def options(tmp_path, **updates):
    return argparse.Namespace(**{
        "provider": "fixture", "model": None, "corpus": None,
        "output": tmp_path / "measurement", "replicates": 2, "workers": 4,
        "concurrency": 4, "group_size": 6, "max_calls": 100, **updates,
    })


def test_matched_comparison_keeps_outputs_and_uses_fresh_workspaces(tmp_path):
    report = comparison.run(options(tmp_path))
    for replicate in (1, 2):
        rows = {row["arm"]: row for row in report["trials"] if row["replicate"] == replicate}
        assert all(row["status"] == "ready" and row["passed_checks"] for row in rows.values())
        assert rows["planned"]["output_sha256"] == rows["grouped"]["output_sha256"]
        assert rows["planned"]["sections"] == rows["grouped"]["sections"] == 6
        assert rows["planned"]["calls"]["production_write"] == 6
        assert rows["grouped"]["calls"]["production_write"] == 1
        assert rows["grouped"]["calls"]["production_review"] == 1
        assert rows["direct"]["calls"] == {"production_write": 1, "production_review": 1}
        assert rows["planned"]["planning_ms"] == rows["grouped"]["planning_ms"]
        assert all(row["usage"] == {} for row in rows.values())


def test_failed_arm_is_retained_and_does_not_cancel_other_arms(tmp_path, monkeypatch):
    original = comparison.FixtureProvider.call

    def fail(self, stage, payload):
        if stage == "production_write" and payload["input"].get("section", {}).get("id") == "section_0" and payload.get("protocol"):
            raise RuntimeError("Injected single-section writer failure")
        return original(self, stage, payload)

    monkeypatch.setattr(comparison.FixtureProvider, "call", fail)
    report = comparison.run(options(tmp_path, replicates=1))
    rows = {row["arm"]: row for row in report["trials"]}
    assert rows["planned"]["status"] == "failed"
    assert rows["grouped"]["status"] == rows["direct"]["status"] == "ready"
    assert report["summary"]["planned"]["failed"] == 1
    assert rows["planned"]["calls"]["production_write"] > 0


def test_live_preflight_requires_credentials_before_creating_results(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    args = options(tmp_path, provider="gemini", model="example-model")
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        comparison.run(args)
    assert not args.output.exists()
