# Measure workload and preservation on your model

A context limit states what an endpoint accepts. A workload policy states how much work Lamina sends to one call. Its useful operating range depends on the model, task, output allowance and source, and a successful JSON response establishes neither completeness nor faithful interpretation.

`lamina calibrate` runs the production pipeline repeatedly, checks specific facts in the extracted ideas, the assignment and the finished output, and saves the settings that pass. Each trial starts with an empty cache. Its report includes the request protocol, model configuration, source hash, workload settings, timings and reported token usage. Before making model calls, it checks that the declared facts can be matched in the imported sources.

## Start a project

The adapter configuration accepts `"workload": "starter"`. This supplies distinct initial policies for reading, planning, writing and review. They are configured defaults; a production receipt shows their measurement status. Reading starts at 96 source spans so a complete PDF page can fit; the clinical test source included a page with 86 spans. Global routing starts at 64 idea cards, grouping and reassignment at 24, and writing/review at six ideas. The global routing allowance keeps an ordinary idea board together before falling back to a hierarchy.

An example for Gemini is in [`examples/calibration/models.gemini.json`](../examples/calibration/models.gemini.json). From the repository root, with the HTTP dependencies installed:

```sh
export LAMINA_API_KEY="$GEMINI_API_KEY"
export LAMINA_API_BASE="<the chat-completions base URL your provider documents>"
lamina ingest your-source.md --workspace .lamina
lamina produce --adapter @examples/calibration/models.gemini.json \
  --workspace .lamina --brief 'Create a reference guide for a new team member.' \
  --output output
```

Keep credentials and the endpoint in the environment: `LAMINA_API_BASE` is the base URL under which your provider serves `/chat/completions` (Gemini documents a compatibility endpoint under its `v1beta` API). The model configuration contains the model name, concurrency and workload settings; set them to suit your account.

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

A passing profile describes this model configuration on this corpus and protocol; use a held-out corpus before extending it to a different task.

## What the oracle checks

A canary passes when one local model-authored statement includes every required phrase, contains no declared counterfact, and cites a locally supporting statement from the correct source. The evaluator separates sentences and Markdown lines, joins PDF line wraps inside prose, then separates references to different named canary subjects so one table lane cannot borrow a neighboring lane's value. Phrase matching ignores whitespace and case and respects word boundaries. A quotation containing a missing qualifier cannot rescue an explanation that omitted it.

Scores are reported for extracted explanations, assigned explanations, initial drafts and finished bodies. Assignment scores establish whether the required content remains assigned; they do not judge whether the section structure is useful. Review observations record findings, and improvement is assessed against the finished body. Each acceptance threshold is supplied by the caller and applied separately to every measured position and every replicate.

| Failure family | Observable check | Remaining limitation |
| --- | --- | --- |
| Deletion | A required canary is absent or loses a required phrase | Unlabelled background facts are outside the oracle |
| Substitution | Required quantities or conditions disappear; declared counterfacts appear | Valid paraphrases can fail lexical matching |
| Insertion | A declared invented claim appears | Unknown invented claims need further review |
| Mixed contexts | A declared lane/value confusion appears | General contextual merging requires semantic labels |
| Misattribution | Correct text lacks evidence from the specified source | Source authority requires a task-specific judgment |

This is a lexical oracle for known facts. The local-statement rule can reject a valid multi-sentence explanation, and wording can change meaning beyond the specified counterfacts. Inspect failures before changing a profile, and review the saved artifacts before using results as evidence for an operating policy. A second model judge would also need validation against human labels.

## Run the titration benchmark

`benchmarks/quality_titration.py` is the lower-level harness behind calibration, kept for adversarial fixtures and corpus-load studies. It exercises the production reader, planner, writer, reviewer and repair paths with original fictional equipment specifications, imports Markdown through the normal parser, uses production prompts and validators, and creates a fresh workspace for each observation. Canaries carry a negation, an exception, quantities, a sequence, two table associations and a conflicting historical source. They occur at the beginning, middle and end of the growing source, and the report records their actual positions within reader requests after packing.

Configure an adapter using [Adapters](adapters.md), including its tokenizer, context size, output allowance and explicit stage workload policies. Then run an experiment such as:

```bash
PYTHONPATH=src python benchmarks/quality_titration.py \
  --models models.json \
  --loads 20,80,200 \
  --input-limits 4000,8000,16000 \
  --stage production_read \
  --reading task \
  --replicates 3 \
  --complete \
  --minimum-fraction 1 \
  --maximum-counterfacts 0 \
  --output /tmp/lamina-quality-run
```

Every numerical value above is an experimental choice. The command makes provider calls and incurs that provider's charges. `--loads` counts distinct background paragraphs; the report records actual rendered input tokens separately. `--input-limits` replaces the selected stage's workload policy for each experiment while keeping its transport, context and output limits; other stages keep their configured policies. Use `production_route` or `production_write` to vary those stages. Omit `--input-limits` to examine the configured policy across source loads. Use `--reading reusable` to examine brief-independent inventories. `--complete` includes writing, review and any triggered repair.

