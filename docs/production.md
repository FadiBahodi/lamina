# Source-aware production

The production engine plans work from a goal and selected source material. Python, `lamina produce` and the local Projects interface call the same implementation in `production.py`.

## Inputs and planning

`plan_production(workspace, provider, brief, source_ids, options=None, progress=None)` returns a saved plan. The brief is text or `{goal, audience?, constraints?}`. Selected sources must exist in the workspace and have the teaching role. Held-out assessment sources cannot be selected.

Options include:

| Setting | Range or values | Purpose |
| --- | --- | --- |
| `format` | `document`, `guide`, `podcast-script`, `assessment` | Sets the output contract and review instructions. |
| `reader_workers`, `writer_workers`, `review_workers` | 1–128 each | Separate upper bounds on concurrent model calls. |
| `core_words` | 100–2000 | Target source-window size; indivisible units may be larger. |
| `halo_units` | 0–8 | Full neighboring units on each side, within the same source. |
| `max_request_bytes` | 4096–2,000,000 | Reject oversized UTF-8 request envelopes before invoking an adapter. This is not a token limit. |
| `source_policy` | A map covering every selected source ID: `authority`, `supplement`, `historical`, or `form_exemplar` | Sets how each teaching source may inform the result. Omit it to treat all selected teaching sources as authorities. |
| `observation_ids` | Up to 20 distinct local IDs | Explicitly put operator observations from the chosen method family into planning context. |
| `method_family` | Lowercase slug | Scopes selected observations; defaults to `document-production`. |
| `retrieval_targets` | `true` or `false`, for `guide` or `assessment` | Build a source-backed catalog of retrieval prompts and answer groups before routing sections. Default `false`. |

Authority, supplement and historical sources are read as factual material, with their assigned policy in the reader and planning requests. Historical text can explain a prior claim or conflict; it is not automatically current authority. A form exemplar contributes bounded structure guidance to planning but does not enter factual reading or citation. The code enforces that separation of requests and exact evidence IDs. It cannot prove that a model interpreted authority correctly or copied no inappropriate detail from an exemplar. The saved plan records source policy and selected observations; changing either requires a new plan. Observation selection is manual, not automatic learning or ranking.

On the command line, `--source-policy` reads the complete ID-to-policy map from a JSON file; repeat `--observation-id` to select local notes and use `--method-family` when they belong to another family. These flags create a new plan. A saved `--plan` already fixes the source policy and selected experience.

A reader owns its core units. It can inspect the halo but may cite only core-owned evidence as a newly extracted idea. The model chooses useful ideas; the code does not require one idea per unit. Each idea includes exact source quotations. This validates provenance, not extraction completeness or semantic support.

A global planner sees the extracted ideas, goal, source metadata, bounded form exemplars and any operator-selected observations. It returns natural sections, a representation for each section, shared evidence-backed context and an explicit reason for each omitted idea. Representation includes a kind, rationale and requirements: a mechanism explanation, comparison, procedure or scenario can require different treatment. Every extracted idea is assigned once or explicitly omitted. This accounting begins after extraction; it cannot discover an idea the reader missed.

With `retrieval_targets=true`, a `production_targets` stage runs after reading and before the section route. The model proposes canonical questions or use contexts, decides which extracted ideas are equivalent or variants, and groups their answers. Code requires each extracted idea to have exactly one target owner; every member idea must retain an answer item with exact source text and citations to its own units. Related targets can be linked as variants or different contexts without merging them. The section route assigns each target to one section or explicitly omits it. Writers receive their assigned targets. Only assigned targets are appended to a guide or the examiner assessment file; deliberately omitted targets and reasons remain in the plan and report, never the candidate file. These checks establish membership and exact-source preservation, not semantic equivalence, complete extraction or a good teaching question. Enable this from `lamina produce --retrieval-targets` or the Projects checkbox.

The saved plan includes original source units, source identities, windows, ideas, assignments and a digest. Keep it private when it contains private source text. A plan is bound to its workspace source content and adapter identity. Editing its JSON invalidates the digest; changing the goal or source collection requires planning again.

## Writing, checking and revision

`run_production(workspace, provider, plan, options=None, progress=None)` sends writers the common route, assigned source evidence and only the earlier evidence selected by the plan. Earlier planned ideas are not completed prose. Writers execute concurrently within the configured capacity.

