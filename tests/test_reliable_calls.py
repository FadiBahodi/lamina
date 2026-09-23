"""Reliability fixtures exercise errors and receipts; they do not score models."""

import copy

import pytest

from lamina.call_runtime import CallTracker, stage_envelope
from lamina.context_budget import RequestBudget
from lamina.evidence import QuoteMatchError, ValidationFailure, resolve_quote
from lamina.production_contract import ProductionError, _evidence
from lamina.store import Workspace, canonical


def test_typography_recovery_returns_unchanged_source_span():
    text = "Before. The “rotor”\u00a0\n turns. After."
    result = resolve_quote('The "rotor" turns.', text)
    assert result.quote == "The “rotor”\u00a0\n turns."
    assert text[result.start : result.end] == result.quote
    assert result.method == "typography"


@pytest.mark.parametrize(
    "text, quote",
    [
        ("A cafe\u0301 opens.", "A café opens."),
        ("A café opens.", "A cafe\u0301 opens."),
    ],
)
def test_combining_unicode_keeps_original_offsets(text, quote):
    result = resolve_quote(quote, text)
    assert result.quote == text
    assert result.start == 0 and result.end == len(text)


def test_exact_match_wins_and_ambiguous_normalization_fails():
    text = "“same” and ‘same’"
    assert resolve_quote("‘same’", text).method == "exact"
    with pytest.raises(QuoteMatchError, match="several source spans"):
        resolve_quote('"same"', "“same” and “same”")


@pytest.mark.parametrize(
    "text, quote",
    [
        ("Dose: 5 mM.", "Dose: 5 MM."),
        ("Die Straße.", "Die STRASSE."),
        ("Change: −5.", "Change: -5."),
        ("Range: 3–5.", "Range: 3-5."),
        ("Area: m².", "Area: m2."),
        ("Letter: å.", "Letter: a."),
        ("Count: ５.", "Count: 5."),
    ],
)
def test_recovery_does_not_change_case_units_numbers_or_signs(text, quote):
    with pytest.raises(QuoteMatchError):
        resolve_quote(quote, text)


def test_typography_can_be_disabled_and_empty_quote_is_rejected():
    with pytest.raises(QuoteMatchError):
        resolve_quote('"word"', "“word”", allow_typography=False)
    with pytest.raises(QuoteMatchError):
        resolve_quote("  \n", "source")


def test_matching_words_do_not_authorize_a_foreign_source():
    with pytest.raises(ProductionError):
        _evidence(
            [{"unit_id": "foreign", "quote": "same words"}],
            {"owned": {"text": "same words"}},
            "reader",
        )


class ScriptedProvider:
    identity = "reliability-fixture"

    def __init__(self, replies, budget=None):
        self.replies = iter(replies)
        self.requests = []
        self.budget = budget or RequestBudget(100_000)

    def budget_for(self, stage):
        return self.budget

    def call(self, stage, request):
        self.requests.append(copy.deepcopy(request))
        result = next(self.replies)
        if isinstance(result, Exception):
            raise result
        return result

    def last_usage(self):
        return {"input_tokens": 11, "output_tokens": 3, "model": "fixture"}


def invoke(
    tracker, workspace, provider, checker=lambda result: result, max_bytes=100_000
):
    return tracker.call(
        workspace,
        provider,
        "example",
        "item",
        "Explain the source.",
        {"answer": "str"},
        {"source": "Original source"},
        checker,
        max_bytes,
    )


def test_contract_feedback_repairs_once_then_warm_cache_makes_no_call(tmp_path):
    def validate(raw):
        if raw["answer"] != "valid":
            raise ValidationFailure(
                "answer needs a known source quote",
                code="quote_not_found",
                path="answer",
                partial={"preserved": "already validated"},
            )
        return raw

    provider = ScriptedProvider([{"answer": "invalid"}, {"answer": "valid"}])
    tracker = CallTracker()
    workspace = Workspace(tmp_path)
    assert invoke(tracker, workspace, provider, validate) == {"answer": "valid"}
    first, retry = provider.requests
    assert first["input"] == retry["input"]
    assert retry["validation_feedback"]["code"] == "quote_not_found"
    assert retry["validation_feedback"]["validated_partial"] == {
        "preserved": "already validated"
    }
    assert invoke(tracker, workspace, provider, validate) == {"answer": "valid"}
    assert len(provider.requests) == 2
    metrics = tracker.metrics()
    assert metrics["provider_attempts"] == 2
    assert metrics["retry_attempts"] == metrics["failed_attempts"] == 1
    assert metrics["failed_requests"] == 0
    assert metrics["recovered_requests"] == 1
    assert tracker.records[0]["recovered_failures"][0]["validated_partial"] == {
        "preserved": "already validated"
    }
    assert metrics["usage"] == {
        "input_tokens": 22,
        "output_tokens": 6,
        "cached_input_tokens": 0,
    }
    assert metrics["usage_reported_calls"] == 2
    assert metrics["cache_hits"] == metrics["cache_misses"] == 1
    assert metrics["provider_request_bytes"] == sum(
        len(canonical(request).encode()) for request in provider.requests
    )


