"""Exercise process multiplexing and real local HTTP connection reuse."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
import threading
import time

import pytest

from lamina.chat_protocol import chat_messages, chat_token_count
from lamina.providers import (
    CommandProvider,
    PersistentCommandProvider,
    ProviderError,
    StageProvider,
    configured_provider,
)

ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "examples" / "adapter" / "http_service.py"


def request(value=0, **extra):
    return {
        "protocol": "lamina-stage-1",
        "stage": "test",
        "instruction": "Read reference data.",
        "expected_shape": {"value": "integer"},
        "input": {"brief": "Explain", "value": value},
        **extra,
    }


@pytest.fixture
def multiplex(tmp_path):
    script = tmp_path / "service.py"
    script.write_text("""import concurrent.futures, json, os, sys, threading, time
with open(os.environ["STARTS"], "a") as handle: handle.write(str(os.getpid()) + "\\n")
lock = threading.Lock()
active = peak = 0
def run(row):
    global active, peak
    value = row["payload"]["input"]["value"]
    with lock:
        active += 1
        peak = max(active, peak)
    if value == "hang": time.sleep(30)
    else: time.sleep(0.12 if value == 0 else 0.01)
    with lock:
        active -= 1
        if value == "bad": print("bad json", flush=True)
        elif value == "rate": print(json.dumps({"id": row["id"], "error": {"code": "rate_limit", "retry_after": 2, "message": "SECRET SOURCE"}}), flush=True)
        else: print(json.dumps({"id": row["id"], "result": {"protocol": "lamina-response-1", "result": {"value": value, "peak": peak}, "usage": {"input_tokens": value if isinstance(value,int) else 1}, "model": "fixture"}}), flush=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=128) as pool:
    for line in sys.stdin: pool.submit(run, json.loads(line))
