# Systems benchmarks

## Live model runs

The September 24 [model evaluation](live-model-evaluation.md) records actual Gemini calls on clinical source material, including failed trials, token usage and the changes those failures prompted. The [calibration guide](calibration.md) explains how to run the same pipeline on your own material.

## Workflow and scheduling fixtures

The current [mixed-document evaluation](optimization-evidence.md) imports five PDFs and three PowerPoint decks, then exercises direct, planned and supplied-assignment workflows through writing, review, repair and source revision. Its [raw result](../benchmarks/results/workflow-matrix.json) records each stage. Responses and delays in this fixture are scripted. Live runs are reported separately above.

The [quality evaluation](quality-evaluation.md) separately checks known facts through extraction, assignment and finished prose. Its [scripted silent-omission result](../benchmarks/results/quality-silent-omission.json) demonstrates a failure that successful execution does not catch: every source unit is cited and the engine returns `ready`, but a negation disappears and only five of six canaries survive. The oracle catches this at both tested background loads. This checks detection of the injected defect.

The [finite-capacity scheduling result](../benchmarks/results/execution-scaling.json) compares identical work and worker limits with variable service times and injected failures. Across three seeds, the median barrier/chain ratios were 1.35 for the variable-call fixture, 1.46 with one reviewer slot, and 1.36 with failures. A constructed case reverses the result: barriers complete in nine service-time units and chains in ten. Earlier completed sections and earlier complete documents are different outcomes.

On a reversed 1,024-node chain, adjacency construction, topological validation and depth ranking took 1.14 ms versus 16.65 ms for repeated readiness scans on this machine. This measures graph bookkeeping; inference time is excluded. Reproduce with `PYTHONPATH=src python benchmarks/execution_scaling.py --output RESULT.json`.

The [25,000-word fixture result](../benchmarks/results/source-workflows-current.json) was regenerated with production protocol revision 6. It makes 22 cold calls (one read, one route, ten writes and ten reviews), zero repeat calls and two calls for one section revision. Reader source exposure is 1.00×. Its scripted provider explicitly declares a configured ceiling of 100 items per stage and returns fixed short ideas; it has no real model output limit. The single reader call measures this finite oracle's mechanics and provides no evidence for a suitable textbook batch size. The runtime now supplies starter policies and a calibration command; the older fixture remains useful for comparing execution mechanics.

## Earlier measurements

The following results describe their named revisions and fixtures.

## Source workflow rewrite

An original deterministic fixture compares baseline commit `539b7f8` with the source workflow rewrite. Both use the same 100 stored units, 25,000 words, ten section assignments and fixed responses. This isolates request construction and reader defaults; it does not score parsing or model output quality.

| Measure | Baseline | Rewrite |
| --- | ---: | ---: |
| Reader calls | 100 | 17 |
| Reader source words sent | 123,500 | 25,000 |
| Reader source repetition | 4.94× | 1.00× |
| Total cold calls | 121 | 38 |
| Reference input tokens, all stages | 325,626 | 144,580 |
| Provider calls on repeat writing | 0 | 0 |
| Provider calls for one section revision | 2 | 2 |

Reference tokens use `cl100k_base` over serialized requests; they are not billed tokens. Total calls fell 68.6% and reference input tokens fell 55.6% on this fixture. This result comes from removing default neighboring overlap, packing reader batches, and shortening writer context. It is not a measured wall-time, monetary-cost or quality improvement. Explicit context can still be necessary on real material.

Reproduce with `python benchmarks/source_workflows.py --repo CHECKOUT --output RESULT.json` for each checkout. Raw results are in [baseline](../benchmarks/results/source-workflows-baseline.json) and [rewrite](../benchmarks/results/source-workflows-rewrite.json). Small direct workflows are separately covered by contract and browser tests: writing plus review uses two calls, with no reader or planner.


`benchmarks/run_systems.py` uses the real `Workspace.run_cached` SQLite claim, lease, result and cache path. Handlers sleep for declared durations and return small JSON objects. They make no model calls or media files. The default graph has 24 independent extraction jobs, one reconciliation and one planning job in series, then six independent author-to-review chains.

Run from a clean clone with Python 3.11 or newer; no optional dependencies are needed:

```sh
python3 benchmarks/run_systems.py --output benchmarks/results/my-machine.json
```