The output directory must be new. It contains each trial's original sources, validated plan, finished document when available, trial measurements and `report.json`. Failed trials remain in the report. A failed acceptance check returns exit status 1 without suppressing results. The report records provider and configuration identities, production protocol revision, corpus hash, task, source bytes, stage budgets, actual request measurements, adapter-reported token usage, response bytes, elapsed time and every canary result. Unknown usage remains unknown. An output allowance is a configured ceiling; actual output tokens require the adapter's usage report. Repeating the same input in a fresh workspace avoids engine-cache reuse but does not make model answers statistically independent.

The summary returns the **largest sampled passing load**, separately for each provider configuration and reading mode. Promotion is bounded by the load the stage's requests actually carried: if ceilings of 24 and 96 both pass but no read ever held more than six items, the promoted profile says six, and a trial whose calls recorded no measurement promotes nothing. A passing ceiling that never bound is not a measurement of it. It supplies no fitted knee, interpolation, confidence interval, recall certificate for unseen material or automatic promotion into an operating profile. Request limits can split a large corpus into smaller calls, so corpus load alone must never become a per-call workload limit. Inspect actual request measurements and failure locations.

## Demonstrate the silent omission

```bash
PYTHONPATH=src python benchmarks/quality_titration.py \
  --scripted --loads 6,20 --reading task --replicates 1 --complete \
  --minimum-fraction 1 --maximum-counterfacts 0 \
  --output /tmp/lamina-silent-omission
```

The scripted provider cites every source unit, returns valid records, and omits a negation from its explanation and finished prose. Its reviewer reports no findings. The production engine finishes with `ready` while the canary check fails, and exit status 1 is expected. The [recorded result](../benchmarks/results/quality-silent-omission.json), produced at protocol `lamina-production-6`, shows five of six canaries surviving at both background loads. This tests the evaluator's ability to expose a known failure and measures no real model. Scripted reports identify themselves as `scripted-adversarial-contract` and cannot establish an observed workload policy for a real provider.

## Output capacity and repeated reading

If a call must express $F$ separate facts and each fact requires at least $t$ output tokens, an output allowance $O$ imposes the conditional bound $R \leq \min(1, O/(tF))$. With a hypothesized density $\rho$ facts per thousand input tokens and source length $L$ in thousands, substitute $F=\rho L$. The bound is derived from those two assumptions, separate facts and a minimum representation size; compression, shared references and compound statements change them. A model can also stop with a valid but incomplete response before reaching its output ceiling. Truncation is one observable failure; completeness needs a separate check.

Position-sensitive evaluation is motivated by [Liu et al., *Lost in the Middle* (2024)](https://aclanthology.org/2024.tacl-1.9/). That study does not supply a universal operating threshold for later models or this extraction task.

Capture–recapture needs identifiable objects across samples. Overlapping span IDs show shared source location, but a single span can contain several distinct facts, so they cannot establish fact identity. Chapman estimates depend on assumptions about capture probabilities, dependence and matching; correlated omissions and heterogeneous detectability can bias the inferred population size, and a biased point estimate is not a certified upper bound on recall. Chao estimators address specified sampling models, and a third model read does not remove those assumptions. See [Brittain and Böhning, *Estimators in capture–recapture studies with two sources* (2009)](https://www.personal.soton.ac.uk/dab1f10/Brittain_Boehning.pdf). Lamina therefore attaches no recall certificate based on citation overlap.

Multiplying stage recalls is valid for the probability that the same fact survives every stage when each factor is conditioned on survival so far. Unconditional aggregate scores generally cannot be multiplied. Later writers can also recover a missing qualification from original sources, so end-to-end correctness must be measured directly.

## Calibrate with Gemini's native tokenizer

The optional Python provider in [`examples/adapter/gemini_provider.py`](../examples/adapter/gemini_provider.py) calls Gemini's official `countTokens` and `generateContent` REST methods directly. It does not approximate Gemini tokens with `tiktoken`. The same rendered system instruction, shared data, local data and generation settings are sent for counting and generation. When a request supplies a response schema, both operations receive that schema as well.

Keep the API key in `GEMINI_API_KEY`. This example tests 4,000- and 8,000-token reader workloads with two replicates, an 8,192-token output allowance, a 1,024-token thinking budget and at most four simultaneous HTTP requests (the provider's default is 16):

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

## Limits

The bundled canaries cover a narrow invented domain and Markdown structure. They do not establish real PDF/OCR, clinical, assessment or audio quality. Growing unique background paragraphs exercises input load but does not span real source difficulty or fact density. Current measurements justify no universal density trigger, repeated-reading rate or output-occupancy threshold. A reusable inventory remains a fallible interpretation, and cached results preserve its errors as well as its successes. The oracle matches declared phrases and their source evidence: valid paraphrases can fail it, and undeclared mistakes can escape it. A report reference records evidence provenance and scope, while the operator remains responsible for the policy chosen from that evidence.
