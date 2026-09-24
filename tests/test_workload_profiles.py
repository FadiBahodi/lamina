"""Task limits cannot be replaced by a large context or transport allowance."""

import json
import hashlib
import sys

import pytest

from lamina.chat_protocol import chat_messages, chat_token_count
from lamina.context_budget import ContextBudgetError, RequestBudget, pack_units
from lamina.providers import CommandProvider, StageProvider, configured_provider
from lamina.workload_profiles import WorkloadProfile, with_workload


def request(units):
    return with_workload(
        {
            "protocol": "lamina-stage-1",
            "revision": "test-protocol",
            "stage": "production_read",
            "instruction": "Preserve source qualifications.",
            "expected_shape": {"ideas": []},
            "input": {"core": units},
        },
        len(units),
    )


def test_large_context_does_not_override_stage_workload_limit():
    units = [{"id": str(i), "source_id": "s", "text": "One fact."} for i in range(9)]
    budget = RequestBudget(
        1_000_000,
        context_tokens=1_000_000,
        output_tokens=1000,
        count_tokens=lambda envelope: len(json.dumps(envelope)),
        workload=WorkloadProfile("production_read", max_items=2),
    )
    batches = pack_units(units, request, budget)
    assert [len(batch.units) for batch in batches] == [2, 2, 2, 2, 1]
    assert [u for batch in batches for u in batch.units] == units
    assert all(batch.measurement.workload_status == "configured" for batch in batches)
    with pytest.raises(ContextBudgetError, match="9 > 2 items"):
        budget.check(request(units))


def test_item_limits_require_an_explicit_count_and_never_guess_input_shape():
    budget = RequestBudget(
        1_000_000, workload=WorkloadProfile("production_read", max_items=2)
    )
    payload = request([])
    del payload["workload_items"]
    assert not budget.fits(payload)
    with pytest.raises(
        ContextBudgetError, match="requires a workload_items annotation"
    ):
        budget.check(payload)
    payload["workload_items"] = True
    with pytest.raises(ValueError, match="nonnegative integer"):
        budget.measure(payload)


def test_workload_annotation_does_not_enter_model_prompt():
    first = request([])
    second = with_workload(first, 100)
    assert chat_messages(first) == chat_messages(second)
    assert (
        RequestBudget(1_000_000).measure(first).request_bytes
        < RequestBudget(1_000_000).measure(second).request_bytes
    )


def test_workload_tokens_count_prompt_overhead_and_feedback():
    tiktoken = pytest.importorskip("tiktoken")
    encoding = tiktoken.get_encoding("cl100k_base")
    counter = lambda value: chat_token_count(value, encoding)
    payload = request([])
    tokens = counter(payload)
    budget = RequestBudget(
        1_000_000,
        count_tokens=counter,
        workload=WorkloadProfile("production_read", max_input_tokens=tokens),
    )
    assert budget.check(payload).input_tokens == tokens
    assert not budget.fits(
        {
            **payload,
            "validation_feedback": {"errors": "Retain this exact qualification."},
        }
    )
    with pytest.raises(ContextBudgetError, match="rendered input tokens"):
        budget.check(
            {
                **payload,
                "validation_feedback": {"errors": "Retain this exact qualification."},
            }
        )
    with pytest.raises(ValueError, match="requires an adapter token counter"):
        RequestBudget(
            1_000_000, workload=WorkloadProfile("production_read", max_input_tokens=10)
        )


def test_profile_is_stage_specific_and_unprofiled_is_unassessed():
    provider = CommandProvider(
        [sys.executable], workload={"production_read": {"max_items": 2}}
    )
    assert provider.budget_for("production_read").workload.max_items == 2
    assert provider.budget_for("production_write").workload is None
    assert (
        provider.budget_for("production_write").measure({}).workload_status
        == "unassessed"
    )
    with pytest.raises(ValueError, match="another stage"):
        provider.budget_for("production_read").measure({"stage": "production_write"})


def test_chat_workload_tokens_can_be_limited_without_declaring_context_capacity(
    monkeypatch,
):
    pytest.importorskip("tiktoken")
    monkeypatch.delenv("LAMINA_CONTEXT_TOKENS", raising=False)
    provider = CommandProvider(
        [sys.executable],
        request_format="lamina-chat-1",
        env={"LAMINA_TOKENIZER": "cl100k_base"},
        workload={"production_read": {"max_input_tokens": 1000}},
    )
    budget = provider.budget_for("production_read")
    assert budget.context_tokens is None
    assert budget.check(request([])).input_tokens > 0
    unknown = CommandProvider(
        [sys.executable], workload={"production_read": {"max_input_tokens": 1000}}
    )
    with pytest.raises(ValueError, match="requires an adapter token counter"):
        unknown.budget_for("production_read")


def test_configured_wildcard_is_explicit_and_named_override_is_complete(tmp_path):
    path = tmp_path / "models.json"
    path.write_text(
        json.dumps(
            {
                "default": {
                    "command": [sys.executable],
                    "workload": {
                        "*": {"max_items": 10},
                        "production_read": {"max_items": 2},
                    },
                }
            }
        )
    )
    provider = configured_provider(path)
    assert provider.budget_for("production_read").workload == WorkloadProfile(
        "production_read", max_items=2
    )
    assert provider.budget_for("production_route").workload == WorkloadProfile(
        "production_route", max_items=10
    )
    assert provider.budget_for("production_route").workload.basis == "configured"


