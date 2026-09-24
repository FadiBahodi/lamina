"""Provider-reported quality metrics stay distinct from source-only counts."""

import json

import pytest

from lamina.context_budget import RequestBudget
from lamina.quality_evaluation import (
    Canary,
    ObservedProvider,
    _call_details,
    _draft_score,
)


def read_payload(text="alpha beta gamma delta"):
    return {
        "stage": "production_read",
        "revision": "test",
        "input": {
            "source": {"filename": "source.md"},
            "core": [{"id": "unit:1", "text": text}],
        },
    }


class MetricProvider:
    identity = "metric-provider"

    def __init__(self, *, fail=False, output_hook=True):
        self.fail = fail
        self.output_hook = output_hook
        self.usage = {}
        self.source_count_calls = 0

    def budget_for(self, _stage):
        return RequestBudget(
            20_000,
            context_tokens=1_000,
            output_tokens=100,
            count_tokens=lambda _request: 60,
            counting="test-framed-prompt-counter",
        )

    def output_limit_for(self, _stage):
        if not self.output_hook:
            return None
        return 50

    def source_token_count(self, text):
        self.source_count_calls += 1
        return len(text.split())

    def call(self, _stage, _payload):
        self.usage = {
            "input_tokens": 80,
            "output_tokens": 25,
            "total_tokens": 105,
        }
        if self.fail:
            raise RuntimeError("provider failed after reporting usage")
        return {"ideas": [{"id": "idea:1"}, {"id": "idea:2"}]}

    def last_usage(self):
        return dict(self.usage)


def test_read_metrics_separate_actual_prompt_usage_from_source_tokens_and_cache():
    provider = MetricProvider()
    observed = ObservedProvider(provider)

    observed.call("production_read", read_payload())
    observed.call("production_read", read_payload())

    assert provider.source_count_calls == 1
    details = _call_details(observed.records, [])
    assert details[0]["measurement"]["input_tokens"] == 60
    assert details[0]["measurement"]["counting"] == "test-framed-prompt-counter"
    assert details[0]["usage"] == {
        "input_tokens": 80,
        "output_tokens": 25,
        "total_tokens": 105,
    }
    assert details[0]["prompt_tokens"] == 80
    assert details[0]["source_tokens"] == 4
    assert details[0]["source_to_prompt_fraction"] == pytest.approx(0.05)
    assert details[0]["read_idea_count"] == 2
    assert details[0]["read_ideas_per_1000_source_tokens"] == 500
    assert details[0]["output_token_allowance"] == 50
    assert details[0]["output_token_fraction"] == 0.5


def test_failed_call_retains_elapsed_payload_usage_and_source_measurements(tmp_path):
    provider = MetricProvider(fail=True)
    journal = tmp_path / "calls.jsonl"
    observed = ObservedProvider(provider, journal)

    with pytest.raises(RuntimeError, match="provider failed"):
        observed.call("production_read", read_payload())

    record = observed.records[0]
    assert record["status"] == "failed"
    assert record["wall_ms"] >= 0
    assert record["measurement"]["input_tokens"] == 60
    assert record["usage"]["total_tokens"] == 105
    assert record["payload"]["input"]["core"][0]["text"].startswith("alpha")
    detail = _call_details(observed.records, [])[0]
    assert detail["prompt_tokens"] == 80
    assert detail["source_tokens"] == 4
    assert detail["source_characters"] == len("alpha beta gamma delta")
    assert detail["output_token_fraction"] == 0.5
    assert detail["read_idea_count"] is None
    assert detail["read_ideas_per_1000_source_tokens"] is None
    persisted = json.loads(journal.read_text().strip())
    assert persisted["status"] == "failed"
    assert persisted["usage"]["total_tokens"] == 105


def test_declared_budget_is_output_allowance_fallback_when_hook_has_no_limit():
    observed = ObservedProvider(MetricProvider(output_hook=False))

    observed.call("production_read", read_payload("one two"))

    detail = _call_details(observed.records, [])[0]
    assert detail["output_token_allowance"] == 100
    assert detail["output_token_fraction"] == 0.25


def test_call_journal_persists_raw_response_and_usage_before_final_report(tmp_path):
    journal = tmp_path / "trial" / "calls.jsonl"
    observed = ObservedProvider(MetricProvider(), journal)

    output = observed.call("production_read", read_payload())

    rows = [json.loads(line) for line in journal.read_text().splitlines()]
    assert len(rows) == 1
    assert rows[0]["status"] == "completed"
    assert rows[0]["payload"] == read_payload()
    assert rows[0]["output"] == output
    assert rows[0]["usage"]["total_tokens"] == 105


def test_nonreader_core_none_never_enters_source_reconstruction():
    provider = MetricProvider()
    observed = ObservedProvider(provider)
    payload = {
        "stage": "production_write",
        "revision": "test",
        "input": {"core": None},
    }

    observed.call("production_write", payload)

    detail = _call_details(observed.records, [])[0]
    assert detail["source_tokens"] is None
    assert detail["source_characters"] is None
    assert detail["canary_source_positions"] == {}
    assert provider.source_count_calls == 0


def test_initial_draft_score_materializes_raw_writer_markers():
    records = [
        {
            "stage": "production_write",
            "status": "completed",
            "payload": {
                "input": {
                    "section": {"id": "limits"},
                    "factual_sources": [{"id": "source:0", "filename": "current.md"}],
                    "assigned_units": [
                        {
                            "id": "unit:0",
                            "source_id": "source:0",
                            "addressed_text": "[s0]Rotor Nacre stops above 17 m/s.",
                        }
                    ],
                    "earlier_evidence_units": [],
                    "shared_evidence_units": [],
                }
            },
            "output": {"body_marked": "Rotor Nacre stops above 17 m/s. [s0]"},
        }
    ]
    canary = Canary(
        "threshold",
        "current.md",
        "Rotor Nacre",
        ("Rotor Nacre", "17 m/s"),
        (),
        "start",
        "quantity",
    )

    score = _draft_score(records, [canary])

    assert score["preserved"] == 1
