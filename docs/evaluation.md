# Evaluating Lamina

Lamina's tests establish source IDs, exact quotations, assignments, cache behavior and export structure. This plan specifies how to test source comprehension, output quality, learning, case behavior and media delivery on new material.

## Measurement rules

- Freeze corpus, source roles, adapter and code revisions, prompts, tasks and rubric before comparison. Keep development and held-out questions separate; check paraphrased duplicates.
- Name the unit behind each rate: page, proposition, concept, lesson, question, learner, case transition or audio minute. Report numerator, denominator, sampling method, uncertainty interval and examples of failure. Stratify by source type, length, visual density and topic; report both pooled and source-level averages.
- Have two qualified reviewers label independently, then adjudicate. Report raw agreement and a suitable chance-adjusted statistic for nominal labels, such as [Cohen's kappa](https://journals.sagepub.com/doi/abs/10.1177/001316446002000104).
- Set acceptance rules in advance. Structural invariants may require zero violations; empirical targets need a domain-appropriate baseline and uncertainty interval. No universal pass percentage is assumed.

## Evaluation layers

| Layer and unit | Current check | Study and acceptance question |
| --- | --- | --- |
| Parsing, file/page | Ordered text and Markdown units; PDF text page locators; image-only pages fail explicitly. | Compare sampled pages with rendered originals for missing words, reading order, tables, headings and boundaries. Route unsupported classes to OCR/layout processing or exclusion. |
| Region coverage, source region | Hashes and unit IDs track ingested text. | Inventory text blocks, tables, figures, captions, formulas and image-only pages. Which critical regions were captured or marked unsupported? |
| Atomic extraction, proposition | Proposed concepts cite exact teaching-unit quotes; held-out assessment units stay excluded. | Independently annotate source propositions. Score supported precision, important-proposition recall and invented or inverted claims, including negation, quantities and exceptions. |
| Semantic merge, concept pair | Each raw concept maps to one canonical concept and retains its evidence. | Label same, related-distinct and conflicting pairs. Count harmful false merges, missed merges and lost conditions against an unmerged baseline. |
| Curriculum, lesson/objective | Extracted concepts are assigned or deferred; prerequisites point back; lessons name assigned concepts. | Judge order, task-critical deferrals and lesson boundaries against a source-order outline. The denominator is the extracted set. |
| Grounding, claim/evidence | Known unit IDs, teaching roles, exact quotes and assignment evidence are checked. | Label artifact claims supported, contradicted or unestablished by cited originals, including multi-passage support. Inspect useful citations by output surface. [FEVER](https://aclanthology.org/N18-1074/) illustrates evidence labels; the rubric here must fit the source. |
| Retrieval, prompt/answer | Optional guide/assessment targets partition extracted ideas and preserve source-exact answer items. | Ask blinded reviewers whether prompts elicit the intended answer and distinguish near alternatives. Check harmful merges and omissions separately from structural ownership. |
| Practice and transfer, learner/task | Recall, contrast and apply prompts exist; answers start hidden and local self-ratings can be saved. | Compare with source reading or simple questions at matched time. Predefine delayed, unseen near-transfer and changed-context tasks with blinded scoring. [Testing-effect](https://www.psychologicalscience.org/journals/psychological-science/j.1467-9280.2006.01693.x/) and [transfer](https://doi.org/10.1037/a0019902) studies motivate the design; they are not Lamina outcomes. |
| Assessment and case, question/path | Every assessment runs candidate-only solve calls and a separate key/evidence judge. A local examiner can reveal authored findings and one second event. | Test answerability and key quality with fresh providers and humans. For interactive cases, replay actions and time transitions, then run two-person sessions. There is no conditional patient engine or synchronized remote room. |
| Audio, script/minute | A configured adapter renders PCM WAV; Lamina checks structure, duration and hashes. `narration.txt` records synthesis input. | Listen, run independent ASR, compare words/numbers/names/timing with the script, inspect clipping, silence and navigation, then test listener understanding. |
| Time and cost, stage/accepted artifact | Cached jobs, parallel workers, resource lanes and durable results are available. | Log wall time, model tokens and charges, retries, human repair and media checks. Compare quality-matched runs; report median/tails and cost per accepted artifact. |

## Proposed case graph and publication check

For a future interactive case, let `G = (V, E)`. A node `v ∈ V` is a named patient state. An edge `e = (v, a, g, Δtₚ, v′) ∈ E` contains an examiner-asserted action `a`, guard `g`, simulated patient-time advance `Δtₚ` and successor `v′`. Each edge would carry candidate-safe releases, private interpretation, a next prompt, rubric IDs and source support. Oral time `tₒ` and patient time `tₚ` are separate.

The examiner would decide whether an utterance merits action ID `a`; code would select an authored transition and compute `O(v, R, candidate)` from state `v` and released set `R`. It would not infer treatment quality or biological response from free text. A run log could replay decisions, releases, withdrawals, marks and both clocks. Static path tests would look for contradictory branches or leaks; two-person runs would test plausibility and pacing.

Publication review would bind exact lesson/case bytes, source-unit and media manifests, reviewer, rubric, verdict and open issues. A changed branch, answer, source or image would stale the pass. Current caching and production review do not implement this independent, exact-hash case gate. Calling the same adapter again is not an independent expert review.

## First study

Use a small public corpus with prose, a table, diagram and scanned page. Build a source-region inventory and human proposition set. Compare Lamina with a source-order outline and question baseline at matched time and cost; inspect each false merge and unsupported claim. For a case, hand-author success and omission branches, replay both candidate views and run them with two people. Publish denominators, disagreements, uncertainty, defects and revisions with the result.
