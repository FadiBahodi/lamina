# Lamina

Lamina turns source collections into reference documents, guides, podcast scripts and assessments. It preserves source locations, divides independent work across model calls, and reuses completed work when inputs repeat.

Give it files, a description of the result, and a model adapter. It can write directly from the sources, read for the current task and create an outline, or follow sections supplied by a person or another agent.

## Install and run

Python 3.11+ and SQLite with FTS5 are required.

```sh
git clone https://github.com/FadiBahodi/lamina.git
cd lamina
pip install -e '.[pdf,slides,http,tokens]'
lamina ingest ./sources --workspace .lamina
```

For a compatible chat endpoint, set `LAMINA_API_BASE`, `LAMINA_MODEL` and `LAMINA_API_KEY`. Save `models.json`:

```json
{
  "default": {
    "transport": "jsonl",
    "command": ["python", "examples/adapter/http_service.py"],
    "request_format": "lamina-chat-1",
    "workload": {
      "*": {
        "max_input_tokens": "<chosen complete task request limit>",
        "max_items": "<chosen maximum items per task>"
      },
      "production_read": {"max_input_tokens": "<chosen reading request limit>"}
    },
    "env": {
      "LAMINA_CONTEXT_TOKENS": "<documented model context limit>",
      "LAMINA_TOKENIZER": "<tiktoken encoding for the model>",
      "LAMINA_MAX_OUTPUT_TOKENS": "<chosen output allowance>"
    }
  }
}
```

Replace every placeholder before starting. Workload limits must be JSON integers; environment values remain strings. The tokenizer must match the selected model. Context and output limits describe what the endpoint accepts. The separate `workload` limits specify how much work each call may attempt. Choose provisional limits, evaluate the resulting output on representative material, and retain the measurements before increasing them. The `*` entry supplies a fallback; named stages replace it. [Adapters](docs/adapters.md) defines the fields and [Adapters](docs/adapters.md#workload-limits) defines the counted items. No built-in limit establishes a model's accuracy.

```sh
lamina app --workspace .lamina --adapter @models.json
```

Open `http://127.0.0.1:8048`. The adapter sends selected source context to the configured provider. The persistent example shares an HTTP connection pool across calls. Existing one-command-per-call adapters remain supported.

The CLI uses the same engine:

```sh
lamina produce --workspace .lamina --adapter @models.json \
  --brief 'Explain windmill blade designs, preserving where the sources disagree.' \
  --format guide --output output/windmills
```

With no adapter, `lamina app` offers a recorded example. `lamina demo --output demo` runs a deterministic guide fixture offline.

To evaluate a configured provider before expanding task size, run the [quality experiment](docs/quality-evaluation.md):

```sh
PYTHONPATH=src python benchmarks/quality_titration.py --models models.json \
  --loads 20,80,200 --input-limits 4000,8000,16000 \
  --stage production_read --reading task --replicates 3 --complete \
  --minimum-fraction 1 --maximum-counterfacts 0 --output output/quality-run
```

These numbers define an example experiment. `--loads` counts background paragraphs; `--input-limits` varies the selected stage's complete prompt allowance. The report records actual request sizes and traces fragile facts into the finished output. Its lexical checks cover the declared controls; inspect representative source facts and completed documents before accepting an operating limit. This command uses the configured provider and incurs its normal usage.

## What happens to the files

1. **Import their structure.** Markdown blocks, PDF pages and PowerPoint slide components retain their locations. Slide text, tables and speaker notes stay together during reading. Scanned PDFs can use local OCR.
2. **Choose the work per call.** Automatic mode checks the declared writing and review workload limits along with request capacity. Collections that exceed those limits use readers and a planner. Supplied assignments bypass planning. Combining multiple items requires a declared workload policy.
3. **Organize the material.** Readers identify material relevant to the brief and cite source references that code resolves to exact text. Without a reading workload profile, each call owns one parser structure. Planning groups related material across files within its declared limits; final assignment revisits the original ideas.
4. **Write and check each section.** Writers receive assigned material, original source passages and declared context. Review starts when a section finishes. A finding can trigger a repair and recheck. Optional document review compares completed sections with known relationships.
5. **Export and revise.** Deliver Markdown, HTML, PDF and an execution receipt. Repeated requests reuse cached results. Source references remain bound to the selected file revisions.

A reviewer is another model call that compares the draft with its assignment and sources. Code checks identifiers, quotation spans and ownership. The receipt records findings, unperformed checks, source coverage and provider-reported usage.

## Interfaces

| Need | Documentation |
| --- | --- |
| Workflows, controls, assignments and revision | [Production](docs/production.md) |
| Models, persistent transport and context budgets | [Adapters](docs/adapters.md) |
| File structure, OCR and parser limits | [Parsing](docs/parsing.md) |
| Custom dependencies and resource lanes | [Methods](docs/methods.md) |
| Architecture and scheduling | [Architecture](docs/architecture.md) |
| Mechanics measurements and their scope | [Benchmarks](docs/benchmarks.md) |
| Model workload and quality experiments | [Quality evaluation](docs/quality-evaluation.md) |

Search imported sources with `lamina search 'blade design' --json`. Python callers use `build_production(workspace, provider, brief, source_ids, options)` or separate planning and writing calls.

## Limits

Source accounting and quotation matches establish traceability. Semantic completeness, writing quality and factual support need evaluation on the actual material. A model can return valid JSON while omitting important facts. Declared task limits constrain work; their quality remains unassessed until evaluated. Reusable inventories are an explicit option and can carry the same omissions into later projects. Whole structures or required context can exceed configured limits; those cases remain errors or unperformed checks. The shared outline must still fit its planning request.

PDF figures and reading order need inspection. Assessments export separate candidate and examiner files; live oral-case delivery is unavailable. Audio requires a separate speech adapter and listening review. Keep the local app on loopback.

```sh
pip install -e '.[test,pdf,slides,http,tokens]'
python -m pytest -q
```
