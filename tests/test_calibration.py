import hashlib
import json
from datetime import datetime, timezone, timedelta

import pytest

from lamina.calibration import (
    ExperimentalProvider,
    calibrate,
    promote_profiles,
    quality_status,
    read_corpus,
    starter_workloads,
)
from lamina.context_budget import RequestBudget
from lamina.production_contract import REVISION
from lamina.workload_profiles import WorkloadProfile


def observation(stage="production_read", limit=12, replicate=1, passed=True):
    score = {
        "fraction": 1.0 if passed else 0,
        "counterfacts": 0,
        "by_position": {"middle": {"preserved": int(passed), "total": 1}},
    }
    return {
        "status": "completed",
        "engine_status": "ready",
        "provider_identity": "test",
        "protocol_revision": REVISION,
        "experimental_stage": stage,
        "experimental_limit": limit,
        "replicate": replicate,
        "experimental_dimension": "max_items",
        "corpus_sha256": "f" * 64,
        "evaluation_sha256": "a" * 64,
        "reading": "task",
        "load": 30,
        "extraction": score,
        "assignment": score,
        "finished_output": score,
        "stage_budgets": {
            stage: {"configuration_identity": "test", "workload": {"max_items": limit}}
        },
        "calls": [{"stage": stage, "status": "completed"}],
    }


def report(trials):
    return {
        "evaluation": "configured-provider-observations",
        "protocol_revision": REVISION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "stage": "production_read",
        "promotion_policy": "all-declared-checks-two-replicates-v1",
        "dimension": "max_items",
        "limits": [12, 24],
        "replicates_required": 2,
        "trials": trials,
        "summary": {
            "criteria": {
                "minimum_fraction_per_stage_and_position": 1.0,
                "maximum_counterfacts_per_stage": 0,
                "required_stages": ["extraction", "assignment", "finished_output"],
            }
        },
    }


def test_promotion_requires_every_replicate_and_preserves_tested_limit(tmp_path):
    path = tmp_path / "report.json"
    trials = [
        observation(replicate=1),
        observation(replicate=2),
        observation(limit=24, replicate=1),
        observation(limit=24, replicate=2, passed=False),
    ]
    path.write_text(json.dumps(report(trials)))
    profile = promote_profiles(path)["production_read"]
    assert profile["max_items"] == 12
    assert profile["basis"] == "observed"
    assert len(profile["evidence"]["report_sha256"]) == 64
    trials.pop(1)
    path.write_text(json.dumps(report(trials)))
    assert promote_profiles(path) == {}


def test_promotion_rejects_scripted_report_and_mismatched_workload(tmp_path):
    path = tmp_path / "report.json"
    data = report([observation(), observation(replicate=2)])
    data["trials"][1]["stage_budgets"]["production_read"]["workload"]["max_items"] = 99
    path.write_text(json.dumps(data))
    assert promote_profiles(path) == {}
    data["evaluation"] = "scripted-adversarial-contract"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="observations"):
        promote_profiles(path)


def test_promotion_rejects_replicates_from_different_corpora(tmp_path):
    path = tmp_path / "report.json"
    trials = [observation(replicate=1), observation(replicate=2)]
    trials[1]["corpus_sha256"] = "e" * 64
    path.write_text(json.dumps(report(trials)))

    assert promote_profiles(path) == {}


def test_promotion_rejects_missing_or_different_evaluation_identity(tmp_path):
    path = tmp_path / "report.json"
    trials = [observation(replicate=1), observation(replicate=2)]
    trials[1]["evaluation_sha256"] = "b" * 64
    path.write_text(json.dumps(report(trials)))
    assert promote_profiles(path) == {}
    trials[1].pop("evaluation_sha256")
    path.write_text(json.dumps(report(trials)))
    assert promote_profiles(path) == {}


def test_promotion_rejects_trial_for_another_experimental_dimension(tmp_path):
    path = tmp_path / "report.json"
    trials = [observation(replicate=1), observation(replicate=2)]
    trials[1]["experimental_dimension"] = "max_input_tokens"
    path.write_text(json.dumps(report(trials)))

    assert promote_profiles(path) == {}