`--units` and `--lessons` change job counts. The default tests worker widths 1, 4 and 8 in fresh temporary SQLite workspaces, with one cold and one warm run per width. The script asserts 38 cold handler calls and zero warm calls. Its JSON records phase and total wall times, peak simultaneous handlers, calls, job states, Python/SQLite/platform details, sleeps and idealized bounds. It contains no source documents or credentials.

## Observed local run

The checked-in [result](../benchmarks/results/local-systems-2026-09-21.json) is one run per width on Darwin arm64, 12 reported logical CPUs, Python 3.14.7 and SQLite 3.53.4, dated 2026-09-21. There are no confidence intervals.

| Width | Cold wall | Sleep-only phase ideal | Peak handlers | Cold calls | Warm wall | Warm calls |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 2.412 s | 2.160 s | 1 | 38 | 0.022 s | 0 |
| 4 | 0.865 s | 0.780 s | 4 | 38 | 0.022 s | 0 |
| 8 | 0.595 s | 0.510 s | 8 | 38 | 0.018 s | 0 |

At width 8, extraction took 0.191 s, reconciliation 0.127 s, planning 0.123 s and author/review 0.154 s. The global steps stay serial. Scheduling, SQLite transactions and serialization account for part of the gap from sleep-only time. Warm runs read cached rows instead of calling handlers.

Synthetic service work is `W = 24(0.05) + 0.12 + 0.12 + 6(0.08 + 0.04) = 2.16 seconds`. The longest path is `D = 0.05 + 0.12 + 0.12 + 0.08 + 0.04 = 0.41 seconds`. The work/span lower bound `max(W/p, D)` is 2.16, 0.54 and 0.41 seconds at widths 1, 4 and 8. Because the fixture uses equal-duration sleeps and stage barriers, its tighter sleep-only schedule is `ceil(24/p)×0.05 + 0.12 + 0.12 + ceil(6/p)×(0.08+0.04)`: 2.16, 0.78 and 0.51 seconds. Unlimited workers still leave the 0.41-second longest path.

## Context and scaling limits

The fixed guide extractor sends one core unit plus up to 450 characters from each adjacent unit in the same source (`src/lamina/pipeline.py`). If core text totals `B` characters across `U` units, extraction source-text exposure is at most `B + 900U` characters, before headings, IDs, instructions and JSON. Source boundaries lower the actual halo. Log bytes and tokens per stage and the largest request; smaller cores can repeat more halo and prompt overhead.

The real reconciliation call receives all raw concepts; planning receives all canonical concepts. The command adapter's default request guard is 2 MB, while a chosen model may have a lower context limit. This benchmark constructs none of those prompts. A compact idea index and bounded source-restored reconciliation are research directions, not implemented scaling guarantees. Author calls can also repeat a source unit across lessons; measure summed lesson-source bytes. Cache keys include stage, payload and provider identity. A changed global board can invalidate downstream work, whereas extracted-concept counts say nothing about source completeness.

`Workspace` uses SQLite WAL on a local filesystem, a renewable lease and a fencing token. Separate tests cover recovery and stale-owner rejection. This benchmark times successful jobs and warm cache reads; it excludes PDF extraction, figures, model inference, speech, listening and teaching outcomes.

## Wider scheduling run

The checked-in [width experiment](../benchmarks/results/production-widths.json) uses 64 sleep-only readers, two serial global jobs and 16 author/review chains, totaling 98 handlers.

| Capacity | Cold wall (s) | Peak handlers | Warm handler calls |
| ---: | ---: | ---: | ---: |
| 1 | 6.001 | 1 | 0 |
| 4 | 1.690 | 4 | 0 |
| 16 | 0.777 | 16 | 0 |
| 32 | 0.626 | 30 | 0 |

These single-machine runs show configured capacity and observed overlap, not model speed. Warm elapsed times need not improve with width because threads and cache reads still cost time. Reproduce with `python benchmarks/run_systems.py --units 64 --lessons 16 --widths 1 4 16 32`.

The separate [production fixture](../examples/production-example.json) exercises source-aware reading, a deliberately false inference, review, repair and targeted revision. Revision reuses six of eight requests and reruns the changed writer and reviewer. This is a structural result rather than an output-quality measurement.
