# Architecture

A Lamina workflow specifies what each worker should produce, the evidence it may use and the results it must wait for. Models or a calling agent organize the material and write the output. Code records source identity and ownership, limits requests and schedules the declared work. [Production](production.md) specifies the direct, planned and caller-assigned routes.

## Source structure and capacity

Ingestion preserves complete parser structures. Reading uses one structure per call when no workload profile exists. A declared profile can combine structures across headings within one source; the complete request must satisfy separate workload and capacity limits. PowerPoint slide components remain together. Readers receive a boundary halo of sentence spans and can request more adjacent context with a reason; output truncation divides a batch between complete structures. An indivisible structure can require a larger allowance or explicit decomposition.

Providers with a declared tokenizer and context limit expose measured input capacity with an output reserve. Generic adapters expose a byte transport guard. Per-stage workload profiles separately constrain input tokens or item counts. Automatic workflow selection applies those policies to writing and source-review requests; future drafts and findings are checked when available. Multi-item semantic stages require an explicit policy. The writer also checks every visible source unit and any form exemplars or retained observations before allowing an unprofiled single-unit call; these inputs contribute work even when they have no ownership assignment. Configured limits remain operator decisions until supported by task-specific evaluation.

Default readings use the current goal. Reusable inventories require explicit selection and remain unassessed unless evaluated. Original source passages accompany writing because extraction can omit qualifications or relationships. A cache preserves the selected interpretation, including any undetected omissions. When optional evidence comparison raises a follow-up question, it can also search the permitted original units. The local search can return a passage that has no extracted idea, or direct attention to a qualifier in a passage already supplied. Full units retain their source identity and policy; newly opened passages support comparison and later writing without gaining idea ownership. Search is bounded, and missing evidence remains unresolved when it cannot be found or fit in the request.

## Organization and context

Planning cards retain complete idea titles, explanations and evidence references. Repeated quotation text is removed from planning requests and restored mechanically. Inventories exceeding workload or request limits use bounded grouping calls to create an outline; final assignment revisits every original card. Each card has one owner or an explicit omission. The saved grouping tree makes those decisions inspectable. The shared outline must still fit a request.

The engine measures resulting writing and source-review assignments. Models subdivide oversized planned sections without discarding owned material. Required context or one indivisible idea can still exceed capacity.

Each writer receives its assignment, original passages, declared earlier evidence, relevant shared relationships, and its neighbors' titles and purposes. Repeated source IDs appear once. Unrelated sections' assignments stay outside the request.

`context_section_ids` shares earlier source evidence. `candidate_context_ids` supplies completed earlier candidate prompts during assessment checking. Work requiring completed prerequisite prose uses a method dependency graph. Ownership, context and completed outputs remain explicit boundaries.

## Checks and recovery

Code resolves reader source references to exact spans, then validates membership, supplied output claim spans and ownership. Legacy quotation replies retain conservative formatting normalization. Accepted extraction rows remain fixed while invalid rows receive local corrections. Reviewers inspect the actual draft for lost meaning and unsupported claims. Different stages can use different models.

Production permits two attempts by default: the original call and one eligible correction/retry. This configurable resource policy covers validator feedback and provider-declared transient failures. Only fully validated results become successful cache entries. Independent jobs can finish after another fails. After receiving and validating a grouped response, the engine records valid rows as completed work before retrying invalid siblings. The existing pool schedules those retries and any request-budget splits, so an accepted draft can reach review while another row is still being corrected.

Each section proceeds through writing, review and one possible repair/recheck. Optional document review examines completed neighbors and declared relationships, recording unchecked pairs. Coverage reports distinguish material considered, cited by readers, assigned and cited in output. Plans and receipts retain `semantic_recall: "unmeasured"` independently of the operational status. Semantic completeness remains a separate evaluation.

## Scheduling and latency

One worker limit bounds simultaneous production calls; stage limits can reduce it. Review begins as individual sections finish. The planning tree streams: a grouping level starts as soon as a full batch of the level below exists, so only the final outline call waits on a complete level. Podcast sections are synthesized on a separate speech lane as they leave review. The sweep writes cards during reading, then deduplicates them and audits selected windows. It has no separate planner or writer. The method runtime builds dependency counts once, starts ready work within lane limits, and prioritizes longer remaining paths using graph depth. This priority uses structure without estimating model duration.

With total service work W, worker capacity P and longest dependency chain D, ideal completion takes at least max(W/P, D). Real runs also incur provider waiting, network/process overhead, retries and unequal call lengths. Measure complete-run latency and delivered quality alongside call counts and usage. [Flow geometry](flow-geometry.md) applies this bound to the current routes and examines batching, boundary context and recovery under explicit assumptions.

Persistent adapters share a process and HTTP connection pool. Stable prompt ordering preserves repeated prefixes where endpoints support caching. Provider receipts establish actual cache usage; no universal discount or speedup is assumed.

## Identity and reuse

SQLite stores exact source revisions, parsed units, an FTS5 index, jobs and receipts. Completed cache reads avoid write transactions. Renewable leases and owner fencing protect running jobs. Atomic import prevents mixed parser output.

Local request identities allow unchanged readings and section context to reuse results while rebinding citations to the current exact revision. Changing packing boundaries, headings, dependencies or relevant model configuration can invalidate additional work. Source edits have no constant-cost guarantee. New goals reread sources by default. Explicit reusable mode can reuse matching inventories, then plans across the inventory.

Original-source follow-up comparisons include a digest of the entire permitted source snapshot in their request identity. Edits, additions, removals or policy changes therefore invalidate those comparisons, including earlier searches that found nothing. This is conservative reuse: an unchanged cited passage alone cannot preserve a claim that no exception exists elsewhere.

Plans hold source units once and use IDs in reading batches. Browser progress records remain separate from full plans and receipts.

## Code map

| Modules | Responsibility |
| --- | --- |
| `ingest`, `store` | Parse, locate, index and retain sources. |
| `context_budget`, `source_reading`, `source_spans` | Enforce capacity/workload limits, read structures and resolve exact source spans. |
| `planning`, `source_assignments` | Organize bounded plans (streaming grouping tree) or validate supplied assignments. |
| `sweep`, `similarity` | Read straight to cards, suppress duplicates and audit a sample; local similarity for duplicate suppression and relation nomination. |
| `production`, `production_contract`, `context_binding` | Assemble requests, enforce contracts and bind references. |
| `call_runtime`, `execution`, `section_batching`, `providers` | Cache, retry, schedule and transport calls; release accepted batch rows before sibling retries. |
| `evidence_relations` | Compare nominated claims and reopen permitted original source units. |
| `verification`, `assessment_checks` | Check output links, section relationships and assessment behavior. |
| `method_runtime` | Run declared graphs and retain observations. |

Older lesson/procedure APIs retain separate contracts. See [system origins](system-origins.md) for their source families and [measurement](measurement.md) for evaluation boundaries.
