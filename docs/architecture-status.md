# Architecture status

Lamina v0.6 connects a source-aware production engine to a local project interface, CLI, exports and persisted recovery. Source roles, assessment checking on every assessment run, and optional local audio rendering extend that production path. The generic method runtime remains available for explicitly declared dependency graphs. These paths share source storage, adapter conventions and the exact-request job cache; they are not interchangeable.

| Mechanism | Implemented behavior | Boundary |
| --- | --- | --- |
| Source ingestion | Hashed Markdown, text and extractable PDF text with ordered locations. | No OCR, image interpretation or table reconstruction. |
| Source policy | An operator assigns authority, supplement, historical or form-exemplar use to each selected teaching source. Form exemplars are kept out of factual reading and citations. | The model's interpretation of authority and style still needs review; held-out assessment sources remain excluded. |
| Parallel reading | Owned core units with full neighboring-unit context; exact quotes and core ownership checked. | Large indivisible units may exceed target window size; oversized requests fail explicitly. |
| Global planning | Model chooses section count, grouping, representation, selected prerequisite evidence and omissions. | Coverage starts at extracted ideas; missed source meaning is not detected automatically. |
| Retrieval targets | Optional guide/assessment stage makes canonical prompts and answer groups with one owner per extracted idea and exact cited answer items. | Grouping and variants are model judgments; exact membership does not prove semantic correctness or source completeness. |
| Shared writing context | Writers receive the route, common constraints and exact assigned/prerequisite evidence. | They do not receive other parallel writers' finished prose. |
| Local review and repair | Material findings trigger a bounded section repair; unresolved findings stay visible. | No automatic repair of upstream extraction or a cross-artifact semantic dependency closure. |
| Targeted revisions | Per-section instructions change affected requests and preserve unrelated cached work. | Semantic dependence between prose sections is not inferred. Replan when the goal/sources change. |
| Output separation | Candidate and examiner assessment Markdown, HTML and PDF are distinct, with generic candidate question headings. | No live staged-release server or authenticated examiner reveal. |
| Assessment check | Every assessment run includes a blind provider call with current and prior candidate sections; a separate judge gets its answer, key and exact evidence. | Separate calls do not guarantee isolation from provider memory or prove question quality. Findings stay examiner/operator-only. |
| Delivery | Markdown, HTML, formatted PDF, plan and execution report. An optional command adapter renders PCM WAV with hashes and duration. | WAV structure is checked; listening, pronunciation and ASR fidelity are not. Text extraction is not visual fidelity. |
| Audio resource | A process-safe per-user file lock covers uncached speech-adapter calls across local projects. | It is a local renderer lane, not a distributed scheduler or a limit on model workers. |
| Recovery | Browser project state persists; interrupted projects can resume using retained plan/cache. | No mid-call model continuation or distributed coordinator. |
| Custom graphs | Jobs, dependencies, selected inputs, resource lanes, observed results and selected prior observations. | Generic jobs only return JSON objects; they do not inherit production evidence checks. |
| Retained experience | Operator-selected observations can enter a custom method node or a production planner's context. | No autonomous method selection, training or demonstrated transfer improvement. |

## Two execution contracts

[Production](production.md) begins with sources, an operator-assigned source policy and a desired artifact. Its reading and global planning stages create assignments for parallel writing and review. A section's representation makes its requirements explicit instead of assuming every task is a summary. This is the default Projects screen. Assessment checking runs after assessment production; audio rendering is optional for a ready podcast script. They have separate information and resource boundaries.

[Methods](methods.md) begin with an explicit dependency graph. Ready jobs run subject to global capacity and resource lanes. A node sees selected task fields and completed results of its declared prerequisites. A failing node skips dependent work while unrelated branches may finish. Method definitions can express execution shapes that the production pipeline does not.

A planned prerequisite and a completed-result dependency serve different purposes. The former keeps writing parallel while sharing intended scope and exact sources. The latter waits for actual prior work and lengthens the critical path. Choosing between them is a task-design decision, not merely a scheduler optimization.

## What was preserved from the earlier systems

The [cross-system map](system-origins.md) covers educational audio, document/reference generation, question generation and oral-case delivery separately. It distinguishes reusable mechanisms from capabilities that still require dedicated implementations. Original histories and private course content are not distributed.

The next claims must be earned on matched tasks: source coverage before and after selection, semantic quality, useful representation, elapsed time, actual provider cost, operator effort and selective repair after a source change. The [measurement protocol](measurement.md) defines those comparisons. The checked-in deterministic fixture and synthetic scheduler measurements establish mechanics only.
