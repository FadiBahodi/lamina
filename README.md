# Lamina

[Try the interface](https://fadibahodi.github.io/lamina/) · [Technical paper](https://fadibahodi.github.io/lamina/assets/lamina-technical-paper.pdf) · [Download](https://github.com/FadiBahodi/lamina/releases/latest)

Lamina is a framework for agents that turn source collections into documents, guides, scripts and assessments. It reads in parallel, builds a shared plan, gives each writer the evidence it needs, and assembles the result. You can revise one section and reuse the rest.

The design grew out of long-running work on reference books, educational audio and examination cases. Those projects repeatedly lost qualifiers during extraction, merged questions that needed different answers, or forced a complete rebuild to fix one section. Lamina carries the resulting source, coordination and repair mechanisms into a reusable engine. [System origins](docs/system-origins.md) describes that history.

Models decide how to group and explain the material. Lamina manages source identity, evidence, scheduling, saved results and delivery. It runs locally through Python, a command line or a browser app. The public website contains recorded examples.

![Lamina project interface](docs/overview.png)

## How it works

1. Readers work on assigned passages with neighboring text for context. Each extracted idea cites a quotation from its assigned passage.
2. A planner groups the ideas into sections, records omissions, and identifies the evidence each writer needs. Section counts and formats follow the task.
3. Writers run in parallel with the shared plan and their source material. Review identifies defects, then one repair pass revises and rechecks the affected sections. Unresolved findings stay visible.
4. The engine saves the plan, output and execution report. Cache keys include request inputs and adapter identity, so unchanged work can be reused after a revision or interruption.

Reading, writing and review each support 1 to 128 concurrent calls. Dependency depth, request size, provider limits and resource contention determine elapsed time. For workflows with custom dependencies or resource limits, the [method runtime](docs/methods.md) executes a graph of jobs using the same workspace and adapter.

Sources can serve as authorities, supplements, historical references or examples of form. Form examples guide planning and stay out of factual citations; held-out assessments stay out of authoring. You can also select saved project notes for the next plan.

Guides and assessments can merge equivalent questions while preserving answer groups and useful variants. Every assessment includes a blind solve using the current and earlier candidate information, followed by a judge with the marking guide and source evidence. Candidate and examiner files are exported separately.

## Run it

Requires Python 3.11 or newer.

```sh
git clone https://github.com/FadiBahodi/lamina.git
cd lamina
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[pdf]'
lamina app --workspace .lamina --port 8048
```

Open `http://127.0.0.1:8048` to run the included example. For your own sources, configure the [JSON command adapter](examples/adapter/README.md):

```sh
lamina app --workspace .lamina --port 8048 \
  --adapter 'python examples/adapter/http_chat.py'
```

Projects shows the source selection, progress, finished sections, evidence and downloads. Saved projects reopen after a restart; interrupted runs resume from their plan and completed jobs. Credentials stay in the adapter process, outside the browser.

## Use it from an agent

The CLI calls the same engine as the app:

```sh
lamina ingest ./notes --workspace .lamina
lamina produce --workspace .lamina \
  --brief 'Write an incident guide for on-call engineers. Preserve exceptions and conflicting evidence.' \
  --format guide --readers 16 --writers 8 --reviewers 8 \
  --adapter 'python examples/adapter/http_chat.py' --output ./output/guide
```

The result includes HTML, Markdown, a saved plan and an execution report. The `pdf` extra adds formatted PDFs. Assessments use numbered candidate headings and export marking answers in separate examiner files. Plans and reports may contain private source text and answer keys.

Use `--source-policy` with a JSON map from each selected source ID to `authority`, `supplement`, `historical` or `form_exemplar`; the default is `authority`. Repeat `--observation-id` for up to 20 saved notes from `--method-family` (default `document-production`). Source policy and notes are fixed in the saved plan; changing them requires a new plan.

`--retrieval-targets`, also available in Projects, groups questions before writing a guide or assessment. Each extracted idea belongs to one target with cited answer items. Assigned targets appear in the guide or examiner file; omissions and their reasons stay in the plan and report. The [question-merging example](examples/retrieval-targets/README.md) shows duplicate consolidation and the same answer preserved in a different context. The [source-policy example](examples/source-policy/demo.py) shows authority, historical references, form examples and saved notes.

For audio, add `--audio-adapter` and optionally `--audio-adapter-version` to `lamina produce` or `lamina app`. A ready `podcast-script` becomes `narration.wav`, `narration.txt` and `audio.json`. The [local speech adapter](examples/audio/local_speech.py) uses macOS `say` and `afconvert`, or Linux `espeak`. A process-safe local lock serializes uncached speech calls. The app reports whether audio is configured; adapters are set at startup. With no audio adapter, the output is a script.

To revise a section, save a JSON object such as `{"section_3":"Explain the recovery exception using the existing source evidence."}` and run:

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

See the [production contract](docs/production.md) for the API and the [technical brief example](examples/methods/technical-brief.md) for a custom job graph.

## Examples and measurements

The [engineering fixture](examples/production-example.json) uses fixed responses to exercise the production engine. Two documents describe leases, fencing and incident logging. A writer introduces an error, review catches it, and repair corrects the section. A second run revises one section and reuses six of eight requests.

```sh
python examples/production/run.py --output output/example
python benchmarks/run_systems.py --units 64 --lessons 16 --widths 1 4 16 32
```

The fixtures demonstrate source tracking, caching and selective repair. The scheduler benchmark uses controlled waits. The [evaluation protocol](docs/measurement.md) covers model quality, latency, cost and learning outcomes.

## Limits

Ingestion reads Markdown, text and PDFs with extractable text; figures, scans and complex table layouts need further processing. Source quotations and assignments are checked mechanically. Extraction coverage, interpretation and question quality still need review.

Assessments are exported files, with no live examination server. Blind-solve calls isolate the supplied inputs; providers may retain state. Audio checks cover PCM structure, nonzero duration, hashes and timing. The transcript records synthesis input; spoken fidelity and pronunciation need listening or transcription checks.

Saved notes are selected by the user. Lamina has no autonomous method selection or training. Production and custom graphs share infrastructure but have different contracts. The [architecture status](docs/architecture-status.md) records those details.

## Technical details and development

The [LaTeX paper](docs/paper/lamina.tex) covers source ownership, context amplification, work/span, resource bounds and repair cost. Build it with `python tools/build_paper.py` after installing [Tectonic](https://tectonic-typesetting.github.io/).

```sh
python -m pip install -e '.[pdf,test]'
python -m pytest tests -q
python -m lamina.studio_site ./site --pdf
```

Maintained by Fadi Bahodi. [MIT license](LICENSE).
