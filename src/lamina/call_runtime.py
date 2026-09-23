"""Cached model calls with bounded repair, measured attempts and fenced commits."""

from __future__ import annotations

import copy
from dataclasses import asdict, replace
import math
import threading
import time

from .context_budget import ContextBudgetError, RequestBudget
from .evidence import ValidationFailure
from .production_contract import ProductionError, REVISION, _BASE

_TOKEN_KEYS = ("input_tokens", "output_tokens", "cached_input_tokens")


def make_envelope(stage, instruction, expected_shape, data, *, workload_items=None):
    envelope = {
        "protocol": "lamina-stage-1",
        "revision": REVISION,
        "stage": stage,
        "instruction": _BASE + instruction,
        "expected_shape": expected_shape,
        "input": data,
    }
    if workload_items is not None:
        if type(workload_items) is not int or workload_items < 0:
            raise ValueError("workload_items must be a nonnegative integer")
        envelope["workload_items"] = workload_items
    return envelope


stage_envelope = make_envelope


def request_budget(provider, stage, max_bytes):
    budget = getattr(provider, "budget_for", lambda _: RequestBudget(max_bytes))(stage)
    if budget is None:
        budget = RequestBudget(max_bytes)
    if budget.workload is not None and budget.workload.evidence is not None:
        identity_for = getattr(provider, "configuration_identity_for", None)
        identity = (
            identity_for(stage)
            if callable(identity_for)
            else getattr(provider, "configuration_identity", None)
            or getattr(provider, "identity", None)
        )
        if not isinstance(identity, str) or not identity:
            raise ValueError(
                "observed workload evidence requires a provider configuration identity"
            )
        budget.workload.validate_binding(provider_identity=identity)
    return replace(budget, max_request_bytes=min(max_bytes, budget.max_request_bytes))


def _usage_total(attempts):
    result = {}
    for attempt in attempts:
        usage = attempt.get("usage", {})
        for key in _TOKEN_KEYS:
            if key in usage:
                result[key] = result.get(key, 0) + usage[key]
        if isinstance(usage.get("model"), str):
            result["model"] = usage["model"]
    return result


