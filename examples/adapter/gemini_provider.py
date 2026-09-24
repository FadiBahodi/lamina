"""Native Gemini REST provider for private calibration experiments.

This optional example uses only the Python standard library.  It renders every
Lamina request through ``chat_messages`` and asks Gemini's own ``countTokens``
endpoint to measure that exact system instruction and user content.
"""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from lamina.calibration import starter_workloads
from lamina.chat_protocol import chat_messages
from lamina.context_budget import RequestBudget
from lamina.providers import ProviderError
from lamina.store import canonical
from lamina.workload_profiles import parse_workloads


API_ROOT = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_MODEL = "models/gemini-2.5-flash"
DEFAULT_CONTEXT_TOKENS = 1_048_576
DEFAULT_OUTPUT_TOKENS = 8_192
DEFAULT_THINKING_TOKENS = 1_024


def _positive_int(name, value, *, allow_zero=False):
    minimum = 0 if allow_zero else 1
    if type(value) is not int or value < minimum:
        qualifier = "nonnegative" if allow_zero else "positive"
        raise ValueError(f"{name} must be a {qualifier} integer")
    return value


def _retry_after(headers):
    value = headers.get("Retry-After") if headers is not None else None
    try:
        return max(0.0, min(float(value), 3600.0))
    except (TypeError, ValueError):
        return None


def _http_error(status, headers=None):
    code = (
        "rate_limit"
        if status == 429
        else "timeout"
        if status == 408
        else "unavailable"
        if status >= 500
        else "authentication"
        if status in {401, 403}
        else "invalid_request"
    )
    messages = {
        "rate_limit": "Gemini rate limited the request",
        "timeout": "Gemini timed out the request",
        "unavailable": "Gemini is temporarily unavailable",
        "authentication": "Gemini rejected authentication",
        "invalid_request": "Gemini rejected the request",
    }
    return ProviderError(
        messages[code],
        code=code,
        retryable=code in {"rate_limit", "timeout", "unavailable"},
        retry_after=_retry_after(headers),
    )


