# Live model evaluation, September 2026

The first live experiments used Gemini 2.5 Flash on pediatric orthopedics excerpts. They exercised PDF import, source reading, planning, writing, review and repair. They found failures in request construction, source markers and the evaluator that the scripted tests had missed.

## Configuration

The native adapter used `models/gemini-2.5-flash`, temperature 0.2, an 8,192-token output allowance, a 1,024-token thinking budget and four concurrent requests. It called Gemini's `countTokens` endpoint with the same rendered input used for generation. Each trial began with an empty Lamina cache. Provider-side cached tokens are reported separately.

The larger source was an eight-page, approximately 5,354-word textbook excerpt. A two-page excerpt supported the smaller writer experiment. The sources and model responses remain private; the [public measurements](../benchmarks/results/live-model-2026-09-24.json) contain hashes, configuration, timings, token counts and aggregate check results. The original evaluation checked four clinical distinctions on the larger source and two on the smaller source.

## What the trials changed

| Observed failure | Change |
| --- | --- |
| A reader needed the next page to finish a sentence, and the extended request exceeded its 4,000-token policy | Context requests remain subject to the full request limit. The failed trial is retained; a context extension can require a larger policy. |
| Hierarchical planning requested source references from summary cards that had none | Summary-card outlines return no evidence relationships; assignment restores the original source references. |
| An empty overview section survived a retry because the validation error was vague | Feedback identifies the empty section and explains how to attach an overview to populated sections. |
| Reader repairs repeated reversed or cross-page span ranges | Feedback names the endpoints and explains the valid range or multiple-reference form. |
| Valid citation markers in nested lists, spaced lists of IDs and clinical comparisons were rejected | Marker parsing follows Markdown structure and accepts the supported range and list syntax. |
| Reviewers copied citation markers inserted into displayed source text, producing invalid quotations | Reviewers receive original text. Writers receive addressed text for their inline citations. |
| Reviewers returned approval statements as defects | Review instructions specify an empty findings list when no material defect exists. |
| The evaluator split PDF line wraps and rejected facts present in the source and output | Version 3 joins prose wraps while retaining sentence and Markdown boundaries. Source controls run before paid calls. |

Reader calls retain valid rows during a correction. A failed stage leaves completed calls cached for recovery. Calibration intentionally starts fresh for each replicate so reuse cannot disguise the work required.

## Initial measurements

The two eight-page trials under protocol 7 failed after 105.95 and 205.50 seconds. Reported total usage was 84,157 and 408,595 tokens respectively. Under protocol 8, the two trials failed after 221.74 and 35.41 seconds, using 558,604 and 43,739 tokens. These totals include input, candidate output and model thinking as reported by the provider.

The smaller protocol 8 experiment varied the writer ceiling between three and six ideas:

| Ceiling | Replicate | Result | Wall time | Total tokens |
| ---: | ---: | --- | ---: | ---: |
| 3 | 1 | Artifact produced; engine still required review | 70.50 s | 91,219 |
| 3 | 2 | Planning failed on an empty section | 38.54 s | 15,029 |
| 6 | 1 | Review quotation validation failed | 58.17 s | 93,627 |
| 6 | 2 | Review referenced an unknown source unit | 69.21 s | 90,114 |

Every writer call that ran owned one idea. Neither ceiling constrained those calls, so this experiment provides no three-versus-six capacity comparison. It measured the full pipeline's reliability and exposed the review failures above. A writer-capacity experiment needs a fixed upstream plan with sections that actually exercise the chosen loads.

The original evaluator scored the completed artifact zero out of two because it could not match the source's line-wrapped sentences. A separate rescore with evaluator version 3 found both facts in extraction, assignment, the draft and the finished output. The original report remains unchanged, and the engine's unresolved review status remains part of the result.

A preceding 4,000-token probe failed after 29.81 seconds when requested neighboring context exceeded that policy. A second probe lost its aggregate summary to a measurement-code error. Its saved stage jobs remain available, but it has no reliable aggregate token total. Every later trial writes each model response and its usage to disk immediately.

## Interpretation

These runs measure actual provider work and explain several reliability fixes. They do not locate a quality-versus-load threshold. The clinical checks cover selected distinctions; human evaluation of the complete artifacts remains outstanding. No workload profile was promoted from the initial trials.

Use [calibration](calibration.md) to test a representative corpus with declared checks. Keep source controls, failures and posthoc rescoring distinct in the record. [Engineering decisions](engineering-decisions.md) connects the design to historical workloads and the alternatives considered.

## Protocol 9 confirmation

The source controls passed before all four confirmation trials. The private clinical excerpt and the bundled original equipment corpus were tested independently, with two cold trials each and an 8,000-token reader ceiling.

| Corpus | Replicate | Engine outcome | Wall time | Total tokens |
| --- | ---: | --- | ---: | ---: |
| Clinical, two pages | 1 | Planning failed on empty sections | 40.29 s | 16,180 |
| Clinical, two pages | 2 | Ready | 49.94 s | 36,167 |
| Original equipment fixture | 1 | Finished with unresolved review findings | 64.17 s | 51,275 |
| Original equipment fixture | 2 | Review used an unknown unit ID | 47.90 s | 40,591 |

The ready clinical artifact passed one of two lexical checks at extraction and one of two at output. These were different checks: the writer recovered one distinction from its source, while another was expressed across two sentences and failed the evaluator's local-statement rule. The equipment artifact passed three of six output checks. These results are insufficient to promote a profile, and a lexical failure needs inspection before being counted as lost meaning.

Review traces showed repeated complaints about a space left before punctuation after citation-marker removal. The parser now removes that separator at the marker boundary. It also preserves escaped literal citation notation and keeps code and links separate from active citations.

## Released protocol 10

Two further cold trials used the same two-page clinical corpus after the marker punctuation fix:

| Replicate | Outcome | Wall time | Input | Output | Thinking | Total tokens |
| ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | Ready; both checks passed at extraction, assignment and output | 35.42 s | 32,585 | 3,464 | 8,772 | 44,821 |
| 2 | Planning failed on empty sections after its correction attempt | 57.37 s | 7,806 | 11,111 | 2,392 | 21,309 |

The successful trial made 14 model calls and produced six sections. Both readers received 2,519 input tokens under the configured 8,000-token ceiling. That is the observed reader load; the ceiling is not a measured capacity threshold. The failed replicate prevents promotion, so the release ships configured starter policies and no observed recommendation from these trials.

The remaining planning failure is reproducible: the model sometimes creates empty overview sections even though every executable section needs assigned material. The engine retains the failed record and completed reading. The next planning comparison should test a clearer overview representation against this frozen baseline. Human-labeled output checks are also needed before using lexical scores to choose a quality threshold.
