# Measuring preservation against workload

A context limit states what an endpoint accepts. A workload policy states how much work Lamina sends to one call. Its useful operating range depends on the model, task, output allowance and source. A successful JSON response establishes neither completeness nor faithful interpretation.

`benchmarks/quality_titration.py` exercises the production reader, planner, writer, reviewer and repair paths with original fictional equipment specifications. It imports Markdown through the normal parser, uses production prompts and validators, and creates a fresh workspace for each observation. Canaries carry a negation, an exception, quantities, a sequence, two table associations and a conflicting historical source. They occur at the beginning, middle and end of the growing source; the report records their actual positions within reader requests after packing.

Use [`lamina calibrate`](calibration.md) for repeatable experiments and report-linked profiles. The lower-level benchmark below remains available for adversarial fixtures and corpus-load studies.

## Run a configured provider

Configure an adapter using [Adapters](adapters.md), including its tokenizer, context size, output allowance and explicit stage workload policies. Run this example experiment:

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

Every numerical value above is an experimental choice. The command makes provider calls and incurs that provider's charges. `--loads` counts distinct background paragraphs; the report records actual rendered input tokens separately. `--input-limits` replaces the selected stage's workload policy for each experiment while retaining its transport, context and output limits. Other stages retain their configured policies. Use `production_route` or `production_write` to vary those stages. Omit `--input-limits` to examine the configured policy across source loads. Use `--reading reusable` to examine brief-independent inventories. `--complete` includes writing, review and any triggered repair.

The output directory must be new. It contains each trial's original sources, validated plan, finished document when available, trial measurements and `report.json`. Failed trials remain in the report. A failed acceptance check returns exit status 1; it does not suppress results.

The report records provider and configuration identities, production protocol revision, corpus hash, task, source bytes, stage budgets, actual request measurements, adapter-reported token usage, response bytes, elapsed time and all individual canary results. Unknown usage remains unknown. An output allowance is a configured ceiling; actual output tokens require the adapter's usage report. Repeating the same input in a fresh workspace avoids engine-cache reuse, but does not establish statistical independence between model answers.

## What the oracle checks

A canary passes when one local model-authored statement includes every required phrase, contains no declared counterfact, and cites a locally supporting statement from the correct source. The evaluator separates sentences and Markdown lines, then separates references to different named canary subjects. This prevents one table lane from borrowing a neighboring lane's value. Phrase matching ignores whitespace and case and respects word boundaries. A quotation containing a missing qualifier cannot rescue an explanation that omitted it.

Scores are reported for extracted explanations, assigned explanations, initial drafts and finished bodies. Assignment scores establish whether the required content remains assigned. They do not judge whether the section structure is useful. Review observations record findings; improvement is assessed against the finished body. Each acceptance threshold is supplied by the caller and applied separately to every measured position and every replicate.

| Failure family | Observable check | Remaining limitation |
| --- | --- | --- |
| Deletion | A required canary is absent or loses a required phrase | Unlabelled background facts are outside the oracle |
| Substitution | Required quantities or conditions disappear; declared counterfacts appear | Valid paraphrases can fail lexical matching |
| Insertion | A declared invented claim appears | Unknown invented claims need further review |
| Mixed contexts | A declared lane/value confusion appears | General contextual merging requires semantic labels |
| Misattribution | Correct text lacks evidence from the specified source | Source authority requires a task-specific judgment |

This is a lexical oracle for known facts. The local-statement grammar can reject valid multi-sentence explanations, and wording can change meaning beyond the specified counterfacts. Human review of the saved artifacts remains necessary before using the results as evidence for an operating policy. A second model judge would also need validation against human labels.

The summary returns the **largest sampled passing load**, separately for each provider configuration and reading mode. It supplies no fitted knee, interpolation, confidence interval, unseen-corpus recall certificate or automatic promotion into an operating profile. Model request limits can split a large corpus into smaller calls; therefore corpus load alone must never become a per-call workload limit. Inspect actual request measurements and failure locations.

## Demonstrate the silent omission

```bash
PYTHONPATH=src python benchmarks/quality_titration.py \
  --scripted --loads 6,20 --reading task --replicates 1 --complete \
  --minimum-fraction 1 --maximum-counterfacts 0 \
  --output /tmp/lamina-silent-omission
```

The scripted provider cites every source unit, returns valid records, and omits a negation from its explanation and finished prose. Its reviewer reports no findings. The production engine can finish with `ready` while the canary check fails. Exit status 1 is expected. This tests the evaluator's ability to expose a known failure; it provides no measurement of a real model. Scripted reports identify themselves as `scripted-adversarial-contract` and cannot establish an observed real-provider workload policy.

## Output capacity and repeated reading

If a call must express $F$ separate facts and each fact requires at least $t$ output tokens, an output allowance $O$ imposes the conditional bound $R \leq \min(1, O/(tF))$. With a hypothesized density $\rho$ facts per thousand input tokens and source length $L$ in thousands, substitute $F=\rho L$. The assumptions about separate facts and minimum representation size matter: compression, shared references and compound statements change them. A model can stop with a valid but incomplete response before reaching its output ceiling. Truncation is one observable failure. Completeness needs a separate check.

Position-sensitive evaluation is motivated by [Liu et al., *Lost in the Middle* (2024)](https://aclanthology.org/2024.tacl-1.9/). That study does not supply a universal operating threshold for later models or this extraction task.

Capture–recapture needs identifiable objects across samples. Overlapping span IDs show shared source location; a single span can contain several distinct facts. They cannot establish fact identity. Chapman estimates depend on assumptions about capture probabilities, dependence and matching. Correlated omissions and heterogeneous detectability can bias inferred population size. A biased point estimate is not a certified upper bound on recall. Chao estimators address specified sampling models; a third model read does not remove those assumptions. See [Brittain and Böhning, *Estimators in capture–recapture studies with two sources* (2009)](https://www.personal.soton.ac.uk/dab1f10/Brittain_Boehning.pdf). Lamina therefore does not attach a recall certificate based on citation overlap.

Multiplying stage recalls is valid for the probability that the same fact survives every stage when each factor is conditioned on survival so far. Unconditional aggregate scores generally cannot be multiplied. Later writers can also recover a missing qualification from original sources, so end-to-end correctness must be measured directly.

## Limits

The bundled canaries cover a narrow invented domain and Markdown structure. They do not establish real PDF/OCR, clinical, assessment or audio quality. Growing unique background paragraphs exercises input load but does not span real source difficulty or fact density. Current measurements do not justify a universal density trigger, repeated-reading rate or output-occupancy threshold. A reusable inventory remains a fallible interpretation; cached results preserve its errors as well as its successes. A report reference records evidence provenance and scope, while the operator remains responsible for the policy chosen from that evidence.
