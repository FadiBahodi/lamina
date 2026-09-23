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

This example selects transports and models. Add the required [workload policies](#workload-limits) and model token settings below before running production. Unlisted stages use the default adapter. A stage selects its configured model directly. Keep API keys in the process environment. The bundled HTTP examples require `LAMINA_API_BASE`, `LAMINA_MODEL` and `LAMINA_API_KEY`; install `lamina-engine[http]` for the persistent example. `http_service.py` shares one HTTPX connection pool across its workers. HTTP/2 is opt-in with `LAMINA_HTTP2=1`.

Both transports accept `command`, `env`, `timeout`, `version`, `max_request_bytes`, optional `request_format` and per-stage `workload` policies. Persistent transport also accepts `max_pending` and `max_response_bytes`. These are resource ceilings. `max_pending` bounds requests admitted to the adapter process; extra callers wait under their call deadline. Match it to the endpoint's permitted concurrency. The runtime's worker limit can be lower.

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

Usage belongs to the current calling thread. The bundled HTTP adapters retain reported usage on successful responses and output-truncation failures. Other failures can incur usage that the endpoint does not report. Missing usage remains unknown. A provider attempt can fail before reaching the endpoint; it does not establish a billed request.

## Production stages

`production_read` interprets source structures. `production_group` groups navigation cards across sources; `production_assign` assigns original ideas against the resulting outline. `production_route` builds the section plan, and optional `production_targets` collects exact prompt and answer groups. Writers, reviewers and repairs use `production_write`, `production_review` and `production_repair`. `document_review=true` enables the `production_consistency` stage to check relationships across completed sections. Assessment checking uses `assessment_blind_solve` and `assessment_judge`.

Each stage can select its own configured adapter, request capacity and workload policy. Direct and supplied-assignment workflows skip the source-planning stages they do not need.

Reader input units contain the original `text` once and a `spans` list of `{id, start, end}`. Offsets count Unicode characters. Readers return `evidence_refs: [{span_id, end_span_id?, phrase?}]`; a range must be contiguous within one owned unit, and an optional phrase must occur exactly once in that range. Code materializes the original quotation. Existing `{unit_id, quote}` evidence remains supported.

An extraction-row correction supplies `repair.invalid_ideas: [{index, idea, error}]`. The response supplies only `replacements: [{index, idea}]` for those indices. The validator retains accepted rows, merges replacements and checks the complete result under the same attempt allowance.

## Workload limits

A context limit checks whether a request fits. A separate workload policy limits how much the model must accomplish in that request. Put policies on each adapter row in `models.json`:

```json
{
  "workload": {
    "*": {"max_items": "<chosen maximum items per call>", "basis": "configured"},
    "production_read": {
      "max_input_tokens": "<chosen complete reading request limit>",
      "max_items": "<chosen maximum owned source spans>",
      "basis": "configured"
    }
  }
}
```

Replace placeholders with positive JSON integers. These values are operator choices, not recommended optima. `max_input_tokens` counts the complete rendered prompt, including framing and context; it requires a matching token counter. `max_items` counts owned objects as defined below and can operate without tokenization. If both are supplied, both apply. A named stage replaces the `*` policy completely. Hard context, output and transport limits continue to apply.

| Stage | Item count |
| --- | --- |
| `production_read` | Owned source spans |
| `production_route`, `production_group`, `production_assign`, `production_targets` | Incoming idea or group cards |
| `production_write`, `production_review`, `production_repair` | Assigned ideas, or original source units for direct/assigned workflows |
| `production_consistency` | Two completed sections |
| `assessment_blind_solve`, `assessment_judge` | One question |

Item counts describe objects supplied to the task; a source unit or sentence can contain many propositions. Use token limits as well when object sizes vary. Unowned context contributes to the token measurement.

Multi-item planning, writing and review require a declared workload policy. Planned workflows check required route, write and review policies before reading sources. An unprofiled reader owns one parser structure; an explicitly assigned single structure can run without a policy only when no additional source units, form exemplars or retained observations enter its context. Its semantic quality remains unmeasured. The engine never silently substitutes the model context limit for a missing workload policy.

`basis="configured"` is the default. Evaluate selected loads on the actual model, task, domain and output requirements before treating them as supported operating limits. The [quality evaluation protocol](quality-evaluation.md) describes experiments and their scope.

A named-stage policy can declare `basis="observed"` with an `evidence` object containing `provider_identity`, `protocol_revision`, `report_path` and `report_sha256`. The provider identity must match `configuration_identity`, or `StageProvider.configuration_identity_for(stage)`; the revision must match the request protocol revision. `report_path` locates a readable configured-provider observation report; `report_sha256` verifies its contents. The report must contain a completed trial with a completed call, matching stage-budget and provider-configuration records, and the same protocol revision. Relative report paths resolve against the model configuration file. The runtime checks that provenance and configuration binding; it cannot infer that the observed load is appropriate for new material. The `*` fallback supports configured policies only.

Custom Python providers can return a `RequestBudget` carrying `WorkloadProfile(stage, max_items=...)`. Profiles without evidence remain unassessed for semantic quality.

## Context and repeated prefixes

The bundled chat examples share one renderer with the engine's token counter. It places instructions and output requirements first, shared reference material next, and local source material last. Each block has stable JSON ordering, even after cache serialization reorders the request dictionary. Validation feedback travels with the local material.

This preserves repeated prefixes where an endpoint supports prefix caching. Cached-token usage must come from the endpoint. Lamina assumes no cache discount, hit rate or latency benefit, and does not insert vendor-specific cache breakpoints.

Set `request_format="lamina-chat-1"`, `LAMINA_CONTEXT_TOKENS`, `LAMINA_TOKENIZER` and `LAMINA_MAX_OUTPUT_TOKENS` for the actual selected model. The engine counts the rendered message text with the named tiktoken encoding, adds a 256-token framing reserve, and reserves output capacity. The framing reserve is an explicit allowance; it is not a measurement of every vendor's message framing. The adapter checks the same budget before HTTP.

`budget_for(stage)` returns the configured `RequestBudget`, including the independent workload profile. Generic command adapters expose a byte guard and can declare item limits. A custom Python provider can supply a token counter for its actual prompt conversion. Byte counts are never converted into guessed token counts.

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