class GeminiProvider:
    """Direct ``generateContent`` provider with provider-native token budgets."""

    def __init__(
        self,
        *,
        model=None,
        timeout=120,
        max_request_bytes=16_000_000,
        context_tokens=DEFAULT_CONTEXT_TOKENS,
        output_tokens=DEFAULT_OUTPUT_TOKENS,
        thinking_tokens=DEFAULT_THINKING_TOKENS,
        temperature=0.2,
        max_concurrency=4,
        workload=None,
    ):
        configured_model = model or os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
        if not isinstance(configured_model, str) or not configured_model:
            raise ValueError("model must be a nonempty string")
        if not configured_model.startswith("models/"):
            configured_model = "models/" + configured_model
        if not 1 <= timeout <= 3600:
            raise ValueError("timeout must be between 1 and 3600 seconds")
        _positive_int("max_request_bytes", max_request_bytes)
        _positive_int("context_tokens", context_tokens)
        _positive_int("output_tokens", output_tokens)
        _positive_int("thinking_tokens", thinking_tokens, allow_zero=True)
        if output_tokens >= context_tokens:
            raise ValueError("output_tokens must be smaller than context_tokens")
        # Gemini 2.5 Flash accepts 0..24576 thought tokens. maxOutputTokens also
        # covers thought tokens, so leave at least one token for returned JSON.
        if thinking_tokens > min(24_576, output_tokens - 1):
            raise ValueError("thinking_tokens exceeds the configured output allowance")
        if type(temperature) not in {int, float} or not 0 <= temperature <= 2:
            raise ValueError("temperature must be between 0 and 2")
        if type(max_concurrency) is not int or not 1 <= max_concurrency <= 32:
            raise ValueError("max_concurrency must be between 1 and 32")

        self.model = configured_model
        self.timeout = float(timeout)
        self.max_request_bytes = max_request_bytes
        self.context_tokens = context_tokens
        self.output_tokens = output_tokens
        self.thinking_tokens = thinking_tokens
        self.temperature = float(temperature)
        self.max_concurrency = max_concurrency
        self._slots = threading.BoundedSemaphore(max_concurrency)
        self._local = threading.local()
        self._count_cache = {}
        self._count_lock = threading.Lock()
        self._metrics_lock = threading.Lock()
        self._transport_metrics = {
            "count_requests": 0,
            "count_wall_ms": 0.0,
            "generation_requests": 0,
            "generation_wall_ms": 0.0,
        }
        self._stage_budgets = {}
        self.workloads = parse_workloads(
            starter_workloads() if workload is None else workload
        )

        from lamina import chat_protocol

        renderer_hash = hashlib.sha256(
            Path(chat_protocol.__file__).read_bytes()
        ).hexdigest()
        configuration = {
            "api": API_ROOT,
            "model": self.model,
            "context_tokens": self.context_tokens,
            "output_tokens": self.output_tokens,
            "thinking_tokens": self.thinking_tokens,
            "temperature": self.temperature,
            "max_concurrency": self.max_concurrency,
            "max_request_bytes": self.max_request_bytes,
            "prompt_renderer": renderer_hash,
        }
        digest = hashlib.sha256(canonical(configuration).encode()).hexdigest()[:20]
        self.configuration_identity = "gemini:" + digest
        for profile in self.workloads.values():
            profile.validate_binding(provider_identity=self.configuration_identity)
        workload_digest = hashlib.sha256(
            canonical(
                [
                    self.configuration_identity,
                    {
                        name: profile.identity
                        for name, profile in sorted(self.workloads.items())
                    },
                ]
            ).encode()
        ).hexdigest()[:20]
        self.identity = "gemini:" + workload_digest

    def _url(self, method):
        model = urllib.parse.quote(self.model, safe="/")
        return f"{API_ROOT}/{model}:{method}"

    @staticmethod
    def _api_key():
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise ProviderError(
                "GEMINI_API_KEY is not configured", code="authentication"
            )
        return key

    def _generation_request(self, request):
        messages = chat_messages(request)
        generation = {
            "responseMimeType": "application/json",
            "maxOutputTokens": self.output_tokens,
            "temperature": self.temperature,
            "thinkingConfig": {"thinkingBudget": self.thinking_tokens},
        }
        if request.get("response_schema") is not None:
            generation["responseJsonSchema"] = request["response_schema"]
        return {
            "systemInstruction": {"parts": [{"text": messages[0]["content"]}]},
            "contents": [{"role": "user", "parts": [{"text": messages[1]["content"]}]}],
            "generationConfig": generation,
        }

    def _post(self, method, body):
        raw = canonical(body).encode("utf-8")
        if len(raw) > self.max_request_bytes:
            raise ProviderError(
                "Gemini request exceeds the configured transport budget",
                code="context_limit",
            )
        request = urllib.request.Request(
            self._url(method),
            data=raw,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self._api_key(),
            },
            method="POST",
        )
        try:
            with self._slots:
                prefix = "count" if method == "countTokens" else "generation"
                started = time.monotonic()
                with self._metrics_lock:
                    self._transport_metrics[prefix + "_requests"] += 1
                try:
                    with urllib.request.urlopen(
                        request, timeout=self.timeout
                    ) as response:
                        envelope = json.load(response)
                finally:
                    elapsed = (time.monotonic() - started) * 1000
                    with self._metrics_lock:
                        self._transport_metrics[prefix + "_wall_ms"] += elapsed
        except urllib.error.HTTPError as exc:
            # Do not read or expose the response body: it may echo source data or
            # provider diagnostics containing request details.
            raise _http_error(exc.code, exc.headers) from exc
        except TimeoutError as exc:
            raise ProviderError(
                "Gemini request timed out", code="timeout", retryable=True
            ) from exc
        except urllib.error.URLError as exc:
            raise ProviderError(
                "Gemini connection failed", code="connection", retryable=True
            ) from exc
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise ProviderError(
                "Gemini returned an invalid response", code="invalid_response"
            ) from exc
        if not isinstance(envelope, dict):
            raise ProviderError(
                "Gemini returned an invalid response", code="invalid_response"
            )
        return envelope

    def _count_generation(self, body):
        cache_key = hashlib.sha256(canonical(body).encode()).hexdigest()
        with self._count_lock:
            cached = self._count_cache.get(cache_key)
        if cached is not None:
            return cached
        count_request = {"generateContentRequest": {"model": self.model, **body}}
        envelope = self._post("countTokens", count_request)
        count = envelope.get("totalTokens")
        if type(count) is not int or count < 0:
            raise ProviderError(
                "Gemini returned an invalid token count", code="invalid_response"
            )
        with self._count_lock:
            self._count_cache.setdefault(cache_key, count)
            return self._count_cache[cache_key]

    def count_tokens(self, request):
        return self._count_generation(self._generation_request(request))

    def source_token_count(self, text):
        if not isinstance(text, str):
            raise ValueError("source text must be a string")
        body = {
            "contents": [{"role": "user", "parts": [{"text": text}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "maxOutputTokens": self.output_tokens,
                "temperature": self.temperature,
                "thinkingConfig": {"thinkingBudget": self.thinking_tokens},
            },
        }
        return self._count_generation(body)

    def budget_for(self, stage):
        profile = self.workloads.get(stage, self.workloads.get("*"))
        if profile is not None and profile.stage == "*":
            profile = replace(profile, stage=stage)
        if stage not in self._stage_budgets:
            self._stage_budgets[stage] = RequestBudget(
                self.max_request_bytes,
                context_tokens=self.context_tokens,
                output_tokens=self.output_tokens,
                count_tokens=self.count_tokens,
                counting="gemini-countTokens",
                workload=profile,
            )
        return self._stage_budgets[stage]

    def output_limit_for(self, _stage):
        return self.output_tokens

    def configuration_identity_for(self, _stage):
        return self.configuration_identity

    def identity_for(self, stage):
        profile = self.workloads.get(stage, self.workloads.get("*"))
        if profile is not None and profile.stage == "*":
            profile = replace(profile, stage=stage)
        if profile is None:
            return self.configuration_identity
        token = canonical([self.configuration_identity, profile.identity])
        return "gemini:" + hashlib.sha256(token.encode()).hexdigest()[:20]

    def last_usage(self):
        return getattr(self._local, "usage", {}).copy()

    def transport_metrics(self):
        """Return process-wide network counts, separate from model-call usage."""
        with self._metrics_lock:
            return {
                name: round(value, 3) if name.endswith("_wall_ms") else value
                for name, value in self._transport_metrics.items()
            }

    def call(self, stage, request):
        self._local.usage = {}
        if request.get("stage") != stage:
            raise ProviderError("stage mismatch in Gemini request")
        body = self._generation_request(request)
        envelope = self._post("generateContent", body)
        metadata = envelope.get("usageMetadata")
        metadata = metadata if isinstance(metadata, dict) else {}
        usage = {}
        for source, target in (
            ("promptTokenCount", "input_tokens"),
            ("candidatesTokenCount", "output_tokens"),
            ("cachedContentTokenCount", "cached_input_tokens"),
            ("thoughtsTokenCount", "thinking_tokens"),
            ("totalTokenCount", "total_tokens"),
        ):
            value = metadata.get(source)
            if type(value) is int and value >= 0:
                usage[target] = value
        returned_model = envelope.get("modelVersion")
        usage["model"] = (
            returned_model if isinstance(returned_model, str) else self.model
        )
        self._local.usage = usage
        try:
            candidate = envelope["candidates"][0]
            finish = candidate.get("finishReason")
            if finish == "MAX_TOKENS":
                raise ProviderError(
                    "Gemini output exceeded its output budget",
                    code="output_truncated",
                    usage=usage,
                )
            parts = candidate["content"]["parts"]
            text = "".join(
                part.get("text", "") for part in parts if isinstance(part, dict)
            )
            result = json.loads(text)
            if not isinstance(result, dict):
                raise ValueError("JSON response is not an object")
            return result
        except ProviderError:
            raise
        except (
            KeyError,
            IndexError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as exc:
            raise ProviderError(
                "Gemini returned invalid JSON", code="invalid_response", usage=usage
            ) from exc
