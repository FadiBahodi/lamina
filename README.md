# Lamina

Lamina turns source documents into guides, reference documents, podcast scripts and assessments. It keeps source references, runs independent work concurrently, and reuses completed work after a revision or interruption.

Give it your files, the result you want, and a model adapter. Small inputs go directly to a writer and review. Larger inputs use readers and a planner. An outer agent can supply its own section-to-source assignments and skip both steps.

## Install and run

Python 3.11+ and SQLite with FTS5 are required.

```sh
git clone https://github.com/FadiBahodi/lamina.git
cd lamina
pip install -e '.[pdf,slides]'
lamina ingest ./sources --workspace .lamina
lamina app --workspace .lamina --adapter 'python examples/adapter/http_chat.py'
```

Set `LAMINA_API_BASE`, `LAMINA_MODEL` and `LAMINA_API_KEY` for the example adapter. Open `http://127.0.0.1:8048`. Credentials stay in the local adapter process. The model provider receives the selected source context.

The same workflow is available from the command line:

```sh
lamina produce --workspace .lamina \
  --brief 'Explain windmill blade designs, preserving where the sources disagree.' \
  --format guide --workers 8 \
  --adapter 'python examples/adapter/http_chat.py' --output output/windmills
```

With no adapter, `lamina app` offers a recorded example. `lamina demo --output demo` runs a separate deterministic legacy guide fixture offline.

## How it works

1. **Read files.** Import Markdown, text, PDF text and PowerPoint text, tables and speaker notes. Keep locations and structural boundaries. Optional local OCR handles scanned PDFs.
2. **Choose the work.** Automatic mode writes directly from small inputs. The planned route extracts source-backed ideas and assigns them to sections. Supplied source assignments bypass that planning.
3. **Write and check.** Writers receive their assigned evidence and required context. Each section enters review when it finishes. A concrete finding can trigger one repair and recheck.
4. **Deliver and reuse.** Export Markdown, HTML, PDF, source references and execution records. Revise one section while unchanged requests stay cached.

One shared limit controls simultaneous model calls. It is a capacity limit; it does not decide how to divide the subject. Models or the calling agent make that decision. Different stages can use different configured models.

```python
from lamina.production import build_production
from lamina.providers import configured_provider
from lamina.store import Workspace

workspace = Workspace('.lamina')
provider = configured_provider('models.json')
sources = [s['id'] for s in workspace.sources() if s['role'] == 'teaching']
result = build_production(workspace, provider, 'Compare these designs', sources)
print(result['markdown'])
```

## Interfaces

| Need | Documentation |
| --- | --- |
| Workflows, source assignments and revision | [Production](docs/production.md) |
| Per-stage models, context budgets and usage | [Adapters](docs/adapters.md) |
| File structure, OCR and parser choices | [Parsing](docs/parsing.md) |
| Source search | `lamina search 'blade design' --json` |
| Custom dependencies and resource lanes | [Methods](docs/methods.md) |
| Runtime design and mathematical scope | [Architecture](docs/architecture.md) |
| Reproducible measurements | [Benchmarks](docs/benchmarks.md) |

## Limits

Exact quotes establish source occurrence, not correctness or completeness. Review is a model judgment. PDF text extraction and OCR do not interpret arbitrary figures or guarantee reading order. Automatic planning still has a bounded global step; large projects can supply source assignments. Input size selects a route, not a difficulty score. Live quality, cost and latency require evaluation with the chosen models and sources.

Assessment prompts and marking guides are separate exports. Interactive oral-case delivery remains unimplemented. Podcast scripts need a separate speech adapter for WAV output; file checks do not establish listening quality. Keep the local app on loopback.

```sh
pip install -e '.[test,pdf,slides]'
python -m pytest -q
```
