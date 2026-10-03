# Lamina

[Website](https://fadibahodi.github.io/lamina/) · [Releases](https://github.com/FadiBahodi/lamina/releases/latest) · [Documentation](docs/README.md)

Lamina is a Python library, command-line tool and local web app for turning source files into flashcards, reference guides, podcast scripts and audio, or practice exams. You supply the files, the goal and a model adapter. Lamina divides the work, runs independent model calls in parallel, preserves source references, and saves results for recovery and revision.

Readers work from original passages. Writers receive assigned evidence and shared context. Each section can move into review while others are still being written. Failed reads and unresolved findings stay visible in the saved plan and receipt.

## Install

Requires Python 3.11+ and SQLite with FTS5.

```sh
git clone https://github.com/FadiBahodi/lamina.git
cd lamina
python -m venv .venv
source .venv/bin/activate
pip install -e '.[pdf,slides,http,tokens]'
```

## Connect a model

Generation requires your own model endpoint and credentials. For a chat-completions-compatible endpoint, set its connection details:

```sh
export LAMINA_API_BASE="https://your-provider.example/v1"
export LAMINA_MODEL="your-model"
export LAMINA_API_KEY="your-key"
```

Save this as `models.json` in the repository root:

```json
{
  "default": {
    "transport": "jsonl",
    "command": ["python", "examples/adapter/http_service.py"],
    "request_format": "lamina-chat-1",
    "workload": "starter",
    "version": "my-model-1"
  }
}
```

The [adapter guide](docs/adapters.md) covers other providers, per-stage model selection and request limits. Starter limits are initial settings to evaluate on your material.

## Use it

Start the local app and open `http://127.0.0.1:8048`:

```sh
lamina app --workspace .lamina --adapter @models.json
```

Or ingest files and generate from the CLI:

```sh
lamina ingest --workspace .lamina chapter.pdf slides.pptx
lamina produce --workspace .lamina --adapter @models.json \
  --format guide --brief "An answered reference guide with conditions and exceptions"
```

Use `--format cards` for an Anki-importable deck, `podcast-script` for episodes, or `assessment` for separate candidate and examiner material. Audio also requires a [speech adapter](docs/adapters.md#speech-resources). Document exports include Markdown, HTML and optional PDF, alongside the plan and receipt. See [Production](docs/production.md) for source selection, options, revisions and Python usage.

The website contains installation instructions and documentation. Model runs use the installed app or CLI; selected source text goes to the configured model service.

## How the code fits together

- [`source_reading.py`](src/lamina/source_reading.py) reads bounded original passages and preserves exact source references.
- [`planning.py`](src/lamina/planning.py) groups material and assigns it to sections; [`production.py`](src/lamina/production.py) runs writing and review.
- [`execution.py`](src/lamina/execution.py), [`call_runtime.py`](src/lamina/call_runtime.py) and [`store.py`](src/lamina/store.py) schedule work, enforce limits and cache validated results.
- [`evidence_relations.py`](src/lamina/evidence_relations.py) compares related claims and can reopen original material omitted by extraction.
- [`method_runtime.py`](src/lamina/method_runtime.py) runs custom dependency graphs with selected observations from earlier work.

[Architecture](docs/architecture.md) explains these contracts. [Workflow design](docs/workflow-design.md) covers the different needs of references, audio and exams; [system origins](docs/system-origins.md) preserves their history.

## Limits

Models can omit qualifications or misinterpret real citations. Parsing does not reliably interpret figures, and generated audio needs listening review. Workload settings and cached results do not establish quality. Assessments are exported materials; live oral-case administration requires a separate application. Custom methods execute declared workflows and reuse selected observations without automatically discovering better methods. [Capability status](docs/architecture-status.md) lists the remaining limits; [live model results](docs/live-model-evaluation.md) records measured successes and failures.

## Contribute

```sh
pip install -e '.[test,pdf,slides,http,tokens]'
python -m pytest -q
```

Keep source permissions, exact evidence, independent scheduling and recovery intact when changing a workflow. See [AGENTS.md](AGENTS.md) for repository conventions.
