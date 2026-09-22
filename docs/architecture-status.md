# Architecture status

Lamina v0.6 connects source-aware production to a local Projects interface, CLI, exports, and persisted recovery. It also runs declared method graphs. Both paths share source storage, adapter conventions, and the exact-request cache, but have different contracts.

| Mechanism | Implemented behavior | Limit |
| --- | --- | --- |
| Source ingestion | Hashed Markdown, text, and extractable PDF text with ordered locations. | No OCR, image interpretation, or table reconstruction. |
| Source policy | Selected teaching sources receive authority, supplement, historical, or form-exemplar roles. Exemplars stay out of factual reading and citations. | Model interpretation needs review; assessment sources remain held out. |
| Parallel reading | Readers own core units, see neighboring full units, and cite exact core quotes. | Large units can exceed the target window; oversized requests fail. |
| Global planning | Model chooses section count, grouping, representation, prerequisite evidence, and omissions. | Coverage starts with extracted ideas. |
| Retrieval targets | Optional guide/assessment stage groups ideas into source-backed prompts and answer groups with one owner per idea. | Grouping and variants are model judgments. |
| Shared writing context | Writers receive the route, constraints, and assigned/prerequisite evidence. | Parallel writers do not see each other's finished prose. |
| Review and repair | Findings trigger one section repair; remaining findings stay visible. | No upstream extraction repair or inferred cross-artifact dependency closure. |
| Targeted revisions | Section notes change affected requests while unrelated work stays cached. | Prose dependence is not inferred; replan after goal/source changes. |
| Assessment output | Separate candidate/examiner Markdown, HTML, and PDF; generic candidate headings. | No authenticated staged examiner reveal. |
| Assessment check | Every assessment run has a blind solve from current/prior candidate sections and a separate judge with the answer, key, and evidence. | Separate calls cannot exclude provider memory or prove question quality. Findings stay examiner/operator-only. |
| Delivery | Markdown, HTML, formatted PDF, plan, report, and optional PCM WAV with hashes and duration. | No listening, pronunciation, ASR fidelity, or visual-extraction proof. |
| Audio resource | A process-safe per-user lock covers uncached speech calls across projects. | Local renderer lane, not a distributed scheduler or model-worker limit. |
| Recovery | Persisted projects resume after interruption with retained plan/cache. | No mid-call continuation or distributed coordinator. |
| Custom graphs | Dependencies, selected task inputs, resource lanes, results, and selected observations. | JSON object replies do not inherit production evidence checks. |
| Experience | Selected observations can reach method nodes or the production planner. | No autonomous method selection, training, or demonstrated transfer gain. |

## Execution contracts

[Production](production.md) starts with sources, a source policy, and an artifact goal. Reading and global planning assign sections for parallel writing. Each section's representation states its requirements. Assessment checking follows assessment production; audio rendering is optional for a ready podcast script, with its own information and resource boundaries. This is the default Projects path.

[Methods](methods.md) start from a declared dependency graph. Ready jobs run within global and lane capacities. Each node sees selected task fields and completed results from declared prerequisites. A failed node skips descendants while unrelated branches may finish. Method graphs can express execution shapes outside the production pipeline.

Planned prerequisites share intended scope and evidence while writers run in parallel. Dependencies on completed results wait for prior work and lengthen the critical path. Choose according to the task's information needs.

## Evidence still needed

The [cross-system map](system-origins.md) separates educational audio, reference generation, question generation, and oral-case delivery. Original histories and private course content are not distributed. On matched tasks, compare source coverage, semantic quality, useful representation, elapsed time, provider cost, operator effort, and repair after source changes. The [measurement protocol](measurement.md) defines these comparisons. Checked-in deterministic fixtures and synthetic scheduler measurements establish mechanics only.
