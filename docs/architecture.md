# Architecture

A Lamina workflow specifies what each worker produces, the evidence it may use and the results it must wait for. Models or a calling agent organize the material and write the output. Code records source identity and ownership, limits requests, schedules the declared work and checks exact contracts. [Production](production.md) describes the sweep, direct, planned and caller-assigned routes and their options; this document describes the mechanisms behind them.

## 1. Source structure and capacity

Ingestion stores exact source revisions and ordered units with locations. Markdown paragraphs, lists, tables, code blocks and quotations remain intact. PDF text keeps its page boundaries. PowerPoint text, tables and speaker notes remain separately citable units that share a slide-level structural group. Optional OCR adds a searchable text layer before PDF extraction. Import parses every file before publishing any of them, so a failed batch leaves no mixed parser output.

Parser boundaries record structure the parser can see. They do not establish semantic independence: a PDF page can continue an argument from the previous page, and a slide's notes can qualify its table.

Without a reading workload profile, one reader call owns up to eight contiguous units from one heading section of one source, a single PDF page, or one slide group. The request budget can split such a group further. A declared profile can combine structures across headings within one source while the complete request satisfies both the workload limit and the capacity limit. An indivisible structure that does not fit is reported with its locator and never truncated.

Providers with a declared tokenizer and context limit expose measured input capacity with an output reserve. Generic adapters expose a byte transport guard. Per-stage workload profiles separately limit input tokens or item counts. Automatic workflow selection applies those policies to writing and source-review requests and checks actual drafts and findings when they exist. Multi-item semantic stages require an explicit policy. Before allowing an unprofiled single-unit writing call, the writer counts every visible source unit, form exemplar and retained observation, because these inputs add work even without an ownership assignment. Configured limits remain operator decisions until task-specific evaluation supports them; [calibration](calibration.md) measures them.

## 2. Reading and evidence

