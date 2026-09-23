#!/usr/bin/env python3
"""One-shot chat adapter. http_service.py reuses these request/response rules."""

from __future__ import annotations

import datetime
import email.utils
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

from lamina.chat_protocol import chat_messages, chat_token_count


class AdapterFailure(Exception):
    def __init__(self, code, retry_after=None):
        self.code, self.retry_after = code, retry_after
        super().__init__(code)

    def error(self):
        result = {"code": self.code}
        if self.retry_after is not None:
            result["retry_after"] = self.retry_after
        return result


def endpoint():
    base = os.environ["LAMINA_API_BASE"].rstrip("/")
    parsed = urllib.parse.urlparse(base)
    if parsed.scheme != "https" and not (
        parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    ):
        raise AdapterFailure("invalid_request")
    return base + "/chat/completions"


def request_body(request):
    messages = chat_messages(request)
    output_limit = int(os.environ.get("LAMINA_MAX_OUTPUT_TOKENS", "8192"))
    if output_limit < 1:
        raise AdapterFailure("invalid_request")
    context = os.environ.get("LAMINA_CONTEXT_TOKENS")
    if context:
        import tiktoken

        encoding = tiktoken.get_encoding(os.environ["LAMINA_TOKENIZER"])
        if chat_token_count(request, encoding) + output_limit > int(context):
            raise AdapterFailure("context_limit")
    body = {
        "model": os.environ["LAMINA_MODEL"],
        "messages": messages,
        "temperature": float(os.environ.get("LAMINA_TEMPERATURE", "0.2")),
        "max_tokens": output_limit,
    }
    schema = request.get("response_schema")
    if schema is not None:
        # The endpoint must explicitly support this dialect. expected_shape remains
        # prompt documentation and is never guessed into a JSON Schema.
        if os.environ.get("LAMINA_STRUCTURED_OUTPUT") != "json_schema":
            raise AdapterFailure("invalid_request")
        from jsonschema import Draft202012Validator

        Draft202012Validator.check_schema(schema)
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "lamina_result", "strict": True, "schema": schema},
        }
    return body


def response_result(envelope, request):
    try:
        choice = envelope["choices"][0]
        if choice.get("finish_reason") == "length":
            raise AdapterFailure("output_truncated")
        result = json.loads(choice["message"]["content"])
        if not isinstance(result, dict):
            raise AdapterFailure("invalid_response")
        if request.get("response_schema") is not None:
            from jsonschema import Draft202012Validator

            if not Draft202012Validator(request["response_schema"]).is_valid(result):
                raise AdapterFailure("invalid_response")
        usage = envelope.get("usage") or {}
        measured = {}
        for source_key, target_key in (
            ("prompt_tokens", "input_tokens"),
            ("completion_tokens", "output_tokens"),
        ):
            if type(usage.get(source_key)) is int and usage[source_key] >= 0:
                measured[target_key] = usage[source_key]
        cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens")
        if type(cached) is int and cached >= 0:
            measured["cached_input_tokens"] = cached
        return {
            "protocol": "lamina-response-1",
            "result": result,
            "model": envelope.get("model", os.environ["LAMINA_MODEL"]),
            "usage": measured,
        }
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise AdapterFailure("invalid_response") from exc


def http_failure(status, retry_after=None):
    delay = None
    if retry_after is not None:
        try:
            delay = float(retry_after)
        except (TypeError, ValueError):
            try:
                delay = (
                    email.utils.parsedate_to_datetime(retry_after)
                    - datetime.datetime.now(datetime.timezone.utc)
                ).total_seconds()
            except (TypeError, ValueError, OverflowError):
                pass
    if delay is not None:
        delay = max(0, min(delay, 3600))
    code = (
        "rate_limit"
        if status == 429
        else (
            "timeout"
            if status == 408
            else (
                "unavailable"
                if status >= 500
                else "authentication" if status in {401, 403} else "invalid_request"
            )
        )
    )
    return AdapterFailure(code, delay)


def main():
    try:
        request = json.load(sys.stdin)
        body = request_body(request)
        call = urllib.request.Request(
            endpoint(),
            data=json.dumps(body, ensure_ascii=False).encode(),
            headers={
                "Authorization": "Bearer " + os.environ["LAMINA_API_KEY"],
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(call, timeout=100) as response:
                envelope = json.load(response)
        except urllib.error.HTTPError as exc:
            raise http_failure(exc.code, exc.headers.get("Retry-After")) from exc
        except TimeoutError as exc:
            raise AdapterFailure("timeout") from exc
        except urllib.error.URLError as exc:
            raise AdapterFailure("connection") from exc
        reply = response_result(envelope, request)
    except AdapterFailure as exc:
        reply = {"protocol": "lamina-error-1", "error": exc.error()}
    except Exception:
        # Source text, credentials and provider response bodies never enter public
        # exception strings. Add protected diagnostics locally when needed.
        reply = {"protocol": "lamina-error-1", "error": {"code": "invalid_request"}}
    json.dump(reply, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
