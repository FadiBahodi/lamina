# Toward retained methods

A source-grounded lesson is a useful artifact. A reusable **method** would go further: it would tell a later run when a way of framing a problem applies, how to adapt it, which checks matter, and what observation should change the method afterward. This is a proposed extension to Lamina, not a capability hidden inside its current procedure editor.

## What exists in v0.2

A procedure is bounded configuration: an audience, authoring instructions, selected output types, and a worker limit. Lamina validates that data, includes a procedure revision in semantic-stage requests and cache keys, and produces artifacts through fixed extraction, reconciliation, planning, authoring, review, and format-specific stages. A procedure can be edited, exported, and applied to another source collection. It cannot add executable stages or learn from a completed run.

The exported bundle stores source units, raw and canonical concepts, a lesson plan, authored lessons, and stated review responses. It does not contain a longitudinal learner model, an experience store, a method selector, or an update loop. Local practice ratings are not calibrated mastery. The [pipeline inspector](../src/lamina/studio/inspector.js) reads one exported example; it does not replay a live run or infer why the adapter made a choice.

## A method as an executable hypothesis

A future method record could have five linked parts:

| Part | Question it answers | Example of a checkable representation |
| --- | --- | --- |
| Applicability | In what source, task, learner, and constraint conditions might this help? | Typed predicates with scope and exclusions |
| Problem representation | Which distinctions must stay visible? | Concepts, answer atoms, conflicts, prerequisite and contrast edges |
| Procedure | What transformations and tools should be attempted? | Versioned stage graph with input/output contracts |
| Expected observations | What would count as success or failure? | Grounding audits, answer conservation, learner responses, cost and latency |
| Revision rule | Which evidence changes the method, and how? | Proposed patch, test set, human acceptance, rollback path |

The word “method” should not turn a preferred writing style into a universal rule. “Preserve every source answer token during consolidation” is a useful invariant when the task is to keep a source answer inventory; it is not a sufficient rule for deciding which answers are true or worth teaching first. “Use staged reveals” is useful when decisions genuinely change with new information; it can distract when the target is a fixed factual structure.

## Proposed loop

```text
source + task + constraints
          ↓
represent the problem and retrieve candidate methods
          ↓
select or adapt a method with stated applicability and competing options
          ↓
execute versioned steps with source receipts and bounded retries
          ↓
observe artifact quality, learner use, failures, cost, and uncertainty
          ↓
propose a scoped revision → test on held-out cases → accept or reject
```

Selection should expose *why this method here*: which applicability conditions matched, which did not, and what rival method was considered. A dense reference manual might need exhaustive claim inventory before routing. A short incident guide might support a compact decision sequence. The same surface term can denote different tasks, so text similarity alone is not an adequate selector.

Adaptation should preserve protected invariants: stable source identity, assessment holdout, exact citation ownership, conservation of extracted records, and explicit deferrals. It could change lesson granularity, output format, review rubric, or question timing. If adaptation changes a schema or semantic contract, it needs a new version and fresh cache identity. If it merely changes a prompt, the recorded procedure revision still needs to change; otherwise a cached response can masquerade as the new method's result.

Execution would produce an **experience record** that separates attempted action from observed effect: input scope, method version, stage outputs, accepted and rejected artifacts, reviewer objections, learner interaction when consented and measured, and external delivery result. A passing validator proves only its specified invariant. It cannot certify that the method taught well. A failed stage should reopen the smallest dependent step, while preserving the source and decision trail that led to it.

Revision must be evidence-led. A single model critique is a candidate change, not a learned law. Test revisions against a held-out source/task set; compare extraction, consolidation, grounding, response quality, and cost with the prior version. Keep counterexamples and uncertainty. Human acceptance is especially important where the method changes answer scope or a consequential decision. Retain the old version so a regression can be traced and reversed.

## Product and research boundary

This direction would make Lamina a system that accumulates *tested ways of working*, rather than a library of fixed prompt recipes. It also creates new risks: overfitting one corpus, laundering model preference into “experience,” storing sensitive learner traces, and treating a proxy metric as the goal. The first experiment should be narrow: compare two explicit methods on a small, labelled corpus, measure where each succeeds or fails, and verify that a proposed revision improves held-out work before promoting it.

The current release makes a smaller, concrete claim: procedures are portable configuration, source-to-output stages are inspectable, and validation enforces particular accounting and evidence boundaries. The [design note](design.md) describes answer-level conservation and hierarchical scaling proposals; the [evaluation plan](evaluation.md) names the evidence needed before stronger quality claims.
