# Model adapters

An adapter receives a Lamina request and returns a JSON object. It owns access to the chosen model. Lamina owns source checks, request caching, scheduling and retry policy.

## Choose a transport

| Transport | Process lifetime | Use |
| --- | --- | --- |
| `command` | One command per call | Existing adapters, isolated tools and speech synthesis |
| `jsonl` | One process for concurrent calls | Reuse model-client connections across a production run |

Commands run without a shell. Python callers can use `CommandProvider`, `PersistentCommandProvider` or `configured_provider(path)`. Close persistent providers when their owner stops; both provider types support `with` blocks. The CLI accepts `--adapter @models.json`:

```json
{
  "default": {
    "transport": "jsonl",
    "command": ["python", "examples/adapter/http_service.py"],
    "request_format": "lamina-chat-1",
    "max_pending": 8,
    "env": {"LAMINA_MODEL": "your-writing-model"},
    "version": "writing-1"
  },
  "stages": {
    "production_read": {
      "transport": "jsonl",
      "command": ["python", "examples/adapter/http_service.py"],
      "request_format": "lamina-chat-1",
      "env": {"LAMINA_MODEL": "your-reading-model"},
      "version": "reading-1"
    }
  }
}
```

Unlisted stages use the default adapter. A stage selects its configured model directly. Keep API keys in the process environment. The bundled HTTP examples require `LAMINA_API_BASE`, `LAMINA_MODEL` and `LAMINA_API_KEY`; install `lamina-engine[http]` for the persistent example. `http_service.py` shares one HTTPX connection pool across its workers. HTTP/2 is opt-in with `LAMINA_HTTP2=1`.

Both transports accept `command`, `env`, `timeout`, `version`, `max_request_bytes` and optional `request_format`. Persistent transport also accepts `max_pending` and `max_response_bytes`. These are resource ceilings. `max_pending` bounds requests admitted to the adapter process; extra callers wait under their call deadline. Match it to the endpoint's permitted concurrency. The runtime's worker limit can be lower.

## Requests and replies

A stage request contains `protocol`, `revision`, `stage`, `instruction`, `expected_shape` and `input`. The command transport sends that object on stdin and expects one result object on stdout. Existing bare results, including audio envelopes, remain supported.

Persistent transport writes one envelope per line:

```json
{"protocol":"lamina-jsonl-1","id":"request-identifier","payload":{"protocol":"lamina-stage-1","stage":"production_read","instruction":"...","expected_shape":{},"input":{}}}
```

The adapter returns `{"id":"request-identifier","result":{...}}`. Replies may arrive in any order. A result can include measured usage:

```json
{
  "protocol": "lamina-response-1",
  "result": {"the": "requested stage result"},
  "usage": {"input_tokens": 1200, "output_tokens": 400, "cached_input_tokens": 800},
  "model": "reported-model-name"
}
```

Usage belongs to the current calling thread. The bundled HTTP adapters currently return usage for successful result envelopes; failed responses, including truncated output, can incur tokens whose usage is unavailable in the receipt. Missing usage remains unknown. A provider attempt can fail before reaching the endpoint; it does not establish a billed request.

## Production stages

`production_read` interprets source structures. `production_group` groups navigation cards across sources; `production_assign` assigns original ideas against the resulting outline. `production_route` builds the section plan, and optional `production_targets` collects exact prompt and answer groups. Writers, reviewers and repairs use `production_write`, `production_review` and `production_repair`. `document_review=true` enables the `production_consistency` stage to check relationships across completed sections. Assessment checking uses `assessment_blind_solve` and `assessment_judge`.

Each stage can select its own configured adapter and request budget. Direct and supplied-assignment workflows skip the source-planning stages they do not need.

## Context and repeated prefixes

The bundled chat examples share one renderer with the engine's token counter. It places instructions and output requirements first, shared reference material next, and local source material last. Each block has stable JSON ordering, even after cache serialization reorders the request dictionary. Validation feedback travels with the local material.

This preserves repeated prefixes where an endpoint supports prefix caching. Cached-token usage must come from the endpoint. Lamina assumes no cache discount, hit rate or latency benefit, and does not insert vendor-specific cache breakpoints.

Set `request_format="lamina-chat-1"`, `LAMINA_CONTEXT_TOKENS`, `LAMINA_TOKENIZER` and `LAMINA_MAX_OUTPUT_TOKENS` for the actual selected model. The engine counts the rendered message text with the named tiktoken encoding, adds a 256-token framing reserve, and reserves output capacity. The framing reserve is an explicit allowance; it is not a measurement of every vendor's message framing. The adapter checks the same budget before HTTP.

`budget_for(stage)` returns the configured `RequestBudget`. Generic command adapters expose a byte guard. A custom Python provider can supply a token counter for its actual prompt conversion. Byte counts are never converted into guessed token counts.

## Structured output

`expected_shape` documents the requested fields in the prompt. An optional `response_schema` contains a real JSON Schema. The bundled HTTP examples forward it through the endpoint's `response_format` only when `LAMINA_STRUCTURED_OUTPUT=json_schema` explicitly enables that capability; they validate the returned object against it as well. A configured endpoint can reject unsupported schemas. Refusals, truncation, transport failures and semantic mistakes still require handling.

Source membership, exact quotations, section ownership and other production checks continue after decoding. Schema conformance establishes the response's shape.

## Failure and recovery

Persistent adapters return `{"id":"...","error":{"code":"rate_limit","retry_after":2}}`. One-shot adapters can return `{"protocol":"lamina-error-1","error":{...}}`. Recognized transient codes are `rate_limit`, `timeout`, `unavailable` and `connection`. Authentication, invalid requests and invalid responses require a different correction. `output_truncated` reports exhausted output capacity so a reader can split its assignment. Public exceptions omit arbitrary adapter messages, provider response bodies and source text.

The transport never retries by itself. The runtime decides whether a failure fits its retry allowance. A persistent call's deadline includes waiting for a pending-request slot. A timeout, disconnect or malformed stream ends that process and fails its outstanding calls; the next call starts a fresh process. Terminating the local process cannot guarantee cancellation of work already accepted by a remote endpoint. `close()` rejects future calls; an explicit `restart()` permits them again.

Keep requests stateless, especially assessment solves. Reusing a process or HTTP connection does not authorize retaining another request's conversation. The bundled examples construct fresh messages for every call.

Cache identity includes command arguments, readable script hashes, model configuration and explicit environment overrides. Use `version` when behavior changes outside those inputs. `StageProvider` forwards the selected adapter's identity, budget and usage, and closes each owned adapter once.

## References

HTTPX documents [connection pooling](https://www.python-httpx.org/advanced/clients/), [resource limits](https://www.python-httpx.org/advanced/resource-limits/) and [HTTP/2](https://www.python-httpx.org/http2/). Output schemas follow [JSON Schema](https://json-schema.org/understanding-json-schema/).
