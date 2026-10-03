# Compare request grouping

`benchmarks/compare_execution.py` compares ordinary planned execution, grouped
planned execution and the direct path using the same sources and brief. Each
replicate starts with empty workspaces. The two planned variants share an
identical outline, so a different planning decision cannot explain their
request counts. Both totals include that outline's measured preparation cost.
The direct path prepares its own request. Run order rotates between replicates.

The report retains failed attempts, calls, reported token usage, request bytes,
preparation time, provider admission waits when available, time to the first
provisional section and total completion time. Full requests and outputs stay
beside the report for inspection. Keep those files private when using private
sources. The runner records the source, implementation and runner hashes.

## Local measurement

The [October 3 results](../benchmarks/results/matched-execution-2026-10-03.json)
cover ten repetitions of each variant on six original, fictional equipment
statements. The fixture copies source text and applies the real engine's
validation, caching and scheduling. It makes no network requests, adds no
artificial delay and supplies no invented token counts.

All 30 runs completed and retained all six declared statements and their source
references. The planned and grouped outputs matched exactly in every replicate.
Direct execution produced one section containing the same required statements.

| Variant | Read / plan calls | Write / review calls | Request bytes |
| --- | ---: | ---: | ---: |
| Planned | 6 / 1 | 6 / 6 | 65,850 |
| Grouped, up to six sections | 6 / 1 | 1 / 1 | 51,410 |
| Direct | 0 / 0 | 1 / 1 | 12,804 |

Grouping removed ten requests and reduced serialized request bytes by 21.9%
against planned execution. These byte counts describe Lamina request envelopes,
not provider token usage. Grouping took slightly more local execution time in
this fixture, because it adds packing and validation work while avoiding no
network latency. The direct path did the least work on this small collection.
These results do not establish a live speedup.

Median local completion times were 43.80 ms planned, 47.52 ms grouped and
10.07 ms direct. Median time to the first provisional section was 29.61 ms,
46.94 ms and 9.88 ms respectively. These values include parsing and planning;
the raw report separates execution time. This tiny fixture makes grouping's
local overhead visible without predicting network or model latency.

Reproduce the local comparison:

```sh
python benchmarks/compare_execution.py --replicates 10 --output /tmp/lamina-comparison
```

## Live comparison

The same runner supports the existing native Gemini adapter. Set
`GEMINI_API_KEY` in the process environment, then choose the model explicitly:

```sh
python benchmarks/compare_execution.py --provider gemini \
  --model gemini-2.5-flash --replicates 3 --workers 4 --concurrency 4 \
  --output /private/measurements/lamina-comparison
```

`--max-calls` defaults to 100 generation calls across all three variants in each
replicate. It is a call limit, not a spending limit; token counting makes
additional network requests. Live runs consume the configured account's API
quota. Use a new output directory for every experiment.

To measure representative material, add `--corpus corpus.json` using the
[calibration manifest format](calibration.md#use-your-own-corpus). Declare the
facts and qualifications to check before running. Inspect the complete outputs
for errors and awkward wording, including valid paraphrases rejected by the
phrase checks. A run requiring review remains visible in the summary.

## Limits

Live preflight on October 3 found no `GEMINI_API_KEY`, so no live model requests
were made. Fixture success establishes execution behavior only. It does not
measure model understanding, natural writing, cross-document nomination recall,
audio quality or 10,000-page throughput. Six phrase checks are not a complete
semantic evaluation. Ten local repetitions do not establish project tail
percentiles. No workload profile is promoted by this comparison.
