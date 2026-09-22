# Model adapters

An adapter reads one JSON request from standard input, returns one JSON object on standard output, and writes logs to standard error. Lamina starts the command without a shell. The adapter may use any model provider.

```bash
lamina produce --workspace .lamina --brief 'Explain the sources' \
  --adapter 'python my_adapter.py' --output ./result
```

A request contains `protocol`, `revision`, `stage`, `instruction`, `expected_shape`, and `input`. Return the requested result object. Production validates source membership, exact quotes, assignments and stage-specific fields. The `expected_shape` field is an instruction for the model, not a general JSON Schema validator.

## Production stages

| Stage | Input and job |
| --- | --- |
| `production_read` | Owned source units and optional neighbors → cited ideas |
| `production_targets` | Ideas → prompt and answer groups, when enabled |
| `production_route` | Ideas and goal → section assignments |
| `production_write` | Section, assigned evidence and bounded context → finished section |
| `production_review` | Assignment, evidence and finished section → findings |
| `production_repair` | Same context plus findings → corrected section |
| `assessment_blind_solve` | Candidate-facing prompts → answer and uncertainties |
| `assessment_judge` | Candidate answer, key and source excerpts → findings |

Direct and caller-assigned workflows skip reading and routing. Review also checks a repaired result. The legacy learning build uses `extract`, `reconcile`, `plan`, `author`, and `review`; its installed schemas and [example adapter](../examples/adapter) describe those contracts. General methods use `method_node` with the node's declared inputs and output instructions.

## Different models for different work

Pass `--adapter @models.json` to configure adapters by stage:

```json
{
  "default": {
    "command": ["python", "examples/adapter/http_chat.py"],
    "env": {"LAMINA_MODEL": "your-writing-model"},
    "version": "writing-1"
  },
  "stages": {
    "production_read": {
      "command": ["python", "examples/adapter/http_chat.py"],
      "env": {"LAMINA_MODEL": "your-reading-model"},
      "version": "reading-1"
    }
  }
}
```

This is a configuration lookup in code. Unlisted stages use the default adapter. Each configuration accepts `command`, `env`, `timeout`, `version` and `max_request_bytes`. Python callers can use `configured_provider(path)` or `StageProvider`.

Keep credentials in the process environment. Command adapters freeze that environment at startup. Cache identity includes command arguments, readable script hashes, timeout, version, known `LAMINA_*` model settings and explicit environment overrides. Custom behavior controlled by other inherited variables must be represented by `version` or explicit `env`. Changing a stage's model changes that stage's cache identity.

## Token budgets and usage

Lamina's byte limit bounds serialized requests; it cannot infer every model's tokenizer or context window. The [HTTP example](../examples/adapter/http_chat.py) accepts `LAMINA_CONTEXT_TOKENS`, `LAMINA_TOKENIZER`, and `LAMINA_MAX_OUTPUT_TOKENS`. With a context budget configured, it counts message text using the named tiktoken encoding and reserves output space plus a framing allowance before sending HTTP. Configure these for the actual endpoint. A truncated response fails clearly.

Adapters may report provider usage with this envelope:

```json
{
  "protocol": "lamina-response-1",
  "result": {"the": "requested stage result"},
  "usage": {"input_tokens": 1200, "output_tokens": 400, "cached_input_tokens": 0},
  "model": "reported-model-name"
}
```

Bare result objects remain supported. Receipts distinguish logical request volume from actual provider attempts and record usage when supplied. They do not estimate monetary cost from bytes.

## Operation

Keep model calls stateless, especially assessment solves. Exit nonzero on failure; return complete JSON without logs on standard output. Completed requests survive failure and can be reused on resume. Imported assessment-role sources remain held out from generation; duplicated answers inside teaching files can still contaminate that boundary.