def test_exhausted_contract_retains_partial_but_never_caches_success(tmp_path):
    def validate(raw):
        raise ValidationFailure(
            "second idea still has invalid evidence",
            partial={"ideas": [{"id": "valid"}]},
        )

    provider = ScriptedProvider([{}, {}])
    tracker = CallTracker(max_attempts=2)
    workspace = Workspace(tmp_path)
    with pytest.raises(ValidationFailure) as raised:
        invoke(tracker, workspace, provider, validate)
    assert raised.value.partial_results == {"ideas": [{"id": "valid"}]}
    assert raised.value.metrics["failed_requests"] == 1
    assert raised.value.metrics["provider_attempts"] == 2
    assert workspace.stats()["jobs"] == {"failed": 1}


@pytest.mark.parametrize(
    "failure",
    [
        ValueError("programming error"),
        RuntimeError("adapter unspecified failure"),
        ValidationFailure("foreign source id", code="foreign_unit", retryable=False),
    ],
)
def test_unknown_errors_and_foreign_ids_do_not_trigger_blind_retries(tmp_path, failure):
    def validate(raw):
        raise failure

    provider = ScriptedProvider([{}])
    tracker = CallTracker(max_attempts=3)
    with pytest.raises(type(failure)):
        invoke(tracker, Workspace(tmp_path), provider, validate)
    assert len(provider.requests) == 1
    assert tracker.metrics()["retry_attempts"] == 0


def test_only_provider_declared_transient_errors_are_retried(tmp_path):
    class Transient(RuntimeError):
        retryable = True
        retry_after = 0

    provider = ScriptedProvider([Transient("rate limited"), {"answer": "valid"}])
    tracker = CallTracker()
    assert invoke(tracker, Workspace(tmp_path), provider) == {"answer": "valid"}
    assert provider.requests[0] == provider.requests[1]
    assert tracker.metrics()["failed_attempts"] == 1


def test_long_retry_after_defers_without_an_early_duplicate(tmp_path):
    class Transient(RuntimeError):
        retryable = True
        retry_after = 120

    provider = ScriptedProvider([Transient("rate limited")])
    tracker = CallTracker()
    with pytest.raises(Transient):
        invoke(tracker, Workspace(tmp_path), provider)
    assert len(provider.requests) == 1
    assert tracker.records[0]["attempts"][0]["retry_deferred_seconds"] == 120


@pytest.mark.parametrize("use_token_limit", [False, True])
def test_feedback_must_fit_the_complete_request_budget(tmp_path, use_token_limit):
    def validate(raw):
        raise ValidationFailure("Return the required answer field.")

    original = stage_envelope(
        "example",
        "Explain the source.",
        {"answer": "str"},
        {"source": "Original source"},
    )
    if use_token_limit:
        budget = RequestBudget(
            100_000,
            context_tokens=30,
            output_tokens=10,
            count_tokens=lambda request: 25 if "validation_feedback" in request else 10,
        )
    else:
        budget = RequestBudget(len(canonical(original).encode()) + 1)
    provider = ScriptedProvider([{}], budget)
    tracker = CallTracker()
    with pytest.raises(ProductionError, match="budget") as raised:
        invoke(tracker, Workspace(tmp_path), provider, validate)
    assert len(provider.requests) == 1
    assert raised.value.metrics["provider_attempts"] == 1
    assert raised.value.metrics["failed_requests"] == 1


def test_initial_budget_failure_is_measured_without_a_provider_call(tmp_path):
    provider = ScriptedProvider([], RequestBudget(1))
    tracker = CallTracker()
    with pytest.raises(ProductionError) as raised:
        invoke(tracker, Workspace(tmp_path), provider)
    assert provider.requests == []
    assert raised.value.metrics["provider_request_bytes"] == 0
    assert tracker.records[0]["cache"] == "none"


def test_broken_optional_usage_reporting_does_not_discard_valid_work(tmp_path):
    class BadUsage(ScriptedProvider):
        def last_usage(self):
            raise ValueError("broken usage reporter")

    provider = BadUsage([{"answer": "valid"}])
    tracker = CallTracker()
    assert invoke(tracker, Workspace(tmp_path), provider) == {"answer": "valid"}
    assert len(provider.requests) == 1
    assert tracker.active["example"] == 0
    assert tracker.metrics()["usage_reported_calls"] == 0
    assert tracker.records[0]["attempts"][0]["usage_error"] == "ValueError"
