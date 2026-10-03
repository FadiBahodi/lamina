# Implemented capabilities

| Area | Current behavior | Remaining limit |
| --- | --- | --- |
| Inputs | Complete Markdown blocks, text paragraphs, PDF pages, PPTX slide text/tables/notes; optional local OCR | No general visual interpretation or guaranteed PDF reading order. |
| Capacity and workload | Separate request byte/context/output limits and per-stage token/item workload policies | Declared workload limits require quality evaluation. An indivisible structure can exceed either limit. |
| Reading | Task-specific extraction by default; up to eight contiguous units of one heading section, one PDF page or one slide group without a profile; six-span boundary halo on every window, shrunk to fit; failed windows recorded and the run continues; explicit reusable mode; exact source-reference resolution | Natural structures vary in difficulty. Valid responses can omit facts; citation coverage does not measure recall. |
| Sweep | `format=cards`: readers write cards, local similarity suppresses duplicates, a sampled source-centred audit attaches findings, Anki TSV export | Audit is a sample; duplicate thresholds are configured, not learned; card usefulness is unmeasured. |
| Planning | Declared workload limits, compact cards, grouping that starts while reads are still running, streaming hierarchical levels with exemplars, source-ordered level-0 batches, original-card assignment, section subdivision, podcast episodes with word targets | The outline and each required context set must fit; semantic grouping and episode pacing need evaluation. |
| Writing | Direct, planned and caller-assigned routes; local source context, propagated support dependencies, opt-in grouped requests and claim links | Claim links establish exact spans; semantic support requires review. |
| Review | Per-section review/repair/recheck; optional checks between related completed sections | Missing claim maps and unchecked relationships remain visible. Model review can miss errors. |
| Execution | Shared capacity, independent section chains, dependency counters and resource lanes; accepted grouped results advance while unresolved siblings return to the same pool | Grouping can change model reasoning. Event-order tests establish scheduling behavior, not improved live quality or latency. No adaptive provider-rate controller or automatic hedging. |
| Models | Per-stage adapters, optional persistent JSON-lines transport, shared HTTP connections and reported usage | Endpoints must support configured tokenization and structured-output capabilities. |
| Recovery | Extraction-row corrections, bounded transient retries, completed-work caching, renewable leases and fencing | Failed units remain unresolved; incomplete work is not published as a successful cache result. |
| Revision | Reusable readings and local section request identities with exact citation rebinding | Boundary and dependency changes can invalidate additional work. |
| Assessment | Separate candidate/marking exports and blind solve/judge checks | No live staged oral-case administration. |
| Audio | Speech adapter, per-section synthesis during writing on a bounded lane, cached segments, one WAV per episode plus the full programme, WAV checks; scripts in review render by default | No listening or transition evaluation. |
| Methods | Caller-supplied graphs, worker limits, saved receipts and selected observations | The graph stays fixed during a run. Worker questions and proposed changes have no scheduling behavior; the caller chooses experience for later jobs. |
| Search | Persistent SQLite FTS5 and optional caller-vector rank fusion; relation nomination by TF-IDF or provider embeddings; comparison follow-ups can reopen full permitted original units, including material absent from extracted ideas | Pair nomination and original-source follow-up retrieval are bounded. Retrieval recall and the correctness of the resulting interpretation remain unmeasured. |

[Workflow design](workflow-design.md#build-on-the-current-engine) describes the proposed additions for model-chosen methods, questions and resumption, plan changes during a run, and reuse of earlier experience.

Tests cover implementation behavior. Assess model quality, cost, latency and usefulness on the intended material and finished result. See [production](production.md), [adapters](adapters.md), [parsing](parsing.md), [calibration](calibration.md) and [benchmarks](benchmarks.md).
