# Implemented capabilities

| Area | Current behavior | Limit |
| --- | --- | --- |
| Inputs | Markdown/text, PDF text, PPTX text/tables/notes; explicit local OCR | No general visual understanding or guaranteed PDF table reconstruction. |
| Search | Persistent SQLite FTS5; optional caller-vector rank fusion | Candidates require semantic judgment. |
| Production | Automatic direct/planned choice; caller-supplied source assignments | Planned grouping/routing has a bounded global step. |
| Source policy | Authority, supplement, historical and form-exemplar roles; held-out material excluded | Labels do not enforce interpretation. |
| Execution | Shared capacity, stage caps, bounded submission, per-section write/review/repair | Local execution; no adaptive provider-rate controller. |
| Models | Startup-only default and per-stage adapters; usage and model fingerprints | Custom adapters must report usage and identify behavior changes. |
| Revision | Exact-request reuse; unchanged reader interpretations can survive source edits | No discovery of undeclared semantic dependencies. |
| Assessment | Separate candidate/marking exports and blind solve/judge chains with declared prior prompts | No live staged oral-case interface. |
| Audio | Local speech adapter, PCM checks and cached synthesis | Whole-script synthesis; no listening evaluation. |
| Methods | Explicit graphs, lane limits, saved receipts and selected notes | Expected shapes are instructions, not general JSON Schema validation. No autonomous method learning. |

Tests establish implementation behavior. Synthetic timing establishes timing under its fixture. Neither establishes live model quality or educational usefulness. Current contracts are in [production](production.md), [adapters](adapters.md) and [parsing](parsing.md).
