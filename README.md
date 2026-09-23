# Lamina

Lamina turns source collections into reference documents, guides, podcast scripts and assessments. It preserves source locations, divides independent work across model calls, and reuses completed work when inputs repeat.

Give it files, a description of the result, and a model adapter. It can write directly from the sources, create an outline from reusable source readings, or follow sections supplied by a person or another agent.

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
    "env": {
      "LAMINA_CONTEXT_TOKENS": "<documented model context limit>",
      "LAMINA_TOKENIZER": "<tiktoken encoding for the model>",
      "LAMINA_MAX_OUTPUT_TOKENS": "<chosen output allowance>"
    }
  }
}
```

Replace the three profile placeholders before starting: context and output limits are integer token counts; the tokenizer must match the selected model. [Adapters](docs/adapters.md) explains the measured prompt and framing allowance. Generic adapters without a model profile expose only the transport byte limit.

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

## What happens to the files

1. **Import their structure.** Markdown blocks, PDF pages and PowerPoint slide components retain their locations. Slide text, tables and speaker notes stay together during reading. Scanned PDFs can use local OCR.
2. **Choose a route that fits.** Automatic mode measures the actual writing request and the source context needed for review. A fitting collection goes directly to writing. Larger collections use source readers and a planner. Supplied assignments bypass those stages.
3. **Organize the material.** Reusable readers create an inventory of cited statements and relationships. Planning groups related material across files and assigns it to sections. Larger inventories use successive grouping stages; final assignment revisits the original inventory.
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
| Measurements and their scope | [Benchmarks](docs/benchmarks.md) |

Search imported sources with `lamina search 'blade design' --json`. Python callers use `build_production(workspace, provider, brief, source_ids, options)` or separate planning and writing calls.

## Limits

Source accounting and quotation matches establish traceability. Semantic completeness, writing quality and factual support need evaluation on the actual material. Whole structures or required context can exceed a model's capacity; those cases remain explicit errors or unperformed checks. The shared outline must still fit its planning request.

PDF figures and reading order need inspection. Assessments export separate candidate and examiner files; live oral-case delivery is unavailable. Audio requires a separate speech adapter and listening review. Keep the local app on loopback.

```sh
pip install -e '.[test,pdf,slides,http,tokens]'
python -m pytest -q
```
