import json
import threading
import urllib.error

import pytest

from examples.adapter.gemini_provider import GeminiProvider
from lamina.providers import ProviderError


def stage_request():
    return {
        "protocol": "lamina-stage-1",
        "revision": "test",
        "stage": "production_read",
        "instruction": "Preserve every qualification.",
        "expected_shape": {"ideas": []},
        "response_schema": {
            "type": "object",
            "properties": {"ideas": {"type": "array"}},
            "required": ["ideas"],
        },
        "input": {"shared": {"brief": "Teach."}, "local": {"core": []}},
        "workload_items": 0,
    }


class Reply:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self, *_args):
        return json.dumps(self.payload).encode()


def test_count_and_generate_use_same_rendered_request(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "secret-test-key")
    calls = []

    def urlopen(request, timeout):
        body = json.loads(request.data)
        calls.append((request, timeout, body))
        if request.full_url.endswith(":countTokens"):
            return Reply({"totalTokens": 321})
        return Reply(
            {
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {"parts": [{"text": '{"ideas":[]}'}]},
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 321,
                    "candidatesTokenCount": 7,
                    "thoughtsTokenCount": 19,
                    "totalTokenCount": 347,
                },
                "modelVersion": "gemini-2.5-flash-001",
            }
        )

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    provider = GeminiProvider(workload={"production_read": {"max_items": 2}})
    request = stage_request()
    assert provider.budget_for("production_read").measure(request).input_tokens == 321
    assert provider.call("production_read", request) == {"ideas": []}

    count_body = calls[0][2]["generateContentRequest"]
    count_body.pop("model")
    assert count_body == calls[1][2]
    assert calls[0][0].headers["X-goog-api-key"] == "secret-test-key"
    assert calls[1][2]["systemInstruction"]["parts"][0]["text"].startswith(
        "Preserve every qualification."
    )
    assert calls[1][2]["generationConfig"] == {
        "responseMimeType": "application/json",
        "responseJsonSchema": request["response_schema"],
        "maxOutputTokens": 8192,
        "temperature": 0.2,
        "thinkingConfig": {"thinkingBudget": 1024},
    }
    assert provider.last_usage() == {
        "input_tokens": 321,
        "output_tokens": 7,
        "thinking_tokens": 19,
        "total_tokens": 347,
        "model": "gemini-2.5-flash-001",
    }
    metrics = provider.transport_metrics()
    assert metrics["count_requests"] == 1
    assert metrics["generation_requests"] == 1
    assert metrics["count_wall_ms"] >= 0
    assert metrics["generation_wall_ms"] >= 0


def test_counting_is_memoized_and_source_count_uses_gemini(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    bodies = []

    def urlopen(request, timeout):
        bodies.append(json.loads(request.data))
        return Reply({"totalTokens": len(bodies) * 10})

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    provider = GeminiProvider()
    request = stage_request()
    assert provider.count_tokens(request) == 10
    assert provider.count_tokens(request) == 10
    assert provider.source_token_count("source fact") == 20
    assert provider.source_token_count("source fact") == 20
    assert len(bodies) == 2
    assert (
        bodies[1]["generateContentRequest"]["contents"][0]["parts"][0]["text"]
        == "source fact"
    )
    assert provider.transport_metrics()["count_requests"] == 2
    assert provider.transport_metrics()["generation_requests"] == 0


def test_usage_is_thread_local(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    barrier = threading.Barrier(2)

    def urlopen(request, timeout):
        body = json.loads(request.data)
        marker = json.loads(body["contents"][0]["parts"][0]["text"])["local"]["marker"]
        barrier.wait()
        return Reply(
            {
                "candidates": [
                    {"finishReason": "STOP", "content": {"parts": [{"text": "{}"}]}}
                ],
                "usageMetadata": {"promptTokenCount": marker},
            }
        )

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    provider = GeminiProvider()
    seen = []

    def run(marker):
        request = stage_request()
        request["input"]["local"]["marker"] = marker
        provider.call("production_read", request)
        seen.append(provider.last_usage()["input_tokens"])

    threads = [threading.Thread(target=run, args=(value,)) for value in (11, 22)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(seen) == [11, 22]
    assert provider.transport_metrics()["generation_requests"] == 2


def test_http_failures_do_not_expose_response_body_or_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "never-show-this")

    def urlopen(request, timeout):
        raise urllib.error.HTTPError(
            request.full_url,
            429,
            'provider body says "private_source": "secret"',
            {"Retry-After": "3"},
            None,
        )

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    with pytest.raises(ProviderError) as failure:
        GeminiProvider().count_tokens(stage_request())
    assert failure.value.code == "rate_limit"
    assert failure.value.retryable
    assert failure.value.retry_after == 3
    assert "private_source" not in str(failure.value)
    assert "never-show-this" not in str(failure.value)


def test_identity_excludes_key_and_includes_model_and_config(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "first")
    first = GeminiProvider(workload={"production_read": {"max_items": 2}})
    monkeypatch.setenv("GEMINI_API_KEY", "second")
    same = GeminiProvider(workload={"production_read": {"max_items": 2}})
    changed = GeminiProvider(
        model="models/gemini-2.5-flash",
        thinking_tokens=2048,
        workload={"production_read": {"max_items": 2}},
    )
    assert first.identity == same.identity
    assert first.configuration_identity == same.configuration_identity
    assert first.configuration_identity != changed.configuration_identity
    assert (
        first.configuration_identity
        != GeminiProvider(max_concurrency=2).configuration_identity
    )
    assert first.budget_for("production_read").counting == "gemini-countTokens"
    assert GeminiProvider().budget_for("production_write").workload.max_items == 6


def test_missing_key_and_invalid_thinking_limit_are_bounded(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(ProviderError, match="GEMINI_API_KEY"):
        GeminiProvider().count_tokens(stage_request())
    with pytest.raises(ValueError, match="thinking_tokens"):
        GeminiProvider(output_tokens=1024, thinking_tokens=1024)
