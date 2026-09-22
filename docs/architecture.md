# Architecture

Lamina separates three decisions: what material belongs together, what each call needs to see, and when that call can run. A model or calling agent decides meaning. Code stores sources, assembles context, enforces contracts and schedules work.

## Execution

| Route | Model work | When to use it |
| --- | --- | --- |
| Direct | Write → review → optional repair/recheck | Complete source context fits one writing task. |
| Assigned | The same chain per supplied section | A calling agent has chosen source ownership and dependencies. |
| Planned | Read → optional target grouping → plan → section chains | The task needs model-chosen organization first. |

`auto` selects direct for a small complete input, otherwise planned. It does not infer difficulty, choose a model, or prove that input is semantically self-contained. Every call has a request-size check. The example HTTP adapter can additionally check a configured tokenizer and model context budget with reserved output space.

The assigned route never silently creates a second planner. Search supplies candidates, not semantic equivalence: related passages can repeat, complement, qualify or contradict each other. Code deduplicates known source references. The planned route's global decision remains bounded; it is not a solution for an unlimited corpus.

## Context

Writers receive their assigned original units, a short section map and explicitly needed evidence. A unit already supplied as owned evidence is not repeated as predecessor or shared evidence. Planned ideas may retain short quotes used to identify support. Source assignments need no intermediate idea prose.

Source ownership differs from context. An assigned writer accounts for every owned unit as used or omitted with a reason. A planned writer accounts for its extracted ideas. These checks inspect records; neither proves that prose preserves every important distinction.

Earlier evidence is separate from finished candidate prompts. `context_section_ids` shares source evidence. `candidate_context_ids` supplies earlier question text to an assessment's blind solver. Both name earlier sections; neither sends a marking key into candidate input.

## Resources and time

`workers` caps simultaneous production calls. Optional stage limits can lower that capacity. The executor submits bounded work and prioritizes finishing section checks. One slow writer therefore does not block reviews of unrelated sections. Assessment solve/judge pairs also run as local chains.

More workers cannot shorten a dependency. Under an idealized homogeneous worker model, total work divided by worker count and the longest dependency chain are lower bounds on completion time. Provider quotas, token sizes, unequal model speed, retries and overhead can raise actual time. Token counts alone are not execution time.

Queueing models describe contention and waiting for a fixed workload. A scalability curve does not establish which calls should exist, an optimal semantic split, or model accuracy. Compare complete work, elapsed time, spend and output quality when changing the workflow. See [measurement](measurement.md).

## Storage

SQLite stores exact source revisions, units, an FTS5 text index, jobs and method receipts. The index returns lexical candidates without rebuilding corpus statistics in Python for every query. A separate API accepts caller-provided vectors for rank fusion.

Completed cache reads avoid a write transaction. Running jobs retain renewable leases and owner fencing. Source reimport atomically replaces parsed units, preventing mixed segmentation after parser changes. Saved plans retain their source text.

Reader requests for newly ingested sources use local IDs and omit revision locators. Unchanged text, heading, source metadata, policy, task and adjacent context can reuse an interpretation. Results are rebound to current exact source IDs. Changes outside declared context do not cause inferred semantic invalidation.

Progress is separate from the immutable plan and finished receipt. The browser polls small progress records and fetches full results when complete.

## Code map

| Module | Responsibility |
| --- | --- |
| `ingest.py`, `store.py` | Parse, locate, index and persist source material. |
| `production.py`, `production_contract.py` | Build requests, validate results and assemble the document. |
| `source_assignments.py` | Validate direct or caller-supplied source ownership. |
| `execution.py` | Bound concurrent work and run section chains. |
| `providers.py` | Dispatch configured adapters and retain usage metadata. |
| `assessment_checks.py`, delivery/export modules | Output-specific checks and files. |
| `method_runtime.py` | Execute caller-declared dependency graphs. |

The older lesson/procedure path remains available for existing integrations. Its `pipeline.py` and `samp.py` contracts are separate from production. [System origins](system-origins.md) retains historical applications without making them current capability claims.
