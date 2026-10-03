# Measuring Lamina

Lamina's tests establish source IDs, exact quotations, ownership, cache behavior and export structure. This protocol specifies how to measure source comprehension, output quality, learning and media delivery on new material, and how to compare complete source-to-artifact work, including correction and delivery, with other approaches. [Benchmarks](benchmarks.md) records fixture results and [calibration](calibration.md) measures workload limits on a chosen model; neither reports a comparative product result.

## Measurement rules

- Freeze corpus, source roles, adapter and code revisions, prompts, tasks and rubric before comparison. Keep development and held-out questions separate; check for paraphrased duplicates.
- Name the unit behind each rate: page, proposition, card, section, question, learner, case transition or audio minute. Report numerator, denominator, sampling method, uncertainty interval and examples of failure. Stratify by source type, length, visual density and topic; report both pooled and source-level averages.
- Have two qualified reviewers label independently, then adjudicate. Report raw agreement and a suitable chance-adjusted statistic for nominal labels, such as [Cohen's kappa](https://journals.sagepub.com/doi/abs/10.1177/001316446002000104).
- Set acceptance rules in advance. Structural invariants may require zero violations; empirical targets need a domain-appropriate baseline and uncertainty interval. No universal pass percentage is assumed.

## Evaluation layers

| Layer and unit | Current check | Study and acceptance question |
| --- | --- | --- |
| Parsing, file/page | Ordered Markdown, text and slide units; PDF text with page locators; pages with no extractable text stop the import. | Compare sampled pages with rendered originals for missing words, reading order, tables, headings and boundaries. Route unsupported classes to OCR/layout processing or exclusion. |
| Region coverage, source region | Hashes and unit IDs track ingested text; coverage reports list considered and uncited units. | Inventory text blocks, tables, figures, captions, formulas and image-only pages. Which critical regions were captured or marked unsupported? |
| Extraction, proposition | Reader ideas cite exact spans from owned units; held-out assessment sources stay excluded. | Independently annotate source propositions. Score supported precision, important-proposition recall and invented or inverted claims, including negation, quantities and exceptions. |
| Cards, card/window | Sweep readers write prompt/answer cards with span citations; local similarity suppresses near-duplicates and records the score; a sampled audit reports omissions and unsupported cards. | Label sampled windows for testable facts and unsupported cards. Compare audit findings with those labels in audited and unaudited windows, and check suppressed cards for distinct claims removed as duplicates. |
| Organization, idea/section | Every original idea has one section owner or a recorded omission; the grouping tree is saved. | Judge section boundaries, order and task-critical omissions against a source-order outline. The denominator is the extracted set. |
| Semantic merge, idea pair | Retrieval targets and evidence comparison keep every member idea and its evidence; a different-context relation cannot be merged. | Label same, related-distinct and conflicting pairs. Count harmful false merges, missed merges and lost conditions against an unmerged baseline. |
| Grounding, claim/evidence | Writer markers resolve to exact spans supplied to the section; claim records link output text to quotations. | Label artifact claims supported, contradicted or unestablished by cited originals, including multi-passage support. Inspect useful citations by output surface. [FEVER](https://aclanthology.org/N18-1074/) illustrates evidence labels; the rubric here must fit the source. |
| Retrieval, prompt/answer | Optional guide/assessment targets partition extracted ideas and preserve source-exact answer items. | Ask blinded reviewers whether prompts elicit the intended answer and distinguish near alternatives. Check harmful merges and omissions separately from structural ownership. |
| Practice and transfer, learner/task | Card decks and assessments export prompts with separate answers; Lamina records no learner outcomes. | Compare with source reading or simple questions at matched time. Predefine delayed, unseen near-transfer and changed-context tasks with blinded scoring. [Testing-effect](https://www.psychologicalscience.org/journals/psychological-science/j.1467-9280.2006.01693.x/) and [transfer](https://doi.org/10.1037/a0019902) studies motivate the design; they are not Lamina outcomes. |
| Assessment, question | Every assessment runs candidate-only solve calls and a separate key/evidence judge. There is no live staged oral-case administration. | Test answerability and key quality with fresh providers and humans. For a staged case, replay authored paths and run two-person sessions; [workflow design](workflow-design.md#proposed-case-graph-and-publication-check) describes the case graph such a test needs. |
| Audio, script/minute | A speech adapter renders sections on a bounded lane; delivery assembles episode and programme WAV files, checks structure, duration and hashes, and records synthesis input in `narration.txt`. | Listen, run independent ASR, compare words, numbers, names and timing with the script, inspect clipping, silence and episode transitions, then test listener understanding. |
| Time and cost, stage/accepted artifact | Receipts record calls, attempts, cache outcomes, request sizes, reported usage and wall time. | Log wall time, model tokens and charges, retries, human repair and media checks. Compare quality-matched runs; report median, tails and cost per accepted artifact. |

## Fix the task and reference set

Choose a public or permissioned corpus not used to design the method. Include prose, a table, a figure, a difficult or scanned page, overlapping sources, a conflict and a plausible omission. Specify the learner, deadline, output forms, source roles, quality rubric and delivery surface. Two qualified reviewers should independently inventory important answer objects, qualifiers, visual dependencies and acceptable omissions from rendered originals. Keep their initial labels, adjudication rules and uncertainty.

Separate teaching sources, form exemplars and held-out questions. Give compared systems the same allowed examples; check for duplicate or paraphrased evaluation items. Freeze corpus hashes, brief, method and adapter revisions, model IDs, budgets, concurrency limits, operator instructions and acceptance rules before any run.

## Compare complete journeys

On the same brief, compare a careful human-assisted source-order workflow, Lamina's production engine and its generic method runtime where each applies. Add Manus or NotebookLM when accounts and source rights permit, using their documented features and capable operators. A LangGraph baseline requires a built workflow; count its implementation time separately. Match scope and deliverables. Hold the model/provider constant for an internal runtime comparison. Across products with different models, report the combined system result.

Run paired tasks across several corpora and task types, rotating order. Record time to first draft and to an accepted artifact accessible on the intended device. Include setup, inspection, corrections, media checks and delivery. Keep failures and timeouts in the latency distribution. Report raw count, range, median and 90th percentile; small samples support little tail precision.

| Measure | Denominator and evidence | Limit |
| --- | --- | --- |
| Source-region coverage | Human-inventoried text, tables, figures and scans; usable capture or marked unsupported region | Capture alone says little about understanding |
| Important-object recall | Adjudicated task-relevant answers: represented, acceptably omitted, missed or wrong | The reference inventory may miss objects |
| Qualifier preservation | Labeled numbers, conditions, exceptions, contrasts and source conflicts | Separate from learner retention |
| Grounding | Artifact claims checked against original cited regions: supported, contradicted or unestablished | Limited to the task corpus |
| Retrieval quality | Blinded reviewers judge prompts against answer objects; learners answer after a delay where feasible | One task cannot establish general learning |
| Editorial usability | A new operator locates a seeded omission, explains it, repairs it and finds the revised file | Task-specific result |
| Delivery | Artifact hash or URL, open/play check on target surface, media QA when relevant | Access does not show use |

Report harmful merges and missing central answers individually. Blind reviewers to product where feasible. Set a rule in advance for defects that fail acceptance despite a high average score. Citation counts, page counts and a model's `pass` response cannot replace the judgments above.

## Adjacent products

This table uses linked official documentation checked on 21 September 2026. It identifies overlap and a testable reason to choose Lamina; it is not a benchmark.

| Product | Documented capability | What Lamina must test |
| --- | --- | --- |
| [Manus Wide Research](https://help.manus.im/en/articles/11960169-what-is-wide-research) | Decomposes suitable tasks into up to 20 parallel subtasks. Its [architecture account](https://manus.im/blog/manus-wide-research-solve-context-problem) describes independent contexts and central synthesis. | Whether Lamina's source decisions and repair trace help on a specified document task. Parallel agents already exist. |
| [Manus Project Skills](https://manus.im/blog/manus-project-skills) and [self-updating Projects](https://manus.im/blog/manus-projects-self-updating) | Curated skills and proposed reusable project updates, subject to approval. | Whether a retained method revision changes future work and passes a held-out comparison. Saving observations alone is insufficient. |
| [NotebookLM / Gemini Notebook](https://support.google.com/gemininotebook/answer/16212820?hl=en) | Source-based Audio Overviews with format, focus, length and language controls, sharing and interactive listening. [Flashcards and quizzes](https://support.google.com/gemininotebook/answer/16958963?hl=en) are also documented. | Whether Lamina's source inventory, retrieval targets and revision process produce an artifact better suited to a stated objective. Audio, flashcards and quizzes are existing product features. |
| [LangGraph](https://docs.langchain.com/oss/python/langgraph/graph-api) | Graph nodes, edges, shared state, loops and parallel supersteps; [persistence](https://docs.langchain.com/oss/python/langgraph/persistence) and [interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts). | Whether Lamina's document-specific representation and workflow add value beyond a well-built graph application. Count that application's build effort. |

Public documentation cannot reveal every vendor's internal cache, source policy or review process. Claims of speed and quality from any vendor, including Lamina, need the same task-level test.

The testable competitive hypothesis is specific: for a defined source set and output, a person can locate and repair a missed or misgrouped item with less total work while reaching comparable judged quality. Lamina may lose on first-draft speed, media polish, tool access or setup time. A quality-matched test would determine whether the repair benefit matters enough to the intended users.

## Instrument execution and repair

For each job, record version, dependencies, input/output digests, lane, enqueue/start/end times, service time, cache state, retries, errors and invalidations. Production receipts contain calls, attempts, cache outcomes, request sizes, reported usage and wall time. Method receipts contain status, lane, dependencies, request bytes, wall time and output digest or error; their queue times, tokens, charges and invalidation counts need further instrumentation. Record provider-reported input/output tokens, model revision and charges when available. Label estimates with their tokenizer and price source. Keep CPU/GPU use, storage, transfer, human minutes and subscriptions in separate units. Cache retrieval and verification still cost time.

Measure context amplification by stage and overall, and compare observed completion time with the work/span lower bound; [flow geometry](flow-geometry.md) defines both. Report the largest request, source coverage and artifact quality beside the amplification, because some repeated context prevents boundary errors. Account for variable calls, queue waits, throttling, retries and human work when comparing observed time with the bound.

After the first output, seed a local wording defect and a missing idea that should change the global route. Record reopened nodes, service cost, human repair, replaced artifacts and stale review verdicts, which together give the repair cost defined in flow geometry. Failure locality is affected work divided by relevant work; inspect skipped dependencies before crediting a small repair. Interrupt a worker and resume from durable state, checking stale-owner rejection and cache identity. These test different failure modes.

For each resource lane, log arrivals, service-time distribution, active capacity, throttling and wait percentiles. Use a queue model only if batch arrivals, correlated calls and shared rate limits fit its assumptions. Near saturation, small service-time changes can sharply increase waiting. Compare widths at similar scope and quality, and report cost and time per accepted artifact, including review.

## Test transfer

Give a fresh agent or operator the saved method and a new corpus, without the original conversation. Observe source-role choices, dependencies, answer objects and whether prior methods are applied selectively. Include a task where the favored teaching form is wrong. Compare proposed method revisions with the previous version on held-out tasks and record gains and losses before promotion.

Publish lawful corpora or substitutes, briefs, labels and disagreements, redacted traces, failures, costs and artifact hashes. Report separately what ran, passed structural tests, was accepted by reviewers and was used by learners. Repeated quality-matched comparisons are needed for a competitive claim.

## First study

Use a small public or permissioned corpus containing prose, a table, a diagram, a scanned page and related questions. Freeze a source-region inventory, then have reviewers build a proposition set and label important answers, omissions, conflicts and unsupported claims. Build a route and two output forms, and compare Lamina with a source-order outline and a question baseline at matched time and cost, inspecting each false merge and unsupported claim.

After review, introduce a missing-item finding, repair it and record which jobs and artifacts changed. Ask an unfamiliar user to locate and correct the omission, then find the delivered revision. Measure context use, rework, quality and cost. For a staged case, hand-author success and omission branches, replay both candidate views and run them with two people. Publish denominators, disagreements, uncertainty, defects and revisions with the result.

## Decisions that depend on these measurements

- **Source families.** Evaluate reference writing, podcast design and case generation separately. A correct generic section is insufficient evidence that a case has a sensible reveal order or that an audio script survives speech generation.
- **Planning.** The streaming planner already starts grouping while reads run and releases each grouping level when a batch is full; the outline and assignment remain shared decisions. Keep global reconciliation where ownership or cross-family conflicts require it, and test any earlier release of outline or assignment work against the current planned baseline.
- **Workload settings.** Reading size, the direct-writing crossover, grouping depth, model assignment, review coverage and concurrency are hypotheses about a workload. Keep their values distinguishable from hard provider limits and exact source contracts; no universal word count or neighboring-page count determines semantic context.
- **Caching.** Compare repeated runs and selective repairs using source, prompt, model and workload identities. Record where a reused result came from when adding cross-project reuse.
- **Reusable methods.** Store applicability, context requirements and observed outcomes together, then evaluate whether a later task chooses or changes its method because of that record.
