# Source-aware production

Python, `lamina produce`, and local Projects use the same source-to-artifact engine in `production.py`.

## Inputs and planning

`plan_production(workspace, provider, brief, source_ids, options=None, progress=None)` returns a saved plan. The brief is text or `{goal, audience?, constraints?}`. Sources must exist in the workspace with the teaching role; held-out assessment sources cannot be selected.

| Setting | Range or values | Purpose |
| --- | --- | --- |
| `format` | `document`, `guide`, `podcast-script`, `assessment` | Output contract and review instructions. |
| `reader_workers`, `writer_workers`, `review_workers` | 1 to 128 each | Concurrent model-call limits. |
| `core_words` | 100 to 2000 | Target source-window size; indivisible units may be larger. |
| `halo_units` | 0 to 8 | Full neighboring units on each side, within the source. |
| `max_request_bytes` | 4096 to 2,000,000 | Reject oversized UTF-8 requests before the adapter call; not a token limit. |
| `source_policy` | Complete selected-source ID map: `authority`, `supplement`, `historical`, `form_exemplar` | How each teaching source may be used. Omission treats all as authorities. |
| `observation_ids` | Up to 20 distinct local IDs | Include selected observations from `method_family` in planning. |
| `method_family` | Lowercase slug | Observation scope; defaults to `document-production`. |
| `retrieval_targets` | `true` or `false`; `guide` or `assessment` only | Build a source-backed prompt and answer-group catalog before routing. Default `false`. |

Authority, supplement, and historical sources enter factual reading with their roles; historical claims may explain past practice or conflicts. Form exemplars guide structure but their facts and IDs stay out of factual reading and citations. Policy and selected observations are fixed in the plan. Code separates requests and evidence; reviewers assess how the model interpreted source roles.

On the CLI, `--source-policy` reads the complete ID-to-policy JSON map. Repeat `--observation-id` for selected notes and use `--method-family` for another family. These flags create a plan; a saved `--plan` fixes its policy and experience.

Readers own core units and may inspect neighboring halo units. New ideas cite core-owned evidence. The model selects useful ideas at the granularity the material calls for.

The planner uses extracted ideas, the goal, source metadata, form exemplars, and selected observations to choose sections and representations, record cited shared context, and assign or explain each extracted idea's omission. Representations specify kind, rationale, and requirements.

With `retrieval_targets=true`, `production_targets` runs between reading and routing. The model merges equivalent ideas, keeps variants and different contexts distinct, and groups prompts and answers. Each idea has one target; each member needs an answer item from exact quotes in its own units. The route assigns or explains each omission. Writers receive assigned targets. Selected targets appear in guide or examiner output; omissions and reasons stay in the plan and report. In assessments, the catalog appears in examiner and operator material. Enable this stage with `lamina produce --retrieval-targets` or the Projects checkbox.

Plans contain source units, identities, windows, ideas, assignments, and a digest. They are tied to source content and adapter identity; JSON edits break the digest. Replan after goal or source changes, and keep private-source plans private.

## Writing and revision

`run_production(workspace, provider, plan, options=None, progress=None)` gives each writer the route, its assigned evidence, and selected earlier evidence. Writers share planned earlier ideas and run within the configured capacity.

Review compares each section with its assignment, evidence, and representation through the configured model adapter. A concrete finding triggers one local repair and recheck. Remaining findings leave status `review` in the receipt.

Use `options={"section_notes":{"section_id":"requested change"}}` for a targeted revision. The note follows its section through repair; unchanged requests reuse cached work. Browser revisions retain earlier section notes, so a later edit elsewhere does not revert them.

Receipts record sections, citations, findings, sources, request bytes, cache outcomes, per-call time, provider overlap, and wall time including overhead.

## Delivery and recovery

`export_production(receipt, plan, output_path)` writes Markdown, readable HTML, JSON report, saved plan, and a formatted PDF when the `pdf` extra is installed. Assessments have separate candidate and examiner Markdown, HTML, and PDF. `document.*` is candidate-facing, with generic question headings; planned titles and answers stay in examiner/operator material. Reports and plans may contain keys, private titles, and source text.

Every assessment run calls `check_assessment(workspace, provider, plan, receipt, workers=8, progress=None)` after review and repair. A blind-answer request contains the current candidate section and earlier candidate sections. A separate judge sees that answer, candidate context, marking text, and exact cited excerpts, then returns typed findings in examiner/operator-only `receipt.assessment_checks`. Findings leave the run for review.

For a ready `podcast-script`, `render_audio(workspace, audio_provider, receipt, output_path, progress=None)` calls an optional command adapter. It returns WAV bytes and the text submitted to synthesis. Lamina accepts uncompressed PCM WAV up to 20 MB, checks structure and nonzero duration, and writes `narration.wav`, `narration.txt`, and `audio.json` with hashes and duration. A process-safe per-user file lock serializes uncached audio calls across local projects; cache hits skip the lock.

The CLI and local app configure audio at startup with optional `--audio-adapter` and `--audio-adapter-version`, separate from the model adapter. Without one, a podcast script remains text.

The local app persists project state beside artifacts. After restart, unfinished projects become `interrupted`; resume starts a new run with the saved plan when available and the exact-request cache. Completed requests survive; a model call that was interrupted restarts from its beginning. One project runs at a time, with parallel jobs inside it. SQLite uses renewable leases and owner-token fencing to prevent a superseded worker from committing over its replacement.

## HTTP interface

The server binds to loopback and accepts same-origin requests. Model and audio adapters are set at startup, never by a browser request. Status reports whether audio is configured.

- `POST /api/projects` with `{brief, source_ids, options}` starts a project.
- `GET /api/runs/{id}` returns progress, plan, receipt, and output links.
- `GET /api/projects` lists recent persisted projects.
- `POST /api/projects/{id}/revise` with `{section_notes}` starts a targeted revision.
- `POST /api/projects/{id}/resume` with `{}` resumes retained work.

Keep the local app on loopback. The hosted example replays fixtures and offers no visitor generation.

## Limits

Quote and ID checks establish provenance and membership, while source completeness, semantic support, equivalence of retrieval targets, question quality, and factual truth still require review. Model judgments can be wrong; separate candidate and examiner calls do not guarantee that a stateful provider has forgotten earlier context or that answers stayed out of candidate fields. This is an exported assessment, not live oral-case delivery.

Request bytes are measured UTF-8 size, not billed tokens or provider cost. `narration.txt` records the speech adapter's synthesis input, not recognized speech. WAV structure and duration checks do not establish pronunciation, spoken fidelity, pacing, educational quality, or device playback. Lamina does not yet provide ROUNDS' full audio factory or listened audio audit.

The local queue uses leases and fencing within one app; an external provider may still have performed an effect before an interrupted call. Run IDs are not authorization tokens, so the local app must stay off public networks. This release does not include figure interpretation, PDF vision, a differential atlas, staged oral-case delivery, independent semantic verification, or automatic method learning. [System origins](system-origins.md) maps the remaining mechanisms.