Reviews compare each draft with its source packet, assignment and representation requirements. Concrete findings lead to one local repair and another check of that section. Outstanding findings produce status `review`; they remain visible in the returned report. There is no claim of independent expert review or guaranteed truth.

A revision uses `options={"section_notes":{"section_id":"requested change"}}`. The note changes the selected writer request and follows that section through repair. Unchanged sections reuse cached requests. A revision of a revision in the browser retains previous section notes, so an unrelated later edit does not silently revert earlier work.

The receipt includes authored sections, exact evidence, initial and remaining findings, source metadata and execution metrics. It records request bytes, cached versus executed requests, per-request elapsed time and observed provider overlap. Wall time includes local scheduling and cache overhead. Byte counts are neither tokens nor monetary costs.

## Delivery and recovery

`export_production(receipt, plan, output_path)` writes Markdown, safe readable HTML, a JSON report, the saved plan and, with the `pdf` extra installed, a formatted PDF. Assessment output has separate candidate and examiner Markdown, HTML and PDF artifacts. `document.*` is candidate-facing for assessments. Candidate headings are generic question numbers; private planned titles and answers remain in examiner/operator materials. The report and saved plan can contain keys, source text and private titles. File separation is not authenticated live case delivery or proof that a model never put an answer in a candidate field.

Every assessment production run calls `check_assessment(workspace, provider, plan, receipt, workers=8, progress=None)` after the section review and repair pass. Each blind-answer request contains only the current candidate section and earlier candidate sections, with no key, evidence, private planned title or future section. The separate judge sees that answer, the candidate context, marking text and exact cited excerpts, and returns typed findings. Results are recorded in `receipt.assessment_checks` for examiner/operator use. A flagged check leaves the run for review. These are separate provider calls, not a guarantee against hidden state retained by a provider and not a live oral examination.

For a ready `podcast-script` receipt, `render_audio(workspace, audio_provider, receipt, output_path, progress=None)` can invoke a separately configured command adapter. The adapter returns WAV bytes and the text submitted to synthesis. Lamina accepts uncompressed PCM WAV up to 20 MB, checks its structure and nonzero duration, and writes `narration.wav`, `narration.txt` and `audio.json` with hashes and duration. One process-safe, per-local-user file lock serializes uncached audio adapter calls across local projects; a cache hit skips that lock. The lock is a renderer resource boundary, not a claim that all model work is serial. `narration.txt` is adapter-reported synthesis input, not an ASR transcript. Lamina has not listened to or checked pronunciation, word fidelity, pacing or educational quality.

The CLI and local app accept an optional `--audio-adapter` command and `--audio-adapter-version`. These are startup configuration, separate from the model adapter. If none is configured, the podcast-script artifact remains text.

The local app persists project state beside its artifacts. On restart, unfinished projects become `interrupted`. Resume creates a new run using the saved plan if available and the same exact-request cache. It does not resume a model process mid-call. A failed request can be attempted again; completed requests remain reusable. The app allows one active project at a time, with parallel jobs inside it.

The job cache uses SQLite, renewable leases and owner-token fencing. It prevents a superseded worker from committing over its replacement. It does not prevent an external provider from having performed an effect before a process failed, and does not turn a local workspace into a distributed queue.

## HTTP interface

The server binds to loopback and accepts same-origin requests. The model and optional audio adapters are configured at process startup, never supplied by a browser request. The app status reports whether audio is configured.

- `POST /api/projects` with `{brief, source_ids, options}` starts a project.
- `GET /api/runs/{id}` returns progress, plan, receipt and output links when available.
- `GET /api/projects` lists recent persisted projects.
- `POST /api/projects/{id}/revise` with `{section_notes}` starts a targeted revision.
- `POST /api/projects/{id}/resume` with `{}` resumes from retained work.

Run IDs identify local outputs, not authorization tokens. Do not expose this local app directly to a public network. A hosted static example replays original fixture content; it cannot use a visitor's model account or generate new material.

## Scope

This release connects source-aware text production, explicit source roles, automatic blind checking for assessment runs and optional local PCM rendering. It does not reproduce an entire audio factory, PDF vision pipeline, differential atlas or live oral-case system. There is no automatic figure interpretation, staged examiner-controlled reveal, independent semantic truth check, listened audio audit or automatic method learning. [System origins](system-origins.md) distinguishes those mechanisms from the ones implemented here.
