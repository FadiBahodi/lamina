# Rewrite validation — 2026-09-23

This review covers the production workflow from import through planning, writing, checking, revision and export. Package version: 0.9.0.

## Decisions

- Preserve complete parser structures and explicit source ownership. Reader size follows measured requests; no default word target or neighboring-unit overlap remains. Readers can request adjacent context. Truncated outputs split at structure boundaries.
- Reuse a source inventory across briefs. Task-specific reading remains available. Planning still considers the full inventory; retrieval-based subset selection is a separate, unimplemented optimization.
- Plan from complete titles and explanations with evidence references. Oversized inventories use bounded grouping and original-card reassignment. Oversized writing assignments are subdivided semantically. The final outline and its source metadata still need to fit.
- Keep model corrections bounded. Valid fragments of a failed read remain diagnostic evidence; they do not make an incomplete window successful. Independent work completes and stays cached.
- Use exact current source revisions in receipts and local content references in reusable requests. Parser-declared companion material remains context. Changes to visible meaning, policy or declared dependencies invalidate the affected requests.
- Reuse adapter processes and HTTP connections when configured. Preserve the command transport for existing integrations.
- Schedule independent section chains within shared capacity. Graph depth guides general method scheduling. Neither rule establishes optimal scheduling for arbitrary model durations.
- Keep section review and optional document relationship review explicit. Claim links resolve to exported body fields and original quotations; semantic support still requires judgment.

## Checks on the published source

| Check | Result |
| --- | --- |
| Full Python suite | 255 tests and 21 subtests passed |
| Connected Chromium journey | Markdown/PPTX upload, automatic route, budget controls, download, compact progress, targeted revision; no browser script errors |
| Package | Source archive and wheel built; packaged runtime files matched the source; installed-wheel demo completed |
| Local transport | Persistent process multiplexing, connection reuse, deadlines, restarts, structured failures and schema handling |
| OCR | Actual OCRmyPDF/Tesseract integration on an original scanned sentence; original file bytes preserved |
| Mixed-document fixture | Required facts preserved, held-out key excluded, warm calls eliminated, failures retained honestly |
| Capacity stress | 80 distinct records preserved through hierarchy, subdivision, writing and review; maximum request 29,897 bytes under a 30,000-byte ceiling |

Raw results and reproduction commands are in [benchmarks](benchmarks.md) and [optimization evidence](optimization-evidence.md). The mixed-document result includes a fingerprint of the exact Python implementation and confirms that it stayed unchanged during the run.

An independent agent reviewed the code and reproduced integration defects. Fixes cover real-adapter truncation codes, adjacency after reader subdivision, scoped cross-section relationships, claim links into discarded fields, target-batch metadata size, repeated context indexing, and complete failure receipts after sibling or assessment work. Regression tests exercise those boundaries.

## Remaining evaluation and capacity limits

No live model comparison was run. Scripted replies establish information flow and exact fixture outcomes; synthetic waits establish timing only for their declared service distributions. They do not rank model quality, OCR engines or educational usefulness.

Writing preflight measures the complete writing request and review/repair source context. Future drafts and findings are unknown. Actual requests are checked again; an oversized review keeps the draft and reports an unperformed check. A model profile is required to measure tokens; a generic byte guard cannot establish model fit.

The shared outline retains a global capacity limit. Cross-batch target reconciliation preserves existing relations but does not discover every relation between targets kept separate. Cache reuse follows declared context; it cannot discover an unstated semantic dependency. Failed HTTP responses can incur usage unavailable in the receipt.

Automatic hedging, adaptive rate control and unconditional extra audit passes were not added. Their extra requests, cancellation behavior and quality benefit need workload-specific measurement. Interactive oral cases and listened audio verification remain outside this implementation.
