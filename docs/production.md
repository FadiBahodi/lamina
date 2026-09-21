# Source-aware production

The production engine plans work from a goal and selected source material. Python, `lamina produce` and the local Projects interface call the same implementation in `production.py`.

## Inputs and planning

`plan_production(workspace, provider, brief, source_ids, options=None, progress=None)` returns a saved plan. The brief is text or `{goal, audience?, constraints?}`. Sources must exist in the workspace and have the teaching role. Held-out assessment sources cannot be selected.

Options include:

| Setting | Range or values | Purpose |
| --- | --- | --- |
| `format` | `document`, `guide`, `podcast-script`, `assessment` | Sets the output contract and review instructions. |
| `reader_workers`, `writer_workers`, `review_workers` | 1–128 each | Separate upper bounds on concurrent model calls. |
| `core_words` | 100–2000 | Target source-window size; indivisible units may be larger. |
| `halo_units` | 0–8 | Full neighboring units on each side, within the same source. |
| `max_request_bytes` | 4096–2,000,000 | Reject oversized UTF-8 request envelopes before invoking an adapter. This is not a token limit. |

A reader owns its core units. It can inspect the halo but may cite only core-owned evidence as a newly extracted idea. The model chooses useful ideas; the code does not require one idea per unit. Each idea includes exact source quotations. This validates provenance, not extraction completeness or semantic support.

A global planner sees the extracted ideas, goal and source metadata. It returns natural sections, a representation for each section, shared evidence-backed context and an explicit reason for each omitted idea. Representation includes a kind, rationale and requirements: a mechanism explanation, comparison, procedure or scenario can require different treatment. Every extracted idea is assigned once or explicitly omitted. This accounting begins after extraction; it cannot discover an idea the reader missed.

The saved plan includes original source units, source identities, windows, ideas, assignments and a digest. Keep it private when it contains private source text. A plan is bound to its workspace source content and adapter identity. Editing its JSON invalidates the digest; changing the goal or source collection requires planning again.

## Writing, checking and revision

`run_production(workspace, provider, plan, options=None, progress=None)` sends writers the common route, assigned source evidence and only the earlier evidence selected by the plan. Earlier planned ideas are not completed prose. Writers execute concurrently within the configured capacity.

Reviews compare each draft with its source packet, assignment and representation requirements. Concrete findings lead to one local repair and another check of that section. Outstanding findings produce status `review`; they remain visible in the returned report. There is no claim of independent expert review or guaranteed truth.

A revision uses `options={"section_notes":{"section_id":"requested change"}}`. The note changes the selected writer request and follows that section through repair. Unchanged sections reuse cached requests. A revision of a revision in the browser retains previous section notes, so an unrelated later edit does not silently revert earlier work.

The receipt includes authored sections, exact evidence, initial and remaining findings, source metadata and execution metrics. It records request bytes, cached versus executed requests, per-request elapsed time and observed provider overlap. Wall time includes local scheduling and cache overhead. Byte counts are neither tokens nor monetary costs.

## Delivery and recovery

`export_production(receipt, plan, output_path)` writes Markdown, safe readable HTML, a JSON report, the saved plan and an optional PDF. Assessment output has separate candidate and examiner artifacts; the general document is candidate-only. The report and saved plan are examiner/developer materials and can contain answers. This is file separation, not authenticated live case delivery or a guarantee that a model never put an answer in a candidate field.

The local app persists project state beside its artifacts. On restart, unfinished projects become `interrupted`. Resume creates a new run using the saved plan if available and the same exact-request cache. It does not resume a model process mid-call. A failed request can be attempted again; completed requests remain reusable. The app allows one active project at a time, with parallel jobs inside it.

The job cache uses SQLite, renewable leases and owner-token fencing. It prevents a superseded worker from committing over its replacement. It does not prevent an external provider from having performed an effect before a process failed, and does not turn a local workspace into a distributed queue.

## HTTP interface

The server binds to loopback and accepts same-origin requests. The model adapter is configured at process startup, never supplied by a browser request.

- `POST /api/projects` with `{brief, source_ids, options}` starts a project.
- `GET /api/runs/{id}` returns progress, plan, receipt and output links when available.
- `GET /api/projects` lists recent persisted projects.
- `POST /api/projects/{id}/revise` with `{section_notes}` starts a targeted revision.
- `POST /api/projects/{id}/resume` with `{}` resumes from retained work.

Run IDs identify local outputs, not authorization tokens. Do not expose this local app directly to a public network. A hosted static example replays original fixture content; it cannot use a visitor's model account or generate new material.

## Scope

This release implements source-aware text production. It does not reproduce the entire audio factory, PDF vision pipeline, differential atlas or live oral-case system. In particular, there is no automatic figure interpretation, form-exemplar source role, staged examiner-controlled reveal, blind candidate solve, audio rendering or audio delivery audit. [System origins](system-origins.md) retains these as specific mechanisms rather than silently treating them as covered by generic writing.