""")
    starts = tmp_path / "starts.txt"
    with PersistentCommandProvider(
        [sys.executable, str(script)],
        timeout=2,
        max_pending=2,
        env={"STARTS": str(starts)},
    ) as provider:
        yield provider, starts


def test_multiplex_reuses_process_and_matches_out_of_order_replies(multiplex):
    provider, starts = multiplex

    def run(value):
        result = provider.call("test", request(value))
        return value, result, provider.last_usage()

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = [
            future.result()
            for future in as_completed([pool.submit(run, value) for value in range(6)])
        ]
    assert len(starts.read_text().splitlines()) == 1
    assert results[0][0] != 0
    assert {value for value, _, _ in results} == set(range(6))
    for value, result, usage in results:
        assert result["value"] == value
        assert usage["input_tokens"] == value
        assert result["peak"] <= 2


def test_timeout_breaks_generation_and_next_call_restarts(multiplex):
    provider, starts = multiplex
    provider.timeout = 1
    started = time.monotonic()
    with pytest.raises(ProviderError) as failure:
        provider.call("test", request("hang"))
    assert failure.value.retryable and failure.value.code == "timeout"
    assert time.monotonic() - started < 3
    assert provider.call("test", request(1))["value"] == 1
    assert len(starts.read_text().splitlines()) == 2


def test_protocol_failure_is_not_retried_and_close_is_explicit(multiplex):
    provider, starts = multiplex
    with pytest.raises(ProviderError) as failure:
        provider.call("test", request("bad"))
    assert not failure.value.retryable
    assert len(starts.read_text().splitlines()) == 1
    assert provider.call("test", request(2))["value"] == 2
    process = provider._process
    provider.close()
    assert process.poll() is not None
    with pytest.raises(ProviderError, match="closed"):
        provider.call("test", request(3))
    provider.restart()
    assert provider.call("test", request(4))["value"] == 4


def test_structured_rate_limit_preserves_delay_without_source_text(multiplex):
    provider, starts = multiplex
    with pytest.raises(ProviderError) as failure:
        provider.call("test", request("rate"))
    assert failure.value.retryable
    assert failure.value.retry_after == 2
    assert "SECRET" not in str(failure.value)
    assert len(starts.read_text().splitlines()) == 1


def test_static_shared_local_prefix_survives_dictionary_reordering():
    first = request(1)
    first["input"]["shared_route"] = [{"id": "a", "title": "Wind"}]
    second = json.loads(json.dumps(request(2), sort_keys=True))
    second["input"]["shared_route"] = first["input"]["shared_route"]
    a, b = chat_messages(first), chat_messages(second)
    assert a[0] == b[0]
    assert (
        a[1]["content"].split(',"local":')[0] == b[1]["content"].split(',"local":')[0]
    )
    assert a[1]["content"] != b[1]["content"]
    second["validation_feedback"] = {
        "code": "foreign_id",
        "instruction": "Use assigned IDs",
    }
    assert "Use assigned IDs" in chat_messages(second)[1]["content"]


@pytest.fixture
def endpoint():
    pytest.importorskip("httpx")
    seen, ports = [], []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen.append(data)
            ports.append(self.client_address[1])
            value = json.loads(data["messages"][1]["content"])["local"]["value"]
            output = {
                "choices": [{"message": {"content": json.dumps({"value": value})}}],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 4,
                    "prompt_tokens_details": {"cached_tokens": 7},
                },
                "model": "local-test",
            }
            if value == "truncate":
                output["choices"][0]["finish_reason"] = "length"
            encoded = json.dumps(output).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    settings = {
        "LAMINA_API_BASE": f"http://127.0.0.1:{server.server_port}",
        "LAMINA_MODEL": "local-test",
        "LAMINA_API_KEY": "fixture-key",
        "PYTHONPATH": str(ROOT / "src"),
        "ALL_PROXY": "",
        "HTTP_PROXY": "",
        "HTTPS_PROXY": "",
        "all_proxy": "",
        "http_proxy": "",
        "https_proxy": "",
    }
    try:
        yield settings, seen, ports
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_http_service_reuses_keepalive_connection_and_reports_usage(endpoint):
    settings, seen, ports = endpoint
    with PersistentCommandProvider(
        [sys.executable, str(SERVICE)], env=settings, timeout=10
    ) as provider:
        for value in range(4):
            assert provider.call("test", request(value)) == {"value": value}
        assert provider.last_usage() == {
            "input_tokens": 10,
            "output_tokens": 4,
            "cached_input_tokens": 7,
            "model": "local-test",
        }
    assert len(seen) == 4
    assert len(set(ports)) == 1
    assert all("response_format" not in body for body in seen)


@pytest.mark.parametrize("persistent", [False, True])
def test_truncated_output_retains_actual_usage_on_both_transports(endpoint, persistent):
    settings, _, _ = endpoint
    adapter = SERVICE if persistent else SERVICE.with_name("http_chat.py")
    factory = PersistentCommandProvider if persistent else CommandProvider
    with factory([sys.executable, str(adapter)], env=settings, timeout=10) as provider:
        with pytest.raises(ProviderError) as failure:
            provider.call("test", request("truncate"))
        assert failure.value.code == "output_truncated"
        assert (
            failure.value.usage
            == provider.last_usage()
            == {
                "input_tokens": 10,
                "output_tokens": 4,
                "cached_input_tokens": 7,
                "model": "local-test",
            }
        )


def test_structured_decoding_requires_explicit_schema_and_endpoint_capability(endpoint):
    pytest.importorskip("jsonschema")
    settings, seen, _ = endpoint
    schema = {
        "type": "object",
        "properties": {"value": {"type": "integer"}},
        "required": ["value"],
        "additionalProperties": False,
    }
    with PersistentCommandProvider(
        [sys.executable, str(SERVICE)], env=settings, timeout=10
    ) as provider:
        with pytest.raises(ProviderError) as failure:
            provider.call("test", request(1, response_schema=schema))
        assert failure.value.code == "invalid_request"
        assert seen == []
    with PersistentCommandProvider(
        [sys.executable, str(SERVICE)],
        timeout=10,
        env={**settings, "LAMINA_STRUCTURED_OUTPUT": "json_schema"},
    ) as provider:
        assert provider.call("test", request(3, response_schema=schema)) == {"value": 3}
        assert seen[-1]["response_format"]["json_schema"]["schema"] == schema
        with pytest.raises(ProviderError) as failure:
            provider.call("test", request("bad type", response_schema=schema))
        assert failure.value.code == "invalid_response"


def test_chat_budget_counts_actual_messages_and_feedback(endpoint):
    tiktoken = pytest.importorskip("tiktoken")
    settings, _, _ = endpoint
    provider = CommandProvider(
        [sys.executable, str(SERVICE)],
        request_format="lamina-chat-1",
        env={
            **settings,
            "LAMINA_CONTEXT_TOKENS": "4000",
            "LAMINA_MAX_OUTPUT_TOKENS": "1000",
            "LAMINA_TOKENIZER": "cl100k_base",
        },
    )
    payload = request(1, validation_feedback={"instruction": "Correct the assigned ID"})
    encoding = tiktoken.get_encoding("cl100k_base")
    budget = provider.budget_for("test")
    assert budget.count_tokens(payload) == chat_token_count(payload, encoding)
    assert budget.context_tokens == 4000 and budget.output_tokens == 1000
    stage = StageProvider(CommandProvider([sys.executable]), {"test": provider})
    assert stage.budget_for("test") is budget
    assert stage.budget_for("else").context_tokens is None


def test_config_and_legacy_audio_result_remain_compatible(tmp_path):
    script = tmp_path / "audio.py"
    script.write_text(
        'import json; print(json.dumps({"audio": "UklGRg==", "media_type": "audio/wav"}))'
    )
    path = tmp_path / "models.json"
    path.write_text(
        json.dumps(
            {
                "default": {"command": [sys.executable, str(script)]},
                "stages": {
                    "test": {
                        "transport": "jsonl",
                        "command": [sys.executable],
                        "max_pending": 3,
                    }
                },
            }
        )
    )
    with configured_provider(path) as provider:
        assert (
            provider.call("audio", {"protocol": "lamina-audio-1", "stage": "audio"})[
                "audio"
            ]
            == "UklGRg=="
        )
        assert isinstance(provider.stages["test"], PersistentCommandProvider)
        assert provider.stages["test"].max_pending == 3


def test_request_deadline_also_bounds_a_blocked_pipe_write(tmp_path):
    script = tmp_path / "stalled.py"
    script.write_text("import time; time.sleep(30)")
    with PersistentCommandProvider(
        [sys.executable, str(script)], timeout=1
    ) as provider:
        started = time.monotonic()
        with pytest.raises(ProviderError) as failure:
            provider.call("test", request("x" * 500_000))
        assert failure.value.code == "timeout"
        assert time.monotonic() - started < 3
        assert provider._process is None


def test_response_size_is_bounded_before_json_decoding(tmp_path):
    script = tmp_path / "oversized.py"
    script.write_text('import sys; sys.stdin.readline(); print("x" * 3000, flush=True)')
    with PersistentCommandProvider(
        [sys.executable, str(script)], max_response_bytes=1024
    ) as provider:
        with pytest.raises(ProviderError) as failure:
            provider.call("test", request(1))
        assert failure.value.code == "invalid_response"
        assert not failure.value.retryable


def test_real_command_adapter_preserves_output_truncation_code(endpoint):
    settings, _, _ = endpoint
    adapter = ROOT / "examples" / "adapter" / "http_chat.py"
    provider = CommandProvider([sys.executable, str(adapter)], env=settings, timeout=10)
    with pytest.raises(ProviderError) as failure:
        provider.call("test", request("truncate"))
    assert failure.value.code == "output_truncated"
    assert not failure.value.retryable
