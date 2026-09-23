# Architecture

Lamina connects three decisions: which material belongs together, what each worker must see, and when the worker can start. Models or a calling agent decide meaning and editorial structure. Code controls provenance, ownership, resource limits and execution. [Production](production.md) specifies the direct, planned and caller-assigned routes.

## Source structure and capacity

Ingestion preserves complete parser structures. Reading uses one structure per call when no workload profile exists. A declared profile can combine structures across headings within one source; the complete request must satisfy separate workload and capacity limits. PowerPoint slide components remain together. A reader can request adjacent context with a reason; output truncation divides a batch between complete structures. An indivisible structure can require a larger allowance or explicit decomposition.

Providers with a declared tokenizer and context limit expose measured input capacity with an output reserve. Generic adapters expose a byte transport guard. Per-stage workload profiles separately constrain input tokens or item counts. Automatic workflow selection applies those policies to writing and source-review requests; future drafts and findings are checked when available. Multi-item semantic stages require an explicit policy. The writer also checks every visible source unit and any form exemplars or retained observations before allowing an unprofiled single-unit call; these inputs contribute work even when they have no ownership assignment. Configured limits remain operator decisions until supported by task-specific evaluation.

Default readings use the current goal. Reusable inventories require explicit selection and remain unassessed unless evaluated. Original source passages accompany writing because extraction can omit qualifications or relationships. A cache preserves the selected interpretation, including any undetected omissions.

## Organization and context

Planning cards retain complete idea titles, explanations and evidence references. Repeated quotation text is removed from planning requests and restored mechanically. Inventories exceeding workload or request limits use bounded grouping calls to create an outline; final assignment revisits every original card. Each card has one owner or an explicit omission. The saved grouping tree makes those decisions inspectable. The shared outline must still fit a request.

The engine measures resulting writing and source-review assignments. Models subdivide oversized planned sections without discarding owned material. Required context or one indivisible idea can still exceed capacity.

Each writer receives its assignment, original passages, declared earlier evidence, relevant shared relationships, and its neighbors' titles and purposes. Repeated source IDs appear once. Unrelated sections' assignments stay outside the request.

`context_section_ids` shares earlier source evidence. `candidate_context_ids` supplies completed earlier candidate prompts during assessment checking. Work requiring completed prerequisite prose uses a method dependency graph. Ownership, context and completed outputs remain explicit boundaries.

## Checks and recovery

Code resolves reader source references to exact spans, then validates membership, supplied output claim spans and ownership. Legacy quotation replies retain conservative formatting normalization. Accepted extraction rows remain fixed while invalid rows receive local corrections. Reviewers inspect the actual draft for lost meaning and unsupported claims. Different stages can use different models.

Production permits two attempts by default: the original call and one eligible correction/retry. This configurable resource policy covers validator feedback and provider-declared transient failures. Only fully validated results become successful cache entries. Independent jobs can finish after another fails.

Each section proceeds through writing, review and one possible repair/recheck. Optional document review examines completed neighbors and declared relationships, recording unchecked pairs. Coverage reports distinguish material considered, cited by readers, assigned and cited in output. Plans and receipts retain `semantic_recall: "unmeasured"` independently of the operational status. Semantic completeness remains a separate evaluation.

## Scheduling and latency

One worker limit bounds simultaneous production calls; stage limits can reduce it. Review begins as individual sections finish. The method runtime builds dependency counts once, starts ready work within lane limits, and prioritizes longer remaining paths using graph depth. This priority uses structure without estimating model duration.

With total service work W, worker capacity P and longest dependency chain D, ideal completion takes at least max(W/P, D). Real runs also incur provider waiting, network/process overhead, retries and unequal call lengths. Measure complete-run latency and delivered quality alongside call counts and usage.

Persistent adapters share a process and HTTP connection pool. Stable prompt ordering preserves repeated prefixes where endpoints support caching. Provider receipts establish actual cache usage; no universal discount or speedup is assumed.

## Identity and reuse

SQLite stores exact source revisions, parsed units, an FTS5 index, jobs and receipts. Completed cache reads avoid write transactions. Renewable leases and owner fencing protect running jobs. Atomic import prevents mixed parser output.

Local request identities allow unchanged readings and section context to reuse results while rebinding citations to the current exact revision. Changing packing boundaries, headings, dependencies or relevant model configuration can invalidate additional work. Source edits have no constant-cost guarantee. New goals reread sources by default. Explicit reusable mode can reuse matching inventories, then plans across the inventory.

Plans hold source units once and use IDs in reading batches. Browser progress records remain separate from full plans and receipts.

## Code map

| Modules | Responsibility |
| --- | --- |
| `ingest`, `store` | Parse, locate, index and retain sources. |
| `context_budget`, `source_reading`, `source_spans` | Enforce capacity/workload limits, read structures and resolve exact source spans. |
| `planning`, `source_assignments` | Organize bounded plans or validate supplied assignments. |
| `production`, `production_contract`, `context_binding` | Assemble requests, enforce contracts and bind references. |
| `call_runtime`, `execution`, `providers` | Cache, retry, schedule and transport calls. |
| `verification`, `assessment_checks` | Check output links, section relationships and assessment behavior. |
| `method_runtime` | Run declared graphs and retain observations. |

Older lesson/procedure APIs retain separate contracts. See [system origins](system-origins.md) for their source families and [measurement](measurement.md) for evaluation boundaries.