def test_workload_changes_cache_identity_without_changing_evaluation_binding():
    first = CommandProvider([sys.executable], workload={"*": {"max_items": 2}})
    second = CommandProvider([sys.executable], workload={"*": {"max_items": 3}})
    assert first.identity != second.identity
    assert first.configuration_identity == second.configuration_identity
    selected = StageProvider(first, {"production_read": second})
    assert (
        selected.configuration_identity_for("production_read")
        == second.configuration_identity
    )


def test_stage_workload_change_reuses_other_stage_cache_identity():
    old = CommandProvider(
        [sys.executable],
        workload={
            "production_read": {"max_items": 2},
            "production_write": {"max_items": 4},
        },
    )
    new = CommandProvider(
        [sys.executable],
        workload={
            "production_read": {"max_items": 3},
            "production_write": {"max_items": 4},
        },
    )
    assert old.identity != new.identity
    assert old.identity_for("production_read") != new.identity_for("production_read")
    assert old.identity_for("production_write") == new.identity_for("production_write")
    assert old.identity_for("production_review") == new.identity_for(
        "production_review"
    )
    assert StageProvider(old, {}).identity_for("production_write") == StageProvider(
        new, {}
    ).identity_for("production_write")


@pytest.mark.parametrize(
    "row",
    [
        {},
        {"max_items": 0},
        {"max_items": True},
        {"max_input_tokens": -1},
        {"max_items": 2, "basis": "certified"},
        {"max_items": 2, "basis": "observed"},
    ],
)
def test_malformed_profiles_are_rejected(row):
    with pytest.raises(ValueError):
        WorkloadProfile("production_read", **row)


def test_observed_profile_binds_provider_protocol_and_report(tmp_path):
    provider = CommandProvider([sys.executable])
    report = tmp_path / "observations.json"
    report.write_text(
        json.dumps(
            {
                "evaluation": "configured-provider-observations",
                "protocol_revision": "test-protocol",
                "trials": [
                    {
                        "experimental_stage": "production_read",
                        "status": "completed",
                        "protocol_revision": "test-protocol",
                        "calls": [{"stage": "production_read", "status": "completed"}],
                        "stage_budgets": {
                            "production_read": {
                                "configuration_identity": provider.configuration_identity,
                                "workload": {
                                    "max_items": 2,
                                    "max_input_tokens": None,
                                },
                            }
                        },
                    }
                ],
            }
        )
    )
    evidence = {
        "provider_identity": provider.configuration_identity,
        "protocol_revision": "test-protocol",
        "report_sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
        "report_path": str(report),
    }
    profile = WorkloadProfile(
        "production_read", max_items=2, basis="observed", evidence=evidence
    )
    configured = CommandProvider(
        [sys.executable], workload={"production_read": profile}
    )
    assert (
        configured.budget_for("production_read").check(request([])).workload_status
        == "observed"
    )
    with pytest.raises(ValueError, match="another request protocol"):
        configured.budget_for("production_read").check(
            {**request([]), "revision": "changed"}
        )
    with pytest.raises(ValueError, match="another provider"):
        CommandProvider(
            [sys.executable, "changed"], workload={"production_read": profile}
        )
    with pytest.raises(ValueError, match="wildcard"):
        WorkloadProfile("*", max_items=2, basis="observed", evidence=evidence)
    report.write_text("{}")
    with pytest.raises(ValueError, match="digest"):
        WorkloadProfile(
            "production_read", max_items=2, basis="observed", evidence=evidence
        )


@pytest.mark.parametrize("identity_kind", ["stage", "configuration", "provider"])
def test_custom_provider_observed_profile_binding_is_checked_at_both_runtime_boundaries(
    tmp_path, identity_kind
):
    from lamina.call_runtime import request_budget as runtime_budget
    from lamina.source_reading import request_budget as reader_budget

    identity = "custom:evaluated-model"
    stage = "production_read"
    report = tmp_path / "custom-observation.json"
    report.write_text(
        json.dumps(
            {
                "evaluation": "configured-provider-observations",
                "protocol_revision": "test-protocol",
                "trials": [
                    {
                        "status": "completed",
                        "protocol_revision": "test-protocol",
                        "experimental_stage": stage,
                        "calls": [{"stage": stage, "status": "completed"}],
                        "stage_budgets": {
                            stage: {
                                "configuration_identity": identity,
                                "workload": {
                                    "max_items": 2,
                                    "max_input_tokens": None,
                                },
                            }
                        },
                    }
                ],
            }
        )
    )
    profile = WorkloadProfile(
        stage,
        max_items=2,
        basis="observed",
        evidence={
            "provider_identity": identity,
            "protocol_revision": "test-protocol",
            "report_sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
            "report_path": str(report),
        },
    )

    class CustomProvider:
        def budget_for(self, _stage):
            return RequestBudget(9000, workload=profile)

    provider = CustomProvider()

    def set_identity(value):
        if identity_kind == "stage":
            provider.identity = "aggregate:unrelated"
            provider.configuration_identity = "fallback:unrelated"
            provider.configuration_identity_for = lambda stage: value
        elif identity_kind == "configuration":
            provider.identity = "aggregate:unrelated"
            provider.configuration_identity = value
        else:
            provider.identity = value

    for loader in (
        lambda: runtime_budget(provider, stage, 8000),
        lambda: reader_budget(
            provider, stage, {"max_request_bytes": 8500, "max_input_bytes": 8000}
        ),
    ):
        set_identity("custom:unevaluated-model")
        with pytest.raises(ValueError, match="another provider configuration"):
            loader()
        set_identity(identity)
        budget = loader()
        assert budget.max_request_bytes == 8000
        assert budget.check(request([])).workload_status == "observed"
