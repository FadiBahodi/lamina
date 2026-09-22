# Measuring Lamina

This protocol compares complete source-to-artifact work, including correction and delivery. The [systems benchmark](benchmarks.md) measures synthetic scheduling; the [evaluation plan](evaluation.md) defines parser, source, semantic, learner and media checks. Neither reports a comparative product result.

## Fix the task and reference set

Choose a public or permissioned corpus not used to design the method. Include prose, a table, a figure, a difficult or scanned page, overlapping sources, a conflict and a plausible omission. Specify the learner, deadline, output forms, source roles, quality rubric and delivery surface. Two qualified reviewers should independently inventory important answer objects, qualifiers, visual dependencies and acceptable omissions from rendered originals. Keep their initial labels, adjudication rules and uncertainty.

Separate teaching sources, form exemplars and held-out questions. Give compared systems the same allowed examples; check for duplicate or paraphrased evaluation items. Freeze corpus hashes, brief, method and adapter revisions, model IDs, budgets, concurrency limits, operator instructions and acceptance rules before any run.

## Compare complete journeys

On the same brief, compare a careful human-assisted source-order workflow, Lamina's fixed pipeline and its generic method runtime where each applies. Add Manus or NotebookLM when accounts and source rights permit, using their documented features and capable operators. A LangGraph baseline requires a built workflow; count its implementation time separately. Match scope and deliverables. Hold the model/provider constant for an internal runtime comparison. Across products with different models, report the combined system result.

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

## Instrument execution and repair

For each job, record version, dependencies, input/output digests, lane, enqueue/start/end times, service time, cache state, retries, errors and invalidations. Current method receipts contain status, lane, dependencies, request bytes, wall time and output digest or error. Queue times, tokens, charges and invalidation counts need further instrumentation. Record provider-reported input/output tokens, model revision and charges when available. Label estimates with their tokenizer and price source. Keep CPU/GPU use, storage, transfer, human minutes and subscriptions in separate units. Cache retrieval and verification still cost time.

Measure context amplification by stage and overall: `A = Σ input tokens / distinct accepted source-text tokens`. Report the largest request, source coverage and artifact quality beside `A`: some repeated context prevents boundary errors. For service work `W = Σ t_i`, longest dependency path `D`, lane work `W_r` and lane capacity `c_r`, `T ≥ max(D, max_r W_r/c_r)` is a lower bound. Compare it with observed time and account for variable calls, queue waits, throttling, retries and human work.

After the first output, seed a local wording defect and a missing idea that should change the global route. Record reopened nodes, service cost, human repair, replaced artifacts and stale review verdicts. Failure locality is affected work divided by relevant work; inspect skipped dependencies before crediting a small repair. Interrupt a worker and resume from durable state, checking stale-owner rejection and cache identity. These test different failure modes.

For each resource lane, log arrivals, service-time distribution, active capacity, throttling and wait percentiles. Use a queue model only if batch arrivals, correlated calls and shared rate limits fit its assumptions. Compare widths at similar scope and quality. Report cost and time per accepted artifact, including review.

## Test transfer

Give a fresh agent or operator the saved method and a new corpus, without the original conversation. Observe source-role choices, dependencies, answer objects and whether prior methods are applied selectively. Include a task where the favored teaching form is wrong. Compare proposed method revisions with the previous version on held-out tasks and record gains and losses before promotion.

Publish lawful corpora or substitutes, briefs, labels and disagreements, redacted traces, failures, costs and artifact hashes. Report separately what ran, passed structural tests, was accepted by reviewers and was used by learners. Repeated quality-matched comparisons are needed for a competitive claim.
