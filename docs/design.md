# Design: from source spans to a learning route

Lamina's design problem is broader than turning a document into a summary. A useful learning system must decide **what the source says, which ideas are distinct, what deserves first-pass attention, and which form makes each idea retrievable**. Those decisions need different evidence and different checks. The v0.1 release has a working path through them; this document identifies where its guarantees stop and compares plausible next architectures.

The intended data flow is:

```text
source spans → atomic claims and answers → canonical concept graph
             → curriculum route → lessons, practice, cases, scripts, print
```

This is a design model, not a description of five fully implemented data structures. Today, Lamina stores ordered source **units** with locators, extracted **raw concepts** with exact quotes, a partition into **canonical concepts**, and an ordered **lesson plan**. Atomic answer tokens, typed concept edges, and hierarchical global planning are proposed extensions.

## What v0.1 guarantees

| Boundary | Implemented mechanism | Guarantee and limit |
| --- | --- | --- |
| File → units | Content digest, source role, stable unit IDs, ordered text chunks and locators | Accepted text can be traced to its input. PDF text extraction may miss figures, scans, or layout meaning. |
| Unit → raw concepts | Bounded unit request with neighboring context; exact quote and core-unit checks | A concept must cite a real teaching unit. No check establishes that all important facts were extracted. |
| Raw → canonical | One global reconciliation request; each raw concept assigned to exactly one canonical concept; member quotes conserved | Extracted records and their quotes cannot silently disappear. Their distinct answers or qualifiers still can. |
| Canonical → route | One global plan; every canonical concept assigned to a lesson or explicitly deferred | The plan accounts for its input set. Order and importance remain adapter judgments. |
| Route → output | Lesson authoring, evidence checks, review gate, validated bundle, static reader and print exports | Source links and required practice modes can be inspected. Citation presence does not prove a sentence is entailed or teachable. |

The assessment role is withheld from extraction, authoring requests, and public exports. Cache identity, durable jobs, leases, and bounded retries make repeated local builds recoverable. Neither mechanism proves that an evaluation set is uncontaminated or that generated material improves learning. The implementation details and field contracts are in [Architecture](architecture.md) and [Adapters](adapters.md).

## The conservation ladder

Coverage has several denominators. Conflating them makes a complete-looking artifact deceptively persuasive.

Let `U` be accepted source units and `Wᵢ` the units owned by extraction request `i`. **Structural scan coverage** is `|⋃ Wᵢ| / |U|`. A value of 1 says every accepted unit was offered to the extractor. It says nothing about material lost during parsing or missed within a unit. Neighboring context can clarify a boundary, but ownership should stay with the focal unit.

Let `R` be extracted raw concepts and `K` canonical concepts. v0.1 enforces a partition:

```text
For every r in R:  Σ[k in K] 1{r is a member of k} = 1
```

It also requires each canonical concept's evidence to be exactly the allowed quotes inherited from its members. This protects records and source pointers. It does **not** protect all answer alternatives inside a quote. If one paragraph lists four causes and the canonical explanation names three, the quote may still be conserved.

A stronger proposed boundary would assign a stable token to each extracted **atomic source answer or claim**, retaining its wording, scope, locator, and owner. For input tokens `T` and canonical answer items `A`, require:

```text
For every t in T:  Σ[a in A] 1{t is cited by a} = 1
For every citation t on a: owner(t) is a member of concept(a)
```

That would catch silent deletion, duplication, and cross-cluster attribution. It would **not** prove semantic equivalence: a mistaken paraphrase can carry a valid token. Nor does a token for a compound sentence guarantee preservation of every proposition inside it. Atomic segmentation, qualifier retention, contradiction review, and independent semantic audit remain necessary. A source quote is a receipt, not a proof of entailment.

These distinctions yield a practical order of claims: parser coverage, unit scan coverage, extraction recall, answer conservation, semantic correctness, lesson grounding, question quality, and learner effect. Success at one layer cannot be reported as success at the next.

## Three consolidation architectures

| Architecture | Strength | Failure mode | Appropriate use |
| --- | --- | --- | --- |
| Exact-key grouping | Cheap, deterministic, easy to audit | Synonyms remain duplicated; identical labels with different scope can be collapsed incorrectly | Baseline for obvious duplicates only |
| Global semantic reconciliation (v0.1) | Can merge varied wording while preserving raw IDs and quotes | Whole-corpus request grows; a concept-level invariant misses answer-level loss and scope collapse | Small corpora with human review of merges |
| Hierarchical, token-conserving reconciliation (proposed) | Bounded local decisions, answer-level accounting, global exception review | More schema and orchestration; partition boundaries can hide cross-topic duplicates | Larger, heterogeneous corpora after labelled merge tests |