class CallTracker:
    """One logical cached request can make up to ``max_attempts`` model calls.

    Only explicit validator failures or provider-declared transient failures
    permit another attempt. All attempts remain inside the original cache lease;
    only a completely validated result is committed. Concurrency and retry
    limits do not invalidate already successful requests.
    """

    def __init__(self, progress=None, max_attempts=2):
        if type(max_attempts) is not int or max_attempts < 1:
            raise ValueError("max_attempts must be a positive integer")
        self.lock = threading.Lock()
        self.progress = progress
        self.max_attempts = max_attempts
        self.records = []
        self.active = {}
        self.peak = {}

    def event(self, stage, item, status):
        if self.progress:
            self.progress({"stage": stage, "item": item, "status": status})

    def call(
        self,
        workspace,
        provider,
        stage,
        item,
        instruction,
        expected_shape,
        data,
        checker,
        max_bytes,
        *,
        repair_request=None,
        workload_items=None,
    ):
        envelope = make_envelope(
            stage, instruction, expected_shape, data, workload_items=workload_items
        )
        budget = request_budget(provider, stage, max_bytes)
        attempts = []
        validation_history = []
        retained_partial = None
        initial_measurement = budget.measure(envelope)
        started = time.monotonic()
        self.event(stage, item, "started")

        def checked_budget(request):
            try:
                return budget.check(request)
            except ContextBudgetError as exc:
                raise ProductionError(f"{stage} request for {item}: {exc}") from exc

        def handler(original):
            nonlocal retained_partial
            request = original
            for number in range(1, self.max_attempts + 1):
                # Feedback is part of the complete request and must fit too.
                measurement = checked_budget(request)
                attempt = {
                    "number": number,
                    **asdict(measurement),
                    "usage": {},
                    "status": "started",
                }
                attempts.append(attempt)
                before = time.monotonic()
                with self.lock:
                    self.active[stage] = self.active.get(stage, 0) + 1
                    self.peak[stage] = max(self.active[stage], self.peak.get(stage, 0))
                failure = None
                try:
                    raw = provider.call(stage, request)
                    result = checker(raw)
                    attempt["status"] = "completed"
                    return result
                except Exception as exc:
                    failure = exc
                    attempt.update(
                        status="failed",
                        error_type=type(exc).__name__,
                        error_code=getattr(exc, "code", ""),
                    )
                    if isinstance(exc, ValidationFailure):
                        attempt["validation"] = exc.feedback()
                        diagnostic = {"attempt": number, "validation": exc.feedback()}
                        if exc.partial is not None:
                            attempt["retained_partial"] = True
                            retained_partial = copy.deepcopy(exc.partial)
                            diagnostic["validated_partial"] = copy.deepcopy(exc.partial)
                        validation_history.append(diagnostic)
                finally:
                    try:
                        reported = getattr(provider, "last_usage", lambda: {})()
                    except Exception as metadata_error:
                        # Optional usage reporting must not discard an otherwise
                        # validated result. Keep the missing measurement visible.
                        reported = {}
                        attempt["usage_error"] = type(metadata_error).__name__
                    if isinstance(reported, dict):
                        attempt["usage"] = {
                            key: value
                            for key, value in reported.items()
                            if (
                                key in _TOKEN_KEYS and type(value) is int and value >= 0
                            )
                            or (key == "model" and isinstance(value, str))
                        }
                    attempt["wall_ms"] = round((time.monotonic() - before) * 1000, 3)
                    with self.lock:
                        self.active[stage] -= 1

                if (
                    number == self.max_attempts
                    or getattr(failure, "retryable", False) is not True
                ):
                    raise failure
                if isinstance(failure, ValidationFailure):
                    if repair_request is not None:
                        # The caller can retain validated rows and request only
                        # repairs. Attempts, budgets and commit fencing remain
                        # owned by this one logical cached call.
                        request = repair_request(original, failure)
                        self.event(stage, item, "repairing_contract")
                        continue
                    feedback = failure.feedback()
                    request = {**original, "validation_feedback": feedback}
                    if failure.partial is not None:
                        candidate = {
                            **request,
                            "validation_feedback": {
                                **feedback,
                                "validated_partial": copy.deepcopy(failure.partial),
                            },
                        }
                        if budget.fits(candidate):
                            request = candidate
                    self.event(stage, item, "repairing_contract")
                else:
                    # A long Retry-After becomes an explicit deferred failure;
                    # silently retrying sooner would violate provider capacity.
                    delay = getattr(failure, "retry_after", None)
                    if delay is None:
                        delay = 0.25 * 2 ** min(number - 1, 4)
                    if (
                        not isinstance(delay, (int, float))
                        or not math.isfinite(delay)
                        or delay < 0
                        or delay > 60
                    ):
                        attempt["retry_deferred_seconds"] = (
                            delay
                            if isinstance(delay, (int, float)) and math.isfinite(delay)
                            else None
                        )
                        raise failure
                    self.event(stage, item, "retrying_provider")
                    time.sleep(delay)
            raise AssertionError("attempt budget did not terminate")

        failure = None
        try:
            checked_budget(envelope)
            result = workspace.run_cached(
                stage,
                envelope,
                handler,
                identity=f"{REVISION}:{getattr(provider, 'identity_for', lambda _: provider.identity)(stage)}",
                retries=0,
            )
        except Exception as exc:
            failure = exc
        record = {
            "stage": stage,
            "item": item,
            "cache": "miss" if attempts else ("none" if failure else "hit"),
            "status": "failed" if failure else "completed",
            **asdict(initial_measurement),
            "provider_request_bytes": sum(
                attempt["request_bytes"] for attempt in attempts
            ),
            "wall_ms": round((time.monotonic() - started) * 1000, 3),
            "usage": _usage_total(attempts),
            "attempts": attempts,
        }
        if failure:
            record["error_type"] = type(failure).__name__
        elif validation_history:
            record["recovered_failures"] = validation_history
        with self.lock:
            self.records.append(record)
        self.event(stage, item, record["status"])
        if failure:
            failure.metrics = self.metrics()
            if retained_partial is not None:
                failure.partial_results = retained_partial
            raise failure
        return result

    def metrics(self):
        with self.lock:
            records = copy.deepcopy(self.records)
            peak = dict(self.peak)
        attempts = [attempt for record in records for attempt in record["attempts"]]
        return {
            "requests": sorted(
                records, key=lambda record: (record["stage"], record["item"])
            ),
            "peak_provider_calls": peak,
            "context_bytes_total": sum(record["request_bytes"] for record in records),
            "provider_request_bytes": sum(
                record["provider_request_bytes"] for record in records
            ),
            "failed_requests": sum(record["status"] == "failed" for record in records),
            "recovered_requests": sum(
                bool(record.get("recovered_failures")) for record in records
            ),
            "provider_attempts": len(attempts),
            "retry_attempts": sum(
                max(0, len(record["attempts"]) - 1) for record in records
            ),
            "failed_attempts": sum(
                attempt["status"] == "failed" for attempt in attempts
            ),
            "usage": {
                key: sum(attempt["usage"].get(key, 0) for attempt in attempts)
                for key in _TOKEN_KEYS
            },
            "usage_reported_calls": sum(
                any(key in attempt["usage"] for key in _TOKEN_KEYS)
                for attempt in attempts
            ),
            "cache_hits": sum(record["cache"] == "hit" for record in records),
            "cache_misses": sum(record["cache"] == "miss" for record in records),
        }