Each reader input contains the unchanged text of its units once, plus an ordered span index. Prose spans follow conservative sentence boundaries; tables, lists and code stay whole. [Parsing](parsing.md#source-references) gives the boundary rules and [adapters](adapters.md#source-spans-and-citations) the wire format. Readers cite span IDs or contiguous ranges. Code rebuilds the span index from stored text and materializes the exact quotation, so it never trusts a model-supplied offset. Unknown references, reversed ranges and ranges that cross units fail validation. A valid reference establishes location; semantic support still needs review.

By default every reader also sees a boundary halo: the last six sentence spans of the preceding unit and the first six of the following unit (`reader_context_spans`), shown with their real span IDs. The halo shrinks to fit the reader's budget so it never displaces owned material. A reader that still lacks a dependency can request adjacent context with a reason, up to two extensions. The first request in a direction completes the partial neighboring unit; the next steps to the following structure. Context clarifies a boundary and never originates an owned idea. [Flow geometry](flow-geometry.md#why-a-small-halo-can-help) describes the cost of the halo.

Every reader idea has owned `unit_ids` anchored in its core and derived `support_unit_ids` for cited context outside the core. Citations can address only material that read actually received, and an idea that cites only context is rejected. Writer and reviewer requests include the exact supporting units for assigned and declared prior ideas. Their request hashes therefore change when supporting text changes, while unrelated requests stay reusable.

`reading="task"`, the default, asks readers to select ideas useful for the current brief. `reading="reusable"` compiles a brief-independent inventory of statements, quantities, qualifications and relationships for later projects. Reuse also preserves any interpretation or omission in that inventory, so it requires explicit selection. Original passages accompany later writing because extraction can omit qualifications or relationships.

If a reader response is truncated, the engine divides the owned material along complete structure boundaries and releases the children into the same worker pool. The children keep ordered ownership and receive a fresh halo on their inner edge. Prepared reading batches start while later batches are still being measured. A batch that fails after its retry is recorded in `plan.planning.unresolved_reads`, and by default the run continues on the successful reads.

## 3. Organization and context

Planning cards carry each idea's complete title, explanation and evidence handles. Repeated quotation text is removed from planning requests and restored mechanically afterward.

If every card fits one route request, a model chooses sections, representations, ownership, context and explicit omissions directly. Otherwise a grouping tree summarizes the cards level by level, and the tree streams. Level-0 batches form from completed reads in source order, so each grouping call relates adjacent cards that share a structure. A higher level starts as soon as a full batch of lower-level summaries exists and the summaries that have arrived already exceed the outline budget. Cross-source relationships form at the summary levels and in assignment. Each summary carries one original card into the outline call as an exemplar.

Final assignment revisits every original card against the outline. Code requires each original ID to occur exactly once, as an assignment or as an omission with a reason, and summary groups never become source owners. A summary is useful for navigation but cannot carry every qualification in the original ideas, so cross-document contradictions, variants and source roles remain visible when ownership is decided. The saved grouping tree makes these decisions inspectable. The outline itself must fit one request.

For guides and assessments, optional retrieval-target reconciliation runs before section routing. The model decides whether prompts are equivalent, compatible variants or different contexts. Code keeps every member idea and its exact answer evidence, and a relation marked as a different context cannot be merged away. The merge remains a semantic judgment that needs evaluation.

After routing, the engine measures the complete writing and review request for every section. A model subdivides an oversized section into smaller coherent assignments under a no-omission contract. One indivisible idea, retrieval target or required context set can still exceed capacity. Podcast outlines also number sections into episodes with spoken-word targets; a subdivided section's children inherit its episode and share its words.

A writer receives its assignment, the original supporting passages, declared earlier evidence, relevant shared relationships and the titles and purposes of its immediate neighbors. A repeated source unit appears once in the request. Unrelated sections' assignments stay outside it. Direct and assigned routes give writers original units without first creating idea cards.

## 4. Ownership, shared evidence and completed results

Three relationships stay separate because they change what a worker may claim and when it may start. Consider a guide for an engineering team about when a retried worker may publish a result.

**Ownership** says what a section must account for. A section called "Fencing stale completions" might own the manual passage defining fencing tokens and the incident passage describing an old worker's late write. Those passages cannot also be silently assigned as another section's work.

**Shared evidence** supplies relevant source material without changing ownership. A neighboring section about lease expiry may need the fencing definition to explain why expiry does not prove that the first worker stopped. It receives that exact passage as context while the fencing section remains its owner. A shared relationship can also state, with exact evidence, that lease expiry and fencing address different parts of the failure. Planned earlier ideas are context too; they are not completed prose.

**Completed-result dependencies** apply when a task needs another worker's actual output. An editor that must quote or transform the finished fencing section cannot run in parallel with that writer. That job belongs in a [method](methods.md) graph with a dependency on the completed result. The method runtime supplies graph execution, lanes, caching and selected observations; it does not inherit production's source ownership, evidence resolution, review or export contracts, so the method author defines what its nodes require.

Production expresses these boundaries with assigned units or ideas, contextual source units, `context_section_ids` for earlier sections' source evidence, and scoped shared relationships. Assessment checking adds `candidate_context_ids`: a blind solver sees the current candidate prompt and only the earlier candidate prompts declared as context, and a separate judge sees the answer, marking material and cited evidence. Candidate and examiner exports stay separate. This reduces accidental answer leakage; it cannot prove that a stateful external provider forgot earlier calls.

## 5. Evidence comparison and original-source follow-up

`compare_relations=true` runs a comparison stage after reading and before planning. Local similarity nominates pairs above `relation_threshold`, using provider embeddings when the adapter offers `embed` and TF-IDF otherwise, plus same-unit and same-structure lanes. A provider hook can add retrieval lanes and multi-source groups. Very frequent postings are skipped to bound retrieval work, and the receipt reports how many. Models compare the actual source passages and classify each relation as repetition, complement, different conditions, contradiction, supersession, unrelated or unresolved.

A comparison can issue follow-up queries: up to three per comparison, each returning at most one new original unit, across at most three comparisons. Queries search both extracted ideas and the full permitted original units, including passages no reader extracted; exact unit IDs and headings also work. A query can therefore return a passage with no extracted idea, or point to a qualifier in a passage already supplied. Retrieved passages keep their source policy and location and add supporting evidence without creating an owned idea. Relations keep participant IDs, evidence, classification and searches. Planning sees their conditions, and affected writers receive their support. Ownership never transfers because two claims are related.

Every comparison request includes a fingerprint of the complete permitted source snapshot. Edits, additions, removals and policy changes invalidate comparisons, including cached results reporting that no exception exists elsewhere. An unchanged cited passage alone cannot preserve such an absence claim; the cost is that an unrelated edit can rerun comparisons. Search records distinguish passages found from passages actually read. A follow-up must fit complete source structures within the request and workload limits. Otherwise the relation stays unresolved, records the pending unit IDs and keeps the project in review.

Nomination recall and comparison accuracy are separate, unmeasured quantities. Lexically dissimilar relations need caller or dense nominations, or a successful follow-up query. A bounded search cannot perform exhaustive reconciliation.

## 6. Checks: what code establishes and what needs judgment

The plan and receipt keep these counts separate:

- considered source units: structures supplied to readers;
- cited units: structures supporting returned ideas;
- assigned ideas or units: material owned by a finished section;
- explicit omissions: material excluded with a reason;
- output citations and claim links: source material named by the finished section.

One count cannot substitute for another. Full structural coverage does not establish extraction recall, and a valid output citation does not establish semantic support.

Code establishes that a source reference resolves to an exact supplied span; that an idea originated in an owned unit; that every planning object has one owner or an explicit omission; that supplied claim mappings occur in the named output field and link to permitted source text; that candidate and examiner fields remain structurally separate; that configured request, workload and resource limits were respected; and that only fully validated results entered the cache.

| Check | What it establishes | What still needs judgment |
| --- | --- | --- |
| Exact source reference | The cited source contains the materialized quotation | Whether the source is correct, current or applicable |
| Reader disposition | A unit was considered and whether an idea cited it | Whether all relevant meaning was extracted |
| Editorial partition | Every extracted object has an owner or explicit omission | Whether grouping and omission serve the brief |
| Claim mapping | Claimed output text appears in a named body and links to source quotations | Whether the quotation supports the claim and its qualifications |
| Section review | A reviewer reported concrete support, coverage or consistency defects | Defects the reviewer missed |
| Relationship review | A reviewer compared completed sections connected by declared context or a shared source relationship | Undeclared relations and conflicts outside those pairs |
| Blind assessment solve | A separate request attempted the candidate material without the key | Whether real candidates can use it and learn from it |

Writers place compact markers such as `[s3]` after supported statements. Lamina resolves each marker against only the spans supplied to that section, reconstructs the quotation, derives claim records and removes the markers before export. `verification.validate_claims` accepts claim mappings with `id`, `text`, `body_field` and exact `evidence`. One mapping can span a sentence, a table cell or a longer qualified statement, so a sentence splitter never acts as a factual-claim detector. Missing mappings remain visible in the receipt, and supplied mappings must resolve exactly to output and source text. The section reviewer checks support, omitted qualifications and material claims with no mapping in the same request.

`verification.coverage_report` keeps considered units, reader citations, editorial assignment and output citations separate, and lists uncited unit IDs for inspection. An uncited unit can hold an irrelevant title, repeated content or a missed fact; the count cannot distinguish them. Embedding similarity cannot establish entailment either.

`check_document_sections` runs when `document_review=true`. It examines completed sections connected by an explicit source dependency, a candidate prerequisite or a shared-context quotation linking their owners, and consecutive sections for continuity. Each call sees both completed bodies, their claim mappings and citations. An oversized pair stays explicitly unchecked and the audit stays in `review`. Findings name the affected sections, and the receipt reports which pairs were examined and how many other pairs exist. A null `document_checks` field means the audit did not run. Explicit shared-context section scopes determine which outputs a relationship concerns; older plans fall back to the owners of the cited units.

Plans and receipts retain `semantic_recall: "unmeasured"` independently of the operational status. The scripted silent-omission case in [calibration](calibration.md#demonstrate-the-silent-omission) passes every structural check and still loses a negation.

## 7. Execution, grouping and recovery

One worker limit bounds simultaneous production calls; reader, writer and reviewer ceilings can reduce it within a stage. Every production section follows:

```text
write -> review -> optional repair -> recheck
```

Review begins when an individual section finishes, so unrelated sections never wait at an all-writer barrier. Ready follow-ups precede fresh writing in one shared pool. A flagged section receives one bounded repair, and unresolved findings leave the receipt in `review`. Podcast sections are synthesized on a separate speech lane as they leave review. The sweep writes cards during reading, then suppresses duplicates locally and audits a sample of windows; it has no planner or writer. Incremental packing releases eligible reads before later preparation finishes.

Production permits two attempts by default: the original call and one eligible correction or retry. The same allowance covers validator feedback and provider-declared transient failures. A reader correction names the invalid rows; accepted rows stay fixed while the replacements are merged and the complete result is checked again. Only fully validated results become successful cache entries. Independent jobs can finish and keep their results after a sibling fails.

`sections_per_request > 1` groups ready writing or review work under full request and stage workload checks. Cached sections are removed before a physical request is formed, so a change to one section does not regenerate an unchanged peer. Each task keeps its own source alias scope, output contract, section identity and fenced cache entry. After the complete grouped response is validated, accepted rows are recorded as completed work and advance to review. Invalid or missing rows and budget subdivisions return to the same bounded scheduler as new work; no extra executor handles them. Valid rows survive a malformed sibling, repairs stay local, and a provider outage does not fan out into another wave of calls. The engine waits for the full provider response and never parses an unfinished JSON stream.

The native Gemini adapter counts tokens on an admission lane separate from generation, and every submitted request still receives exact capacity checking. A worker count implies no provider throughput. Persistent adapters share a process and HTTP connection pool, and stable prompt ordering preserves repeated prefixes where endpoints support caching. Provider receipts establish actual cache usage.

The method runtime builds dependency counts once, starts ready nodes within lane limits and prioritizes nodes with longer remaining dependency chains. That priority uses graph structure and makes no estimate of model duration. A failed node skips its descendants while independent branches finish.

[Flow geometry](flow-geometry.md) gives the lower bound on completion time and applies it to these routes.

## 8. Identity and reuse

SQLite stores exact source revisions, parsed units, an FTS5 index, jobs and receipts. A model request's cache identity includes its stage, the production protocol revision (currently `lamina-production-11`), adapter identity and complete semantic input. A plan saved under an earlier protocol revision must be replanned. Completed cache reads avoid write transactions.

During writing, exact source-revision pointers are replaced with canonical local references while semantic source text, roles, assignments and context stay in the request identity. After validation, Lamina binds the references to the selected source revision. Equivalent local work can therefore be reused without losing current provenance.

Concurrent callers for one cache key share a durable job. Renewable leases recover abandoned work, and an owner token fences a superseded worker from committing stale output. Failed or partially validated replies never become successful cache entries.

A new brief rereads sources by default. Explicit reusable reading can reuse matching inventories and then plans across the whole inventory. A section revision changes that section's request and can reuse unrelated section work. Changes to headings, packing boundaries, source meaning, supporting units, dependencies, model configuration or relevant context can invalidate more work, so no source edit has a constant-cost guarantee. Comparison requests carry the source-snapshot fingerprint described in section 5.

Plans hold each source unit once and refer to it by ID in reading batches. Browser progress records stay separate from full plans and receipts.

## 9. Alternatives considered

| Problem | Alternatives | Choice |
| --- | --- | --- |
| Reading units | Paragraph calls, heading sections, fixed windows, semantic chunking | Up to eight contiguous units per heading section without a profile, or packing by a declared workload; whole PDF pages and slide groups. A six-span boundary halo by default, shrunk to fit, plus a reasoned request for more adjacent context. |
| Evidence addresses | Copied quotations, paragraph IDs, sentence IDs, structured document blocks | Sentence-sized addresses over immutable source text. Tables, lists and code stay whole. Writers use markers; code derives quotations and claim records. |
| Sentence detection | Custom rules, syntok, spaCy | Conservative rules. Boundaries affect address convenience; source offsets and text establish the quotation. Evaluate a language-specific splitter when a failure corpus warrants it. |
| Structured output | Expected-shape prompts, JSON Schema, Pydantic, Instructor, BAML | Expected-shape prompts plus Lamina's source and ownership checks. Adapters forward a real JSON Schema only when a request supplies one. Another retry layer would duplicate the existing correction and accounting contract. |
| Execution | Local SQLite, Prefect, Temporal | SQLite leases, fencing and the dependency scheduler for local runs. A distributed multi-machine deployment would justify revisiting an external workflow service. |
| Workload selection | Fixed universal sizes, manual settings, optimizer-driven tuning | Initial stage settings plus a reproducible measurement command; promote a tested setting when stored acceptance criteria pass. |
| Prompt optimization | Hand changes, DSPy | Establish held-out quality measurements before introducing an optimizer, which could otherwise improve a proxy while losing useful content. |

The W3C [Web Annotation model](https://www.w3.org/TR/annotation-model/) separates position and quotation selectors. Lamina follows the same principle, a source revision plus deterministic character ranges with quotations reconstructed from the stored source, while keeping its evidence records internal.

[syntok](https://github.com/fnl/syntok) preserves token offsets, and [spaCy](https://spacy.io/usage/linguistic-features#sbd) offers rule-based and trained sentence detection. They would give more convenient boundaries in difficult text. A range can already span several addresses when a condition crosses a boundary.

[Prefect caching](https://docs.prefect.io/v3/concepts/caching) and [Temporal workflows](https://docs.temporal.io/workflows) address broader execution environments. Lamina already has durable local jobs, owner leases and stale-writer fencing; another scheduler would add a second persistence and retry contract. Distribution should follow a concrete deployment need.

[DSPy optimizers](https://dspy.ai/learn/optimization/optimizers/) require a metric and examples. Lamina first needs a trustworthy evaluation set and comparable runs across configurations; the [measurement protocol](measurement.md) describes them.

## 10. Code map

| Modules | Responsibility |
| --- | --- |
| `ingest`, `store` | Parse, locate, index and retain sources; durable jobs, leases and cache. |
| `context_budget`, `workload_profiles` | Request capacity and per-stage workload limits with their evidence. |
| `source_reading`, `source_spans`, `evidence` | Read structures with a halo and context requests; resolve exact source spans and quotations. |
| `planning`, `retrieval_targets`, `source_assignments` | Streaming grouping tree, outline and assignment; retrieval targets; caller-supplied assignments. |
| `sweep`, `similarity` | Read straight to cards, suppress duplicates and audit a sample; local similarity for duplicate suppression and relation nomination. |
| `production`, `production_plan`, `section_context`, `section_calls`, `production_render`, `speech_lane`, `production_contract`, `context_binding`, `writer_markers`, `source_policy` | Assemble requests, enforce option and output contracts, bind references and resolve writer markers. |
| `call_runtime`, `execution`, `section_batching`, `providers`, `chat_protocol` | Cache, retry, schedule and transport calls; release accepted grouped rows before sibling retries; stable prompt layout. |
| `evidence_relations`, `retrieval` | Compare nominated claims and search permitted original units. |
| `verification`, `assessment_checks` | Check output links, coverage, section relationships and assessment behavior. |
| `production_export`, `production_delivery`, `audio_delivery` | Export documents, cards and assessments; synthesize and assemble audio. |
| `calibration`, `quality_evaluation` | Run workload experiments and the canary oracle. |
| `method_runtime`, `methods` | Validate and run declared graphs; retain observations. |
| `production_example` | Deterministic fixture behind `lamina demo`. |

## Limits

Lamina does not interpret figures, reconstruct arbitrary PDF layout or guarantee OCR associations. It does not retrieve a subset of a large imported collection for production; a new brief plans across the whole selection. Model review can miss the same defect as the writer, and receipts record semantic recall as unmeasured. [Capability status](architecture-status.md) lists the remaining limits by area, and [system origins](system-origins.md) records the earlier systems these mechanisms came from.
