# Rewrite validation — 2026-09-23

This review covers version 0.10.0 from source import through planning, writing, checking, revision and export. Its central change separates request capacity from the amount of semantic work assigned to a call.

## Decisions

- Keep hard transport, context and output limits. Apply independent stage workload limits to complete input tokens or owned objects. Every configured limit has an explicit basis; an observed policy links a digest-checked report for the matching provider and protocol. These records establish provenance. Quality thresholds require matched evaluation.
- Read for the current brief by default. Without a reading workload policy, each call owns one parser structure. Slide companions remain together. Combining structures requires declared limits; a large indivisible structure still needs explicit decomposition or a revised policy.
- Require policies before multi-item planning, writing and review. The writer checks all visible source units and extra exemplars or retained observations when deciding whether an unprofiled call is permissible. Planned mode checks required profiles before beginning paid source reads.
- Give readers deterministic source-span references. Code resolves exact Unicode-character offsets to original quotations. Source text appears once in the reading request. Valid location references leave semantic support and completeness to separate evaluation.
- Preserve accepted extraction rows during local corrections. A correction supplies replacements for invalid indices under the existing attempt allowance. Malformed envelopes can still require full replacement; unresolved material never becomes a successful cache entry.
- Make reusable inventories explicit. Changed briefs use task-specific reading unless reuse is selected. Plans and receipts retain `semantic_recall: "unmeasured"` even when all enabled workflow checks complete.
- Bound grouping and assignments while revisiting original idea explanations. Writers receive original passages and declared context. Exact source revision binding, independent section chains, local caching and persistent transport remain in place.
- Evaluate complete outputs across declared experimental loads. The new harness records fragile facts by source position through extraction, assignment, initial drafts and finished bodies. It can call a configured real provider; its shipped scripted case exposes a deliberate silent omission.

## Validation evidence

The following checks ran against the frozen runtime used for the release artifacts. Remote CI results are recorded on the [pull request](https://github.com/FadiBahodi/lamina/pull/1).

| Check | Result |
| --- | --- |
| Full Python suite | 315 tests and 21 subtests passed |
| Independent review | 57 focused tests passed; no unresolved blocking findings |
| Connected browser journey | Chromium 134 / Playwright 1.51: Markdown/PPTX import, task-reading default submitted and saved, direct writing, download and targeted revision passed; no script errors |
| Package | Version 0.10.0 source archive and wheel built; all 72 packaged runtime files matched the source byte for byte |
| Fresh wheel installation | Imported the installed package; 14-job demo and `studio-site --pdf` completed |
| Mixed-document matrix | 22 cases passed their assertions, including the expected persistent-reader failure |
| Workload stress | 80 required facts preserved through 179 scripted calls; largest request 29,917 bytes under a 30,000-byte ceiling |
| Silent-omission controls | Background loads of 6 and 20 both preserved five of six canaries and failed the required preservation threshold, as intended |

The [adversarial scripted case](../benchmarks/results/quality-silent-omission.json) returns valid records and cites every source unit. The engine reaches `ready`, while one of six specified canaries is absent from the finished prose. The quality evaluator detects that omission and returns a failing result. This establishes that operational completion and citation coverage can coexist with a known content loss.

The [mixed-document result](../benchmarks/results/workflow-matrix.json) records runtime fingerprint `4d535d3f60ec95dda3f8dfa4a0c3026bcab5ddb6ca150784b8591a1b56b50ef1` and confirms it stayed unchanged during the run. The mixed-document and workload stress fixtures use declared scripted policies. Their request counts, cache results and exact fixture outcomes describe implementation mechanics. See [benchmarks](benchmarks.md), [optimization evidence](optimization-evidence.md) and the [quality evaluation protocol](quality-evaluation.md) for reproduction and scope.

## Remaining evaluation and limits

No live model workload curve, recall estimate, billing comparison or latency comparison was measured. Operator-selected limits remain provisional. A linked observation report identifies what ran; it does not certify performance on unfamiliar sources. The quality harness checks declared lexical controls and known counterfacts, so representative human review remains necessary.

A structural reading fallback can still be difficult for the selected model. Well-formed replies can omit facts without truncating. No universal density trigger, output-occupancy threshold, repeated-read rate or capture–recapture certificate is inferred.

The shared outline and required source context must fit their configured limits. Future drafts and findings are unknown during preflight; actual requests are checked when available, and an oversized review remains explicitly unperformed. Cross-batch target reconciliation does not discover every relation between targets retained separately. Cache reuse cannot discover an undeclared semantic dependency.

Figures, PDF reading order and OCR quality need evaluation on the actual files. This release does not compare OCR engines or repeat the earlier OCR integration measurement. Interactive oral-case delivery and listened audio verification remain outside the implementation.