The proposed hierarchy starts with deterministic source IDs and atomic claims, partitions candidates by **retrieval task and context** rather than keyword alone, clusters locally, then sends only plausible cross-partition bridge candidates to a reconciliation pass. A compact global board holds titles, scopes, answer-token counts, evidence quality, and unresolved conflicts. Validation checks each boundary; ambiguous merges stay separate or enter a review queue. This bounds most requests without pretending every topic is independent.

Several cases make conservative splits valuable: the same term can refer to a presenting problem, cause, complication, or treatment failure; a population-specific variant may change the answer; two sources may conflict; a broad concept may contain narrower concepts rather than being their synonym. A useful canonical structure may therefore be a **typed graph** (`same target`, `variant of`, `prerequisite`, `contrasts with`, `conflicts with`) instead of one flat set of merged records. That graph is proposed. v0.1 has canonical memberships and lesson prerequisites, not a general typed graph.

## Retrieval relevance is not curricular priority

v0.1 search fuses body-text BM25, heading matches, and optional supplied-vector ranks. It answers “Which stored unit is relevant to this query?” Its reciprocal-rank score is not an estimate of importance, assessment frequency, or teaching value.

A curriculum ranker answers a different question: “Which concepts should a learner reconstruct first, given limited time and dependencies?” Potential evidence includes breadth of reuse, source support, consequences of misunderstanding, assessment relevance where independently documented, prerequisite centrality, and learner time cost. These features can conflict. A rare distinction can be consequential; a common term can be trivial. Extraction confidence is a separate axis from priority.

There are three plausible routing policies:

1. **Flat complete inventory:** maximal discoverability, minimal editorial risk, high reading burden.
2. **Small first-pass spine plus deepen and lookup layers:** digestible route while preserving the archive; requires transparent, revisable inclusion reasons.
3. **Adaptive learner route:** could use performance and prerequisites, but needs outcome data, calibration, privacy design, and a validated update rule. v0.1 does not implement this.

For now, a priority tier should be labelled editorial judgment with a rationale, not a probability. A weighted formula is warranted only after independent relevance labels, agreement checks, and held-out ranking evaluation. Lexical similarity to prior questions can retrieve candidate evidence but is not itself a calibrated likelihood of future assessment.

## Format-specific outputs from one governed representation

The canonical layer should give every format the same scope and source trail; each format then has a distinct job. A lesson explains a causal model. Recall prompts require reconstruction. Contrast prompts expose confusable alternatives. Application prompts test a changed context. A case reveals information in stages. A listening script needs spoken pacing and pauses. Print needs page structure and a separate answer key. v0.1 implements these forms through a shared validated bundle; it does not claim they are equally effective for every concept, synthesize audited audio, or tailor a spaced-repetition schedule.

Question generation has an additional isolation boundary: held-out assessments should remain outside prompts and outputs. A role flag cannot detect duplicate or paraphrased leakage from teaching files; any performance study must audit contamination independently.

Retrieval practice has experimental support for delayed retention, and some studies find transfer to new questions or contexts; carefully arranged interleaving can aid category discrimination. These findings motivate recall, application, and contrast modes, but do not validate Lamina's generated items or its learner outcomes. See the original studies by [Roediger and Karpicke (2006)](https://www.psychologicalscience.org/journals/psychological-science/j.1467-9280.2006.01693.x/), [Butler (2010)](https://pubmed.ncbi.nlm.nih.gov/20804289/), and [Birnbaum and colleagues (2013)](https://pubmed.ncbi.nlm.nih.gov/23138567/). The interleaving result is task-dependent; it does not justify shuffling every lesson.

## What would justify stronger claims

The next evidence is a stratified, manually annotated source set: extraction precision and recall with parser omissions counted separately; pairwise merge/split labels and qualifier-preservation review; exact answer-token conservation; and independent judgments of first-pass route usefulness. A separate delayed learner comparison would be needed to claim improved retention or transfer. Measure these on held-out sources and questions, report disagreement, and publish denominator definitions. Until then, the release can claim inspectable accounting and repeatable artifact production, not completeness, calibrated yield, or learning efficacy.
