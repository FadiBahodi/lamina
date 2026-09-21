# Lamina

[Try the interface](https://fadibahodi.github.io/lamina/) · [Technical paper](https://fadibahodi.github.io/lamina/assets/lamina-technical-paper.pdf) · [Download](https://github.com/FadiBahodi/lamina/releases/latest)

**A source-aware execution engine for agents that build documents, guides, scripts and assessments.**

Give Lamina a goal, a source collection and a model adapter. It reads the material in parallel, asks the model for a shared plan, gives each writer the evidence its section needs, and assembles the result. When a section needs correction, it can revise that section and reuse the rest.

The model makes the editorial decisions. Lamina controls source ownership, context, concurrent execution, saved results and delivery. It runs locally as a Python library, command-line tool or browser application. The public website includes recorded examples; your documents and model credentials belong in your local installation.

![Lamina project interface](docs/overview.png)

## Start a project

Requires Python 3.11 or newer.

```sh
git clone https://github.com/FadiBahodi/lamina.git
cd lamina
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[pdf]'
lamina app --workspace .lamina --port 8048
```

Open `http://127.0.0.1:8048` to inspect the included examples. To build from your own material, configure the [JSON command adapter](examples/adapter/README.md) and start the app with it:

```sh
lamina app --workspace .lamina --port 8048 \
  --adapter 'python examples/adapter/http_chat.py'
```

The **Projects** screen takes a goal and selected sources. It shows work in progress, the finished sections, their evidence, review findings and downloads. You can revise a named section and reopen saved projects after restarting the app. A stopped project can resume from its saved plan and completed jobs. Model credentials stay in the adapter process, outside the browser.

## What the engine does

1. **Read with boundaries.** A worker owns a core of ordered source units and sees neighboring units for context. It must anchor its ideas to exact quotations from its own core. Neighboring context does not confer ownership.
2. **Plan the whole result.** A model groups the extracted ideas into natural sections and explains any omissions. It identifies shared constraints and the earlier evidence each section needs. There is no fixed lesson count or question quota.
3. **Write in parallel.** Each writer receives its assignment, the common plan, exact local sources and selected prerequisite evidence. A planned section is explicitly distinguished from already-written prose.
4. **Review and repair locally.** Reviews identify concrete defects. A bounded repair pass rewrites the affected sections and checks them again. Remaining findings stay visible instead of triggering an indefinite rewrite loop.
5. **Keep useful work.** Requests are cached by their actual inputs and adapter identity. A targeted revision leaves unaffected requests reusable. The saved plan, execution report and output remain inspectable.

Reader, writer and reviewer concurrency are independently configurable from 1 to 128. A separate method runtime supports explicit dependency graphs and resource lanes for workflows that need different execution structures. Capacity is a limit, not a guarantee of speed: dependency depth, request size, rate limits and local contention still matter.

## Use it from an agent

The command line exposes the same source-aware production path as the app:

```sh
lamina ingest ./notes --workspace .lamina
lamina produce --workspace .lamina \
  --brief 'Write an incident guide for on-call engineers. Preserve exceptions and conflicting evidence.' \
  --format guide --readers 16 --writers 8 --reviewers 8 \
  --adapter 'python examples/adapter/http_chat.py' --output ./output/guide
```

The output directory contains a readable HTML document, Markdown, a saved plan and an execution report; installing the `pdf` extra adds a PDF. Assessment outputs have separate candidate and examiner documents. A script is text, not a rendered or audited audio file.

To revise one section, save a JSON object such as `{"section_3":"Explain the recovery exception using the existing source evidence."}` and run:

```sh
lamina produce --workspace .lamina --plan ./output/guide/plan.json \
  --section-notes ./revision.json \
  --adapter 'python examples/adapter/http_chat.py' --output ./output/revised
```

Python callers use the same functions:

```python
from lamina.store import Workspace
from lamina.production import plan_production, run_production
from lamina.production_export import export_production
from pathlib import Path

workspace = Workspace(Path('.lamina'))
source_ids = [s['id'] for s in workspace.sources() if s['role'] == 'teaching']
# provider.call(stage, request) returns a JSON object; provider.identity versions its behavior.
plan = plan_production(workspace, provider, 'Write an incident guide.', source_ids,
                       {'format': 'guide', 'reader_workers': 16})
receipt = run_production(workspace, provider, plan)
export_production(receipt, plan, Path('output/guide'))
```

The [production contract](docs/production.md) describes inputs, source boundaries, saved plans, evidence, revision and recovery. For arbitrary dependency graphs, see [methods](docs/methods.md) and the [technical brief example](examples/methods/technical-brief.md). An operator can attach retained observations to selected method nodes; the runtime does not automatically learn or choose the right method.

## Inspect a complete example

The [original engineering fixture](examples/production-example.json) runs the real production engine with deterministic responses. Two documents describe worker leases, fencing and incident logging. One writer deliberately makes a false inference; review identifies it and a local repair restores the missing distinction. A second run changes one section while reusing six of eight execution requests.

```sh
python examples/production/run.py --output output/example
python benchmarks/run_systems.py --units 64 --lessons 16 --widths 1 4 16 32
```

These examples establish execution, provenance checks and reuse. The scheduling benchmark uses controlled waits, not model inference. Neither establishes superior writing quality, learning outcomes or model latency. A [matched evaluation protocol](docs/measurement.md) defines what those stronger claims would require.

## Design and limits

The design draws on document extraction, differential-reference books, educational audio, question generation and staged oral-case systems. Each exposed a different failure: a qualifier lost at a page boundary, a valid variant erased during merging, parallel writers repeating one another, an answer leaked into a candidate brief, or finished text mistaken for verified media. [System origins](docs/system-origins.md) explains the mechanisms carried into Lamina and those still missing.

Current ingestion supports Markdown, text and PDFs with extractable text. It does not interpret figures or reconstruct complex table layout. Assessment sources are excluded from authoring. Exact-quote and assignment checks establish record consistency, not semantic truth or exhaustive source coverage. Candidate/examiner separation in exported files is not a cross-device examination server. The source-aware engine and the generic graph runtime share the workspace and adapter but remain distinct execution paths.

The [architecture status](docs/architecture-status.md) states the implemented boundaries. The [LaTeX paper](docs/paper/lamina.tex) develops source ownership, context amplification, work/span and resource bounds, repair cost and evaluation. Build it with `python tools/build_paper.py` after installing [Tectonic](https://tectonic-typesetting.github.io/).

## Development

```sh
python -m pip install -e '.[pdf,test]'
python -m pytest tests -q
python -m lamina.studio_site ./site --pdf
```

Maintained by Fadi Bahodi. [MIT license](LICENSE).