def test_observed_profile_requires_exact_limits_from_recorded_budget(tmp_path):
    path = tmp_path / "report.json"
    data = report([observation()])
    workload = data["trials"][0]["stage_budgets"]["production_read"]["workload"]
    workload["max_input_tokens"] = 500
    path.write_text(json.dumps(data))
    evidence = {
        "provider_identity": "test",
        "protocol_revision": REVISION,
        "report_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "report_path": str(path),
    }

    profile = WorkloadProfile(
        "production_read",
        max_items=12,
        max_input_tokens=500,
        basis="observed",
        evidence=evidence,
    )
    assert profile.max_items == 12
    assert profile.max_input_tokens == 500
    with pytest.raises(ValueError, match="stage and limit"):
        WorkloadProfile(
            "production_read",
            max_items=24,
            max_input_tokens=500,
            basis="observed",
            evidence=evidence,
        )
    with pytest.raises(ValueError, match="stage and limit"):
        WorkloadProfile(
            "production_read",
            max_items=12,
            basis="observed",
            evidence=evidence,
        )


class Provider:
    identity = configuration_identity = "test"

    def budget_for(self, stage):
        return RequestBudget(100000, workload=WorkloadProfile(stage, max_items=12))


def test_qc_reports_failure_and_age_without_changing_workload(tmp_path):
    path = tmp_path / "qc.json"
    data = report(
        [observation(replicate=1, passed=False), observation(replicate=2, passed=False)]
    )
    data["created_at"] = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    path.write_text(json.dumps(data))
    provider = Provider()
    provider.qc_report = path
    status = quality_status(provider, ["production_read"])["production_read"]
    assert status["qc_status"] == "failed"
    assert status["stale"] is True
    data["trials"][0]["stage_budgets"]["production_read"]["configuration_identity"] = (
        "different"
    )
    path.write_text(json.dumps(data))
    assert (
        quality_status(provider, ["production_read"])["production_read"]["qc_status"]
        == "configuration_mismatch"
    )


def test_qc_requires_the_measured_stage_and_complete_strict_replicates(tmp_path):
    path = tmp_path / "qc.json"
    provider = Provider()
    provider.qc_report = path
    data = report([observation(replicate=1), observation(replicate=2)])
    path.write_text(json.dumps(data))
    assert quality_status(provider, ["production_read"])["production_read"][
        "qc_status"
    ] == "passed"

    other_stage = quality_status(provider, ["production_write"])["production_write"]
    assert other_stage["qc_status"] == "unmeasured_stage"

    data["trials"].pop()
    path.write_text(json.dumps(data))
    assert quality_status(provider, ["production_read"])["production_read"][
        "qc_status"
    ] == "insufficient_replicates"

    data = report([observation(replicate=1), observation(replicate=2)])
    data["summary"]["criteria"]["minimum_fraction_per_stage_and_position"] = 0.5
    path.write_text(json.dumps(data))
    assert quality_status(provider, ["production_read"])["production_read"][
        "qc_status"
    ] == "ineligible_policy"


def test_qc_rejects_mixed_evaluation_identity(tmp_path):
    path = tmp_path / "qc.json"
    trials = [observation(replicate=1), observation(replicate=2)]
    trials[1]["evaluation_sha256"] = "b" * 64
    path.write_text(json.dumps(report(trials)))
    provider = Provider()
    provider.qc_report = path
    assert quality_status(provider, ["production_read"])["production_read"][
        "qc_status"
    ] == "evaluation_mismatch"


def test_experiment_changes_one_guard_only():
    provider = Provider()
    experiment = ExperimentalProvider(provider, "production_read", 24)
    assert experiment.budget_for("production_read").workload.max_items == 24
    assert experiment.budget_for("production_write").workload.max_items == 12
    assert experiment.identity_for("production_read") != provider.identity
    assert (
        starter_workloads()["production_write"]["max_items"]
        < starter_workloads()["production_route"]["max_items"]
    )


def test_corpus_rejects_missing_source_and_preserves_private_path(tmp_path):
    path = tmp_path / "corpus.json"
    data = {
        "sources": ["private.md"],
        "brief": "Read carefully",
        "canaries": [
            {
                "id": "x",
                "source": "private.md",
                "subject": "Engine",
                "required": ["only"],
                "position": "middle",
                "kind": "condition",
            }
        ],
    }
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="missing"):
        read_corpus(path)
    (tmp_path / "private.md").write_text("Engine runs only when permitted.")
    paths, canaries, brief = read_corpus(path)
    assert paths == [tmp_path / "private.md"]
    assert canaries[0].required == ("only",)
