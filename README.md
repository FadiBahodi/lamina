# Lamina

[Design paper (PDF)](https://fadibahodi.github.io/lamina/assets/lamina-technical-paper.pdf) · [Interactive design and workbench](https://fadibahodi.github.io/lamina/) · [Download v0.4](https://github.com/FadiBahodi/lamina/releases/tag/v0.4.1)

Lamina is an open-source Python engine for document production workflows. You give it source material and an adapter to a model. The model reads, plans, and writes. Lamina defines what each call receives, schedules independent jobs, and reuses completed results when their inputs have not changed. Its guide pipeline also carries source references into the finished work.

The first working application turns documents into a source-linked guide with optional practice questions, a local reader, and print exports. A method workbench imports and runs custom graphs of jobs from JSON, displays each node’s result, and attaches review notes to later runs. They share the adapter and SQLite workspace, but the guide builder does not yet run on a user-defined method graph. [Architecture status](docs/architecture-status.md) maps that boundary and the next integration choices.

![Sources, guide, and method execution in Lamina](docs/overview.png)

This matters most when the source collection or the brief changes. A team may need to update a guide after one policy page changes, reuse the rest of the work, and see which passages support the new output. Lamina keeps stage results and source locations so the team can inspect that revision. It does not currently decide whether every important source fact was found or whether the finished guide is effective.

## Run it locally

Python 3.11 or newer is required. The local app includes a curated offline example. To process your own documents, start it with an adapter that you configure outside the browser.

```sh
git clone https://github.com/FadiBahodi/lamina.git
cd lamina
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[pdf]'
lamina app --workspace .lamina --port 8048
```

Open `http://127.0.0.1:8048`. On Windows, activate the environment with `.venv\Scripts\activate`. For model-backed generation, configure the example [JSON command adapter](examples/adapter/README.md), then start the app with it:

```sh
lamina app --workspace .lamina --port 8048 \
  --adapter 'python examples/adapter/http_chat.py'
```

The public [interactive example](https://fadibahodi.github.io/lamina/) includes a method editor and recorded executions; actual model calls run in the downloaded local application. It uses original engineering material and curated output, so it shows the reader and inspection path without claiming that arbitrary uploads were generated on the hosted site. The local app accepts Markdown, text, and PDFs with extractable text. It keeps model credentials in the adapter's process configuration.

## Build a guide from documents

The command line exposes the same guide pipeline. `ingest` stores source hashes, locators, and text units. `build` asks the configured adapter to extract ideas, reconcile overlaps, plan lessons, write them, and review them. `export` renders the validated bundle.

```sh
lamina ingest ./notes --workspace .lamina
lamina search 'worker leases' --workspace .lamina
lamina build --workspace .lamina \
  --adapter 'python examples/adapter/http_chat.py' --output ./site
lamina export ./site/bundle.json --format pdf --output ./guide.pdf
lamina export ./site/bundle.json --format markdown --output ./guide.md
```

Use `lamina ingest ./questions.md --workspace .lamina --role assessment` to keep evaluation material out of authoring and the public bundle. This is a source-role boundary, not an automatic exam-validity check. PDF import extracts text and rejects image-only pages; it does not interpret diagrams or table layout. The PDF export in the example requires the `pdf` installation extra.

For a build with no model account, run `lamina demo --output ./demo`, then `lamina serve ./demo --port 8000`. That demo is a fixture for the bundled field guide. [Pipeline architecture](docs/architecture.md) explains the stages and the exact checks applied to their outputs.

## Run a reusable method

A method file declares jobs, their dependencies, selected task fields, and limits on concurrent work. A job sees its own assignment and the completed results of its stated prerequisites. The method runner saves a receipt showing which jobs ran, used a cached result, failed, or were skipped. Changing one branch of a task can leave an unrelated branch cached.

```sh
lamina method validate examples/methods/field-guide.json
python examples/methods/demo.py
```

In the browser, **Workbench → Custom workflow** lets you import a method, edit a task, inspect the graph, run it, and attach a review note to a subsequent run. The [technical brief example](examples/methods/technical-brief.md) uses two readers, a shared reconciliation step, two parallel writers, and a reviewer.

The offline example reads site notes and plant notes independently, then joins them into a volunteer guide. It runs again with changed site notes to show selective reuse. To call your own adapter, create a task JSON file with `site_notes`, `plant_notes`, and `audience`, then run:

```sh
lamina method run --method examples/methods/field-guide.json \
  --task ./my-visit.json --workspace .lamina \
  --adapter 'python examples/adapter/http_chat.py' --output ./run.json
```

The example adapter needs a compatible endpoint, model, and credentials supplied through environment variables. [Methods](docs/methods.md) documents the request shape, cache identity, receipt, and observation commands. An operator can select a previously recorded observation for a particular method node so that the next run receives it as context. The operator chooses which observation applies; Lamina does not select or revise methods automatically.

The guide builder and generic method runner remain separate. The local browser app uses a fixed source-to-guide pipeline and configurable output procedures. Custom method graphs run from the command line or the local browser workbench. The workbench accepts a method and task, validates the graph, runs the configured adapter, displays execution receipts, and lets an operator attach a review note for a subsequent run. A generic graph does not inherit the guide pipeline's source and citation checks merely because it uses the same adapter.

## What is checked

For the guide, Lamina records the original file hash and accepted text locations. Extracted ideas need exact source quotes. Reconciliation accounts for each extracted idea, and the plan assigns or defers each reconciled idea. A review response can block export. These checks make omissions and bad merges easier to inspect, but they cannot show that parsing captured every figure, that extraction found every important point, or that a quote supports the writer's interpretation. The configured reviewer is another adapter call, not an independent expert.

The method runner validates its job graph and resource limits. Its generic jobs only have to return JSON objects. The runtime does not verify the meaning or suitability of those objects. Local SQLite jobs support cached reuse and recovery after interruption, though active browser-run status is held in memory and does not automatically resume after an app restart. The reader's Listen view contains a script and optional browser speech; Lamina does not produce or audit podcast files.

The [architecture status](docs/architecture-status.md) distinguishes these working pieces from the open design choices. [Design constraints](docs/design-constraints.md) explains why source boundaries, worker context, editorial selection, repair, and delivery matter. [Measurement](docs/measurement.md) sets out a quality-matched test of reuse, speed, cost, and correction on new material. The [systems benchmark](docs/benchmarks.md) measures synthetic scheduling and cache behavior; it is not a model-production or learning-quality result.

## Technical paper

The [engineering design paper](docs/technical-paper.md) describes source policy, representation choices, worker context, dependency types, selective repair, and the experiments needed to evaluate reuse on new tasks. It separates the proposed integrated system from the working reference implementation. The [recorded runtime experiment](docs/experiments/README.md) is reproducible without a model account.

Rebuild the paper with `python tools/build_paper.py` after installing the `pdf` extra.

## Development

```sh
python -m pip install -e '.[pdf,test]'
python -m pytest tests -q
```

Tests cover source and evidence contracts, cache behavior, dependency execution, recovery, and exports. The project is maintained by Fadi Bahodi and released under the [MIT License](LICENSE).
