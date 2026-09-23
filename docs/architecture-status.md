# Implemented capabilities

| Area | Current behavior | Remaining limit |
| --- | --- | --- |
| Inputs | Complete Markdown blocks, text paragraphs, PDF pages, PPTX slide text/tables/notes; optional local OCR | No general visual interpretation or guaranteed PDF reading order. |
| Capacity and workload | Separate request byte/context/output limits and per-stage token/item workload policies | Declared workload limits require quality evaluation. An indivisible structure can exceed either limit. |
| Reading | Task-specific extraction by default; one parser structure without a profile; explicit reusable mode; exact source-reference resolution | Natural structures vary in difficulty. Valid responses can omit facts; citation coverage does not measure recall. |
| Planning | Declared workload limits, compact cards, hierarchical grouping, original-card assignment and section subdivision | The outline and each required context set must fit; semantic grouping needs evaluation. |
| Writing | Direct, planned and caller-assigned routes; local source context and claim links | Claim links establish exact spans; semantic support requires review. |
| Review | Per-section review/repair/recheck; optional checks between related completed sections | Missing claim maps and unchecked relationships remain visible. Model review can miss errors. |
| Execution | Shared capacity, independent section chains, dependency counters and resource lanes | Local scheduling; no adaptive provider-rate controller or automatic hedging. |
| Models | Per-stage adapters, optional persistent JSON-lines transport, shared HTTP connections and reported usage | Endpoints must support configured tokenization and structured-output capabilities. |
| Recovery | Extraction-row corrections, bounded transient retries, completed-work caching, renewable leases and fencing | Failed units remain unresolved; incomplete work is not published as a successful cache result. |
| Revision | Reusable readings and local section request identities with exact citation rebinding | Boundary and dependency changes can invalidate additional work. |
| Assessment | Separate candidate/marking exports and blind solve/judge checks | No live staged oral-case administration. |
| Audio | Speech adapter, cached synthesis and PCM/WAV checks | Whole-script synthesis; no listening evaluation. |
| Methods | Explicit graphs, lane limits, saved receipts and selected observations | No autonomous method discovery or demonstrated learning from observations. |
| Search | Persistent SQLite FTS5 and optional caller-vector rank fusion | Lexical/vector candidates require semantic judgment; production does not automatically select a retrieved subset. |

Tests establish exercised implementation behavior. Synthetic timing measures its stated fixture. Live model quality, cost, latency and usefulness require matched evaluation on the chosen material. See [production](production.md), [adapters](adapters.md), [parsing](parsing.md), [quality evaluation](quality-evaluation.md) and [benchmarks](benchmarks.md).
