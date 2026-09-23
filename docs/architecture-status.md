# Implemented capabilities

| Area | Current behavior | Remaining limit |
| --- | --- | --- |
| Inputs | Complete Markdown blocks, text paragraphs, PDF pages, PPTX slide text/tables/notes; optional local OCR | No general visual interpretation or guaranteed PDF reading order. |
| Context | Complete-request byte checks; declared model token budgets and output reserves; requested neighboring context | Unknown provider profiles expose only byte capacity. An indivisible structure can exceed capacity. |
| Reading | Reusable source inventories or task-specific extraction; structured subdivision after output truncation | Inventories are interpretations; citation coverage does not measure extraction recall. |
| Planning | Compact cards, bounded hierarchical grouping, original-card assignment and oversized-section subdivision | The outline and each required context set must fit; semantic grouping needs evaluation. |
| Writing | Direct, planned and caller-assigned routes; local source context and claim links | Claim links establish exact spans; semantic support requires review. |
| Review | Per-section review/repair/recheck; optional checks between related completed sections | Missing claim maps and unchecked relationships remain visible. Model review can miss errors. |
| Execution | Shared capacity, independent section chains, dependency counters and resource lanes | Local scheduling; no adaptive provider-rate controller or automatic hedging. |
| Models | Per-stage adapters, optional persistent JSON-lines transport, shared HTTP connections and reported usage | Endpoints must support configured tokenization and structured-output capabilities. |
| Recovery | Bounded feedback/transient retries, completed-work caching, renewable leases and fencing | Failed units remain unresolved; incomplete work is not published as a successful cache result. |
| Revision | Reusable readings and local section request identities with exact citation rebinding | Boundary and dependency changes can invalidate additional work. |
| Assessment | Separate candidate/marking exports and blind solve/judge checks | No live staged oral-case administration. |
| Audio | Speech adapter, cached synthesis and PCM/WAV checks | Whole-script synthesis; no listening evaluation. |
| Methods | Explicit graphs, lane limits, saved receipts and selected observations | No autonomous method discovery or demonstrated learning from observations. |
| Search | Persistent SQLite FTS5 and optional caller-vector rank fusion | Lexical/vector candidates require semantic judgment; production does not automatically select a retrieved subset. |

Tests establish exercised implementation behavior. Synthetic timing measures its stated fixture. Live model quality, cost, latency and usefulness require matched evaluation on the chosen material. See [production](production.md), [adapters](adapters.md), [parsing](parsing.md) and [benchmarks](benchmarks.md).
