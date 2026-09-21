# Systems benchmark: cache and dependency shape

`benchmarks/run_systems.py` runs a deliberately synthetic workload through the **real** `Workspace.run_cached` SQLite claim, lease, result, and cache path. It makes no model call, network request, document conversion, or audio file. Each handler sleeps for its declared duration and returns a tiny JSON object. The benchmark measures scheduling and cache overhead for this graph:

```text
24 independent extract jobs
          ↓ all complete
1 reconcile → 1 plan
          ↓ both complete
6 independent (author → review) chains
```

Run it from a clean clone with Python 3.11 or newer; installation and optional dependencies are unnecessary:

```sh
python3 benchmarks/run_systems.py --output benchmarks/results/my-machine.json
```

`--units` and `--lessons` adjust the job counts. The default runs worker widths 1, 4, and 8. Each width gets a fresh temporary SQLite workspace, then executes the same graph twice in that workspace: cold and warm. The script asserts 38 cold handler calls and zero warm calls for the default workload. The output records wall time, each phase's wall time, observed maximum simultaneous handlers, actual call counts, workspace job states, Python/SQLite/platform details, declared sleeps, and idealized bounds. It contains no source documents or credentials. Do not compare results from unlike machines or workloads as if they were one experiment.

## One observed local run

The checked-in [result](../benchmarks/results/local-systems-2026-09-21.json) was measured on Darwin arm64, 12 reported logical CPUs, Python 3.14.7, SQLite 3.53.4. One run per width was recorded on 2026-09-21; there are no confidence intervals or provider-performance claims.

| Worker width | Cold wall time | Sleep-only phase ideal | Peak active handlers | Cold handler calls | Warm wall time | Warm handler calls |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 2.412 s | 2.160 s | 1 | 38 | 0.022 s | 0 |
| 4 | 0.865 s | 0.780 s | 4 | 38 | 0.022 s | 0 |
| 8 | 0.595 s | 0.510 s | 8 | 38 | 0.018 s | 0 |

The cold width-8 run spent 0.191 s in extraction, 0.127 s in reconciliation, 0.123 s in planning, and 0.154 s in the parallel author/review phase. Reconciliation and planning stay serial as workers increase. The gap between observed time and the sleep-only ideal includes thread scheduling, SQLite transactions, and serialization. A warm cache avoids the handlers, but still reads the job rows; it does not make a new model answer or validate teaching quality.

## What the bounds mean

Default synthetic service work is

`W = 24(0.05) + 0.12 + 0.12 + 6(0.08 + 0.04) = 2.16 seconds`.

The longest dependent path through one unit and one lesson is

`D = 0.05 + 0.12 + 0.12 + 0.08 + 0.04 = 0.41 seconds`.

With `p` workers, `max(W/p, D)` is a general work/span lower bound for the synthetic sleeps. It is 2.16, 0.54, and 0.41 seconds for widths 1, 4, and 8. It does not account for the extraction and lesson barriers. Because all same-stage sleeps have equal duration here, the more informative sleep-only schedule is

`ceil(24/p)×0.05 + 0.12 + 0.12 + ceil(6/p)×(0.08+0.04)`.

That yields 2.16, 0.78, and 0.51 seconds for the tested widths. Even unlimited workers cannot remove the two global calls; this artificial graph tends toward the 0.41-second longest path. Real model calls have variable lengths, rate limits, response sizes, retries, and quality costs, so these figures are **not** a forecast of document-to-course generation speed. Wider pools can increase tail waiting or rate-limit contention.

## Context cost this benchmark does not measure

Lamina's actual extractor sends one core source unit plus up to 450 characters from each adjacent unit in the same source (`src/lamina/pipeline.py`). If the core text totals `B` characters across `U` units, source-text exposure from extraction is bounded above by `B + 900U` characters, before headings, identifiers, instructions, and JSON serialization. Source boundaries reduce the actual halo amount. The correct logged quantity is bytes/tokens sent per stage, not simply unit count. Smaller cores repeat more halo and prompt overhead per source character; the effect of window size on extraction accuracy needs measurement for the chosen model and corpus.

The real reconciliation call sees **all extracted raw concepts**; the plan sees **all canonical concepts**. These are one-call context ceilings even if extraction is perfectly parallel. The command adapter's default 2 MB request guard makes the failure explicit, but a chosen model's context limit may be lower. The benchmark never constructs those prompts and does not test their quality. For larger corpora, a compact global idea index plus bounded, source-restored local reconciliation is a research direction, not an implemented Lamina scaling guarantee.

Likewise, the author receives its assigned source units. If one unit supports concepts placed in several lessons, its text may be sent several times. Measure `Σ lesson source bytes` and the largest individual request. Cache identities include stage, complete payload, and provider/adapter version; unchanged requests are reusable, while changes to an assigned source or global concept board can invalidate downstream work. Counts of assigned or deferred concepts establish structural accounting of **extracted** concepts only, not complete understanding of the source or learner proficiency.

The benchmark does not exercise a distributed queue. `Workspace` uses SQLite WAL on one local filesystem, a renewable lease, and a fencing token. Its tests cover recovery and stale-owner rejection; this sleep benchmark only times normal completed jobs and warm cache reads. It also excludes PDF extraction, image understanding, model inference, voice rendering, listening behavior, and actual teaching outcomes.


## Wider scheduling run (v0.5)

The checked-in [width experiment](../benchmarks/results/production-widths.json) uses 64 reader jobs, two serial global jobs and 16 author–review chains (98 handlers). Each handler sleeps and returns a small object; it performs no model inference.

| Capacity | Cold wall time (s) | Observed peak handlers | Warm handler calls |
| --- | ---: | ---: | ---: |
| 1 | 6.001 | 1 | 0 |
| 4 | 1.690 | 4 | 0 |
| 16 | 0.777 | 16 | 0 |
| 32 | 0.626 | 30 | 0 |

These measurements show that capacity is configurable beyond four and that actual overlap can be smaller than the configured ceiling. They are single local runs, not statistical estimates or predictions of model speed. Warm elapsed time need not fall as worker count rises: threads, SQLite access and scheduling still cost time even when handlers are cached.

Reproduce with `python benchmarks/run_systems.py --units 64 --lessons 16 --widths 1 4 16 32`. The separate [production fixture](../examples/production-example.json) exercises the full source-aware engine, including a deliberate false inference, review, repair and targeted revision. The revision reuses six of eight requests and executes the changed writer and its reviewer; this is a structural result, not a quality benchmark.
