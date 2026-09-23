"""The bundled chat adapter's stable prompt layout and token accounting."""

from __future__ import annotations

import json

FRAMING_RESERVE = 256
_SHARED_FIELDS = {
    "brief",
    "format",
    "shared_route",
    "shared_context",
    "source_policy",
    "outline",
    "parent_section",
}


def chat_messages(request: dict) -> list[dict]:
    """Keep instructions first, shared reference data next, local material last.

    Shared material remains user data. Keeping it separate from instructions
    preserves the reference-data boundary while making repeated prefixes stable.
    """
    if request.get("protocol") != "lamina-stage-1":
        raise ValueError("expected a Lamina stage request")
    data = request["input"]
    if not isinstance(data, dict):
        raise ValueError("stage input must be an object")
    explicit = set(data) == {"shared", "local"}
    shared = (
        data["shared"]
        if explicit
        else {key: value for key, value in data.items() if key in _SHARED_FIELDS}
    )
    local = (
        data["local"]
        if explicit
        else {key: value for key, value in data.items() if key not in _SHARED_FIELDS}
    )
    if "validation_feedback" in request:
        local = {**local, "validation_feedback": request["validation_feedback"]}
    static = {"stage": request["stage"], "expected_shape": request["expected_shape"]}
    if "response_schema" in request:
        static["response_schema"] = request["response_schema"]
    dumps = lambda value: json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return [
        {
            "role": "system",
            "content": request["instruction"]
            + " Return one complete JSON object matching the expected shape.\n"
            + dumps(static),
        },
        {
            "role": "user",
            "content": '{"shared":' + dumps(shared) + ',"local":' + dumps(local) + "}",
        },
    ]


def chat_token_count(request, encoding):
    """Count actual message text plus an explicit protocol-framing reserve."""
    return (
        sum(
            len(encoding.encode(message["content"], disallowed_special=()))
            for message in chat_messages(request)
        )
        + FRAMING_RESERVE
    )
