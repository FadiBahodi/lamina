# Benchmarks

This page lists the repository's benchmark commands, their fixtures and the recorded results. Scripted fixtures measure engine mechanics: request construction, validation, caching, scheduling and recovery. Live model quality, latency and cost come from [live model evaluation](live-model-evaluation.md) and [calibration](calibration.md). Regenerate a result on the exact revision under review; a result from a different commit cannot establish the behavior of the published change.

## Sweep versus planned on your material

`benchmarks/sweep_vs_planned.py` runs the card sweep and a planned route on the same files with a live adapter and a cold cache per run. It records time to first useful output, time to completion, completion status, call counts, reported token usage and output density (cards or ideas per page). It spends real model calls:

```sh
python benchmarks/sweep_vs_planned.py --adapter @models.json --files chapter.pdf --runs 3 --output benchmarks/results/sweep-vs-planned.json
```

`--planned-format` selects `guide` (default), `document` or `podcast-script` for the planned arm; `--audio-adapter` adds speech to a podcast arm. Add `--canaries distinctions.txt` (one planted distinction per line) for a lexical survival count per arm. Coverage still needs a human judge, and the two routes produce different objects, so compare them against a common requested result.

## Request grouping comparison

`benchmarks/compare_execution.py` compares ordinary planned execution, grouped planned execution and the direct path using the same sources and brief. Each replicate starts with empty workspaces. The two planned variants share an identical outline, so a different planning decision cannot explain their request counts. Both totals include that outline's measured preparation cost. The direct path prepares its own request. Run order rotates between replicates.

The report retains failed attempts, calls, reported token usage, request bytes, preparation time, provider admission waits when available, time to the first provisional section and total completion time. Full requests and outputs stay beside the report for inspection; keep those files private when using private sources. The runner records the source, implementation and runner hashes.

### Local measurement

The [October 3 results](../benchmarks/results/matched-execution-2026-10-03.json), recorded at protocol `lamina-production-11`, cover ten repetitions of each variant on six original, fictional equipment statements. The fixture copies source text and applies the real engine's validation, caching and scheduling. It makes no network requests, adds no artificial delay and supplies no invented token counts.

All 30 runs completed and retained all six declared statements and their source references. The planned and grouped outputs matched exactly in every replicate. Direct execution produced one section containing the same required statements.

| Variant | Read / plan calls | Write / review calls | Request bytes |
| --- | ---: | ---: | ---: |
| Planned | 6 / 1 | 6 / 6 | 65,850 |
| Grouped, up to six sections | 6 / 1 | 1 / 1 | 51,410 |
| Direct | 0 / 0 | 1 / 1 | 12,804 |

Grouping removed ten requests and reduced serialized request bytes by 21.9% against planned execution. These byte counts describe Lamina request envelopes, not provider token usage. Grouping took slightly more local execution time in this fixture, because it adds packing and validation work while avoiding no network latency. The direct path did the least work on this small collection.

Median local completion times were 43.80 ms planned, 47.52 ms grouped and 10.07 ms direct. Median time to the first provisional section was 29.61 ms, 46.94 ms and 9.88 ms respectively. These values include parsing and planning; the raw report separates execution time. This small fixture makes grouping's local overhead visible without predicting network or model latency.

Reproduce the local comparison:

```sh
python benchmarks/compare_execution.py --replicates 10 --output /tmp/lamina-comparison
```

### Live comparison

The same runner supports the native Gemini adapter. Set `GEMINI_API_KEY` in the process environment, then choose the model explicitly:

```sh
python benchmarks/compare_execution.py --provider gemini \
  --model gemini-2.5-flash --replicates 3 --workers 4 --concurrency 4 \
  --output /private/measurements/lamina-comparison
```

`--max-calls` defaults to 100 generation calls across all three variants in each replicate. It is a call limit, not a spending limit; token counting makes additional network requests. Live runs consume the configured account's API quota. Use a new output directory for every experiment.

