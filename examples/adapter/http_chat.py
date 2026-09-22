#!/usr/bin/env python3
"""Example Lamina command adapter for a user-configured JSON chat endpoint.

Set LAMINA_API_BASE, LAMINA_MODEL, and LAMINA_API_KEY. The endpoint must accept
POST /chat/completions with model/messages and return choices[0].message.content
as a JSON object string. No provider or model is selected by this repository.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request


def main() -> int:
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict) or request.get("protocol") != "lamina-stage-1":
            raise ValueError("expected one Lamina stage request object")
        base = os.environ["LAMINA_API_BASE"].rstrip("/")
        model = os.environ["LAMINA_MODEL"]
        token = os.environ["LAMINA_API_KEY"]
        parsed = urllib.parse.urlparse(base)
        if parsed.scheme != "https" and not (
            parsed.scheme == "http"
            and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        ):
            raise ValueError("API base must use HTTPS or local loopback HTTP")
        messages = [
            {
                "role": "system",
                "content": request["instruction"]
                + " Return exactly one JSON object matching the expected shape. No markdown.",
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "stage": request["stage"],
                        "expected_shape": request["expected_shape"],
                        "input": request["input"],
                    },
                    ensure_ascii=False,
                ),
            },
        ]
        output_limit = int(os.environ.get("LAMINA_MAX_OUTPUT_TOKENS", "8192"))
        if output_limit < 1:
            raise ValueError("LAMINA_MAX_OUTPUT_TOKENS must be positive")
        context = os.environ.get("LAMINA_CONTEXT_TOKENS")
        if context:
            import tiktoken

            # Configure the encoding for the chosen model, not a word heuristic.
            encoding = tiktoken.get_encoding(os.environ["LAMINA_TOKENIZER"])
            tokens = sum(
                len(encoding.encode(m["content"], disallowed_special=()))
                for m in messages
            )
            if tokens + output_limit + 256 > int(context):
                raise ValueError(
                    "Request plus reserved output exceeds model context; split the assignment"
                )
        body = json.dumps(
            {
                "model": model,
                "messages": messages,
                "temperature": float(os.environ.get("LAMINA_TEMPERATURE", "0.2")),
                "max_tokens": output_limit,
            },
            ensure_ascii=False,
        ).encode()
        call = urllib.request.Request(
            base + "/chat/completions",
            data=body,
            headers={
                "Authorization": "Bearer " + token,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(call, timeout=100) as response:
            envelope = json.load(response)
        if envelope["choices"][0].get("finish_reason") == "length":
            raise ValueError(
                "Model output was truncated; split the assignment or increase its output budget"
            )
        content = envelope["choices"][0]["message"]["content"]
        result = json.loads(content)
        if not isinstance(result, dict):
            raise ValueError("model response was not a JSON object")
        usage = envelope.get("usage") or {}
        measured = {}
        for source_key, target_key in (
            ("prompt_tokens", "input_tokens"),
            ("completion_tokens", "output_tokens"),
        ):
            if type(usage.get(source_key)) is int:
                measured[target_key] = usage[source_key]
        cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens")
        if type(cached) is int:
            measured["cached_input_tokens"] = cached
        json.dump(
            {
                "protocol": "lamina-response-1",
                "result": result,
                "model": envelope.get("model", model),
                "usage": measured,
            },
            sys.stdout,
            ensure_ascii=False,
        )
        sys.stdout.write("\n")
        return 0
    except Exception as exc:
        print(f"Lamina adapter error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
