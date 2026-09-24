# Measure a workload on your model

`lamina calibrate` runs the production pipeline repeatedly, checks specific facts in both the extracted ideas and finished output, and saves the settings that pass. Each trial starts with an empty cache. Its report includes the request protocol, model configuration, source hash, workload settings, timings and reported token usage. Before making model calls, it checks that the declared facts can be matched in the imported sources.

## Start a project

The adapter configuration accepts `"workload": "starter"`. This supplies distinct initial policies for reading, planning, writing and review. They are configured defaults; a production receipt shows their measurement status. Reading starts at 96 source spans so a complete PDF page can fit; the clinical test source included a page with 86 spans. Global routing starts at 64 idea cards, grouping and reassignment at 24, and writing/review at six ideas. The global routing allowance keeps an ordinary idea board together before falling back to a hierarchy.

An example for Gemini is in [`examples/calibration/models.gemini.json`](../examples/calibration/models.gemini.json). From the repository root, with the HTTP dependencies installed:

```sh
export LAMINA_API_KEY="$GEMINI_API_KEY"
lamina ingest your-source.md --workspace .lamina
lamina produce --adapter @examples/calibration/models.gemini.json \
  --workspace .lamina --brief 'Create a reference guide for a new team member.' \
  --output output
```

Keep credentials in the environment. The model configuration contains endpoint and workload settings. Set its concurrency and model to suit your account.

## Run the controls

This command tests the bundled original equipment corpus at three reader workloads:

```sh
lamina calibrate --models examples/calibration/models.gemini.json \
  --limits 12,24,48 --replicates 3 --output measurements/reader-01
```

For a writer experiment, use `--stage production_write --limits 1,3,6`. Each run still completes reading, planning, writing and review; only the selected stage's limit changes. `--dimension max_input_tokens` tests full prompt-token limits when the provider has a matching tokenizer. The HTTP example above reports actual token usage but does not install a Gemini tokenizer.

The automatic promotion policy requires at least two replicates and every declared check to survive at extraction, assignment and finished output, at every tested position and in every replicate, with no known counterfact. Promotion also requires production to finish with no unresolved review findings. `profiles.json` contains the largest tested passing setting for the selected stage. It contains `{}` when no tested setting passed; the CLI then exits with status 1. `models.json` applies any passing profile to a copy of the original configuration and links the new report; use that file for subsequent runs.

The private report stores the brief, canaries, source hashes and effective options under an `evaluation_sha256` identity. All replicates must use the same identity for promotion.

Each model call is saved immediately in a private `calls.jsonl` journal. Trial summaries are saved after each trial. The journal contains source text and model responses; keep it with the source material. A production receipt's `quality_control` field identifies its QC report by hash, checks its provider, protocol and workload, and records passed, failed, mismatched or unavailable results. It also records the report's age; reports older than 30 days are marked stale. The report selected in `models.json` is the control record for that project. A newer QC report can supersede the profile's original promotion report; the receipt displays both hashes. Only the measured stage can receive a passing QC status. Other stages remain unmeasured even when they ran as part of the trial.

## Use your own corpus

Supply `--corpus corpus.json` to measure the material you actually use. Paths are relative to the manifest. Keep private sources and results outside the repository.

```json
{
  "sources": ["operating-manual.md"],
  "brief": "Write a reference preserving the manual's operating conditions and exceptions.",
  "canaries": [{
    "id": "reset-interlock",
    "source": "operating-manual.md",
    "subject": "Rotor Umber",
    "required": ["Rotor Umber", "does not reset", "red lamp"],
    "forbidden": ["Rotor Umber resets while its red lamp"],
    "position": "middle",
    "kind": "negation"
  }]
}
```

Choose conditions, exceptions, numbers and easily confused associations. Inspect the source and proposed checks before treating them as an evaluation set. Run separate corpora for reference writing, podcast scripts and assessments; their useful outputs differ.

## Read the results

Compare quality first, then cost and time among settings that pass. Idea counts depend on how the model groups facts; use the declared checks to judge information loss. Larger requests can save calls while losing distinctions. Small requests can repeat so much framing that overhead dominates. Per-call records show input and output usage, source-token counts when the provider supplies them, output occupancy when its allowance is known, and retained checks by source position.

The oracle matches declared phrases and their source evidence. Valid paraphrases can fail it, and undeclared mistakes can escape it. Inspect failures before changing a profile. A passing profile describes this model configuration on this corpus and protocol; use a held-out corpus before extending it to a different task.

## Calibrate with Gemini's native tokenizer

The optional Python provider in [`examples/adapter/gemini_provider.py`](../examples/adapter/gemini_provider.py) calls Gemini's official `countTokens` and `generateContent` REST methods directly. It does not approximate Gemini tokens with `tiktoken`. The same rendered system instruction, shared data, local data and generation settings are sent for counting and generation. When a request supplies a response schema, both operations receive that schema as well.

Keep the API key in `GEMINI_API_KEY`. This example tests 4,000- and 8,000-token reader workloads with two replicates, an 8,192-token output allowance, a 1,024-token thinking budget and at most four simultaneous HTTP requests:

```python
from pathlib import Path

from examples.adapter.gemini_provider import GeminiProvider
from lamina.calibration import calibrate, read_corpus

provider = GeminiProvider(
    model="models/gemini-2.5-flash",
    context_tokens=1_048_576,
    output_tokens=8_192,
    thinking_tokens=1_024,
    max_concurrency=4,
)

result = calibrate(
    provider,
    Path("measurements/gemini-reader-tokens-01"),
    stage="production_read",
    dimension="max_input_tokens",
    limits=(4_000, 8_000),
    replicates=2,
    corpus=read_corpus(Path("/private/path/corpus.json")),
)
print(result)
print(provider.transport_metrics())
```

Use a new output directory for every run because calibration creates it exclusively. `transport_metrics()` reports actual `countTokens` request count and wall time separately from `generateContent` request count and wall time. Packing probes can issue several count requests even when memoization avoids recounting an identical rendered request. These transport measurements diagnose calibration overhead; model usage remains in each call receipt.

The wire fields follow Google's official [`countTokens`](https://ai.google.dev/api/tokens), [`generateContent`](https://ai.google.dev/api/generate-content), [thinking-budget](https://ai.google.dev/gemini-api/docs/generate-content/thinking), and [Gemini 2.5 Flash](https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flash) documentation. Gemini 2.5 Flash's `maxOutputTokens` allowance includes thinking tokens, so the provider rejects a thinking budget that would consume the complete output allowance.