To measure representative material, add `--corpus corpus.json` using the [calibration manifest format](calibration.md#use-your-own-corpus). Declare the facts and qualifications to check before running. Inspect the complete outputs for errors and awkward wording, including valid paraphrases rejected by the phrase checks. A run requiring review remains visible in the summary.

Live preflight on October 3 found no `GEMINI_API_KEY`, so no live comparison has been recorded. Six phrase checks are not a complete semantic evaluation, ten local repetitions do not establish tail percentiles, and this comparison promotes no workload profile.

## Mixed-document workflow matrix

```sh
pip install '.[pdf,slides,tokens,test]'
python benchmarks/workflow_matrix.py --output benchmarks/results/workflow-matrix.json
```

The benchmark creates five PDFs and three PowerPoint files with original, invented windmill specifications. The corpus includes a condition, a negation, conflicting historical thresholds, repeated facts, a table and speaker notes. A separate held-out examiner key must never reach a production request. PDF and PowerPoint parsing use the production import path.

The provider is scripted. It copies the source, removes one known exception during writing, identifies that defect during review, and restores it during repair. The final oracle checks fifteen exact fixture facts, both historical thresholds, the restored exception and absence of the held-out key. This evaluates information flow, validation, repair and resource accounting; it cannot establish how a real model interprets unfamiliar documents.

| Case | Question it exercises |
| --- | --- |
| Direct, planned and supplied assignments | Can each route preserve the same required fixture facts? |
| Identical rerun | Which exact requests are reused? |
| Changed brief with reusable reading | Which source interpretation can be reused across products? |
| Changed brief with task-specific reading | Does a new goal trigger fresh source interpretation? |
| One edited PDF page | How far does an edit invalidate reading and writing? |
| One invalid reader quote | Does bounded feedback repair recover the individual call? |
| Persistently invalid reader quotes | Does the engine preserve an honest failure state? |
| Deliberately unqualified draft | Does the review/repair boundary restore the known exception? |

The report contains request counts by stage, request and response bytes, reference input and output token counts, cold and warm times, first draft, first review and first terminal section review. A terminal review may still contain unresolved findings. Request delays follow a seeded lognormal distribution with four available workers; their values describe the fixture, separate from live model latency and provider billing. Reference tokens use `cl100k_base`; adapters must report actual usage for cost accounting.

### Recorded fixture results

The [machine-readable run](../benchmarks/results/workflow-matrix.json) was regenerated on 2026-09-23 at protocol `lamina-production-6`; the current code is `lamina-production-11`, so these numbers describe that earlier revision. The run records implementation fingerprint `4d535d3f…` and confirms it stayed unchanged during the run. Every successful document route retained the fifteen required facts, restored the deliberately removed exception and excluded the held-out key.

| Provider calls | Direct | Planned | Supplied assignments |
| --- | ---: | ---: | ---: |
| Cold run, including a repair and recheck | 4 | 21 | 12 |
| Identical rerun | 0 | 0 | 0 |
| Changed brief, reusable reading | 4 | 13 | 12 |
| One edited PDF page | 4 | 4 | 2 |

Supplied assignments are prepared by the fixture. Their creation cost is outside the engine run; a real comparison must count an external planner unless those assignments already exist. The outputs preserve the same required facts with different section structures, and the comparison does not establish equal prose quality.

The changed-brief cases explicitly select reusable reading: the planned route reused all eight source reads after the brief changed. A separate task-specific case uses the default, and both its original run and changed-brief run make 21 calls, including eight fresh reads. Reuse saves repeated work while retaining the original inventory's interpretation and any omissions.

The fixture declares a configured workload ceiling of 512 items per stage for its finite scripted responses; it is a test setting, not an observed operating policy. The invalid-quote cases exercise the compatibility validator and correction path. A single malformed reply required one extra reader call and recovered. Persistently invalid quotes exhausted two attempts per reader and left the plan failed, and invalid material was never counted as completed work.

A separate stress fixture required eighty distinct apparatus records under a 30,000-byte request ceiling. Hierarchical planning and writer subdivision completed with 179 calls, a largest request of 29,917 bytes and all eighty required facts present. The fixture assigns one record per final section by scripted choice. Dense Unicode cases preserved four exact multilingual and notation examples. Assessment and podcast-script cases retained the required answer and script content, and the assessment solver received no source fact markers or examiner text.

Recorded cold elapsed times were 48.7 ms direct, 126.0 ms planned and 52.3 ms with supplied assignments. The synthetic provider delays are only milliseconds, so local database and interpreter work also contribute materially; do not extrapolate these values into live speedups. An explicit continuity review added five relationship calls after cached section work.

## Scheduling fixtures

```sh
PYTHONPATH=src python benchmarks/execution_scaling.py --output RESULT.json
```

The [finite-capacity scheduling result](../benchmarks/results/execution-scaling.json) compares stage barriers with independent section chains under identical work and worker limits, with lognormal service times and injected failures. Across three seeds, the median barrier/chain completion ratios were 1.35 for the variable-call fixture, 1.46 with one reviewer slot and 1.36 with failures. A constructed case reverses the result: barriers complete in nine service-time units and chains in ten. Earlier completed sections and an earlier complete document are different outcomes. [Flow geometry](flow-geometry.md#separate-total-work-from-the-longest-chain) gives the inequality these runs test.

The same result times graph bookkeeping. On a reversed 1,024-node chain, adjacency construction, topological validation and depth ranking took 1.14 ms versus 16.65 ms for repeated readiness scans on the recording machine. Inference time is excluded. No live models, token costs, network quotas, provider retry delays or output quality are measured.

## Method runtime fixture

```sh
python benchmarks/run_method_example.py --output benchmarks/results/method-runtime.json
```

The script runs `tests.test_method_runtime`, then calls `method_demo()` ten times in fresh workspaces. Each call creates a guide, edits a deployment note and applies a selected observation. Assertions check cached and executed nodes, dependency context, captured requests, observation family and the changed guide. Passing runs write the [recorded result](../benchmarks/results/method-runtime.json).

`wall_ms` comes from the runtime's monotonic clock. The report contains all samples, the median and the nearest-rank p95: sorted position `ceil(0.95 × n)`, counting from one, so with ten samples p95 is the maximum. The timings cover local fixture execution and SQLite. Model latency, token cost, source understanding, guide quality, learning and delivery require other measurements.

## Deterministic regressions

The test suite covers support propagation, invalidation from supporting text alone, unknown references, three-source comparison expansion, shuffled nomination, shared-pool reader splits, six-section batching, local retry and repair, audio segment reuse, large raw uploads and bounded preview delivery. The six-section fixture makes one write and one review request with grouping, versus six of each without it, while holding all six outputs and evidence records constant. `lamina demo --output DIR` runs the production engine's deterministic fixture (two short original notes, a scripted adapter, no credentials) and exports `index.html`, `document.md`, `plan.json` and `report.json`; in the same fixture module, revising one of three sections hits cache on six of eight requests and reruns only that section's write and review. These exact responses test mechanics. They establish no live model behavior, large-collection timing, OCR throughput, dense-retrieval recall, assessment quality or listening quality.

## Earlier measurements

An original deterministic fixture of 100 stored units, 25,000 words and ten section assignments with fixed responses tracked request construction and reader defaults across three protocol revisions. It scores neither parsing nor model output.

| Measure | `lamina-production-3` (commit `539b7f8`) | `lamina-production-4` (source workflow rewrite) | `lamina-production-6` |
| --- | ---: | ---: | ---: |
| Reader calls | 100 | 17 | 1 |
| Reader source words sent | 123,500 | 25,000 | 25,000 |
| Reader source repetition | 4.94× | 1.00× | 1.00× |
| Total cold calls | 121 | 38 | 22 |
| Reference input tokens, all stages | 325,626 | 144,580 | 131,749 |
| Provider calls on repeat writing | 0 | 0 | 0 |
| Provider calls for one section revision | 2 | 2 | 2 |

Reference tokens use `cl100k_base` over serialized requests; they are not billed tokens. Between the first two revisions, total calls fell 68.6% and reference input tokens fell 55.6%, from removing default neighboring overlap, packing reader batches and shortening writer context. The `lamina-production-6` run declares a configured ceiling of 100 items per stage and returns fixed short ideas, so its single reader call reflects that finite oracle and says nothing about a suitable textbook batch size. None of these figures is a wall-time, monetary-cost or quality measurement, and explicit context can still be necessary on real material.

Only the [`lamina-production-6` result](../benchmarks/results/source-workflows-current.json) is checked in; the earlier columns are retained from their recorded runs. Reproduce a column with `python benchmarks/source_workflows.py --repo CHECKOUT --output RESULT.json` against the matching checkout.
