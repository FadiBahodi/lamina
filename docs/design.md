# From source spans to a learning route

A learning system must determine what a source says, which ideas are distinct, what deserves first-pass attention and how each idea should be taught. This note describes the v0.1 design and compares extensions.

```text
source spans → atomic claims and answers → canonical concept graph
             → curriculum route → lessons, practice, cases, scripts, print
```

The v0.1 implementation stores ordered source units with locations, raw concepts with quotations, canonical concept memberships and a lesson plan. Atomic answer tokens, typed concept edges and hierarchical planning are proposed extensions to that design.

## Implemented checks

| Stage | Mechanism |
| --- | --- |
| File → units | Content hashes, source roles, stable IDs, ordered chunks and locations link accepted text to its input. |
| Unit → raw concepts | Readers receive assigned units and neighboring context. Concepts must cite quotations from their assigned teaching units. |
| Raw → canonical | A global reconciliation assigns every raw concept to one canonical concept and preserves member quotations. |
| Canonical → route | A global plan assigns each canonical concept to a lesson or records a deferral. |
| Route → output | Authoring, evidence checks and review produce a validated bundle, static reader and print exports. |

Held-out assessments stay outside extraction, authoring and public exports. Cache identity, durable jobs, leases and limited retries support recovery. Field contracts are in [Architecture](architecture.md) and [Adapters](adapters.md).

## Coverage and answer preservation

Let `U` be accepted source units and `Wᵢ` the units owned by extraction request `i`. Structural scan coverage is `|⋃ Wᵢ| / |U|`. A value of 1 means every accepted unit reached the extractor. Parsing losses and missed meaning within those units need their own measurements. Neighboring context helps interpretation while ownership stays with the assigned unit.

Let `R` be raw concepts and `K` canonical concepts. v0.1 enforces:

```text
For every r in R:  Σ[k in K] 1{r is a member of k} = 1
```

A canonical concept must inherit exactly its members' allowed quotations. This preserves records, but an explanation can still lose an answer: a paragraph may list four causes while the generated text names three.

The proposed answer-token model assigns a stable token to each extracted answer or claim, with its wording, scope, location and owner. For input tokens `T` and canonical answer items `A`, require:

```text
For every t in T:  Σ[a in A] 1{t is cited by a} = 1
For every citation t on a: owner(t) is a member of concept(a)
```

These checks catch missing tokens, duplicate ownership and attribution across clusters. Segmentation and interpretation still matter: a token for a compound sentence can conceal several propositions, and a valid citation can accompany a mistaken paraphrase.

Measure the stages separately: parsing, unit scanning, extraction recall, answer preservation, correctness, lesson support, question quality and learner outcomes.

## Consolidation choices

| Approach | Strength | Cost or failure mode | Use |
| --- | --- | --- | --- |
| Exact-key grouping | Cheap and easy to inspect | Misses synonyms; may collapse identical labels with different scope | Baseline for obvious duplicates |
| Global model reconciliation (v0.1) | Merges varied wording while preserving IDs and quotations | Whole-corpus requests grow; concept membership can conceal lost answers | Small corpora with merge review |
| Hierarchical answer-token reconciliation (proposed) | Local grouping, answer accounting and global exception review | More coordination; partitions can hide related material | Larger heterogeneous corpora after labeled merge tests |

The proposed hierarchy starts with source IDs and atomic claims. It partitions by retrieval task and context, groups locally, then reconciles likely relationships across partitions. A compact global record holds titles, scopes, answer-token counts, evidence quality and unresolved conflicts. Ambiguous merges stay apart or enter a review queue.

A term may describe a presentation, cause, complication or treatment failure. Populations can change the answer; sources can conflict; a broad concept can contain narrower ones. A proposed typed graph would express `same target`, `variant of`, `prerequisite`, `contrasts with` and `conflicts with`. v0.1 implements canonical memberships and lesson prerequisites.

## Search and curriculum order

v0.1 search combines body-text BM25, heading matches and optional supplied-vector ranks to find units relevant to a query. Curriculum ordering would use evidence such as reuse, source support, consequences of misunderstanding, documented assessment relevance, prerequisites and learner time. These factors can disagree: a rare distinction may matter more than a common term. Extraction confidence is another dimension.

Three routing policies are worth comparing:

1. A complete inventory maximizes discoverability at the cost of reading time.
2. A short first-pass route with deeper and lookup material preserves access while requiring revisable selection reasons.
3. An adaptive route could use learner performance and prerequisites. It needs outcome data, calibration, privacy controls and a tested update rule; v0.1 leaves this unimplemented.

Priority tiers should state the editor's rationale. A calibrated ranker would need independent relevance labels, agreement checks and held-out evaluation. Search scores and similarity to prior questions measure relevance, not future exam probability.

## Output forms

Each form has a job. Lessons explain causal models, recall prompts ask for reconstruction, contrasts distinguish confusable alternatives, and application prompts change the context. Cases reveal information in stages. Audio needs spoken pacing and pauses; print needs page structure and an answer key. The v0.1 bundle carries these forms with a common scope and source trail.

Retrieval practice has experimental support for delayed retention and some transfer to new questions or contexts. Interleaving can aid category discrimination in suitable tasks. See [Roediger and Karpicke (2006)](https://www.psychologicalscience.org/journals/psychological-science/j.1467-9280.2006.01693.x/), [Butler (2010)](https://pubmed.ncbi.nlm.nih.gov/20804289/), and [Birnbaum and colleagues (2013)](https://pubmed.ncbi.nlm.nih.gov/23138567/).

## Limits and evaluation

PDF parsing may miss figures, scans and layout. Extraction can omit important facts; preserved quotations can lose qualifiers in their interpretation. Plans account for extracted concepts, while order and importance remain model judgments. Model review and citations need content review to establish support and usefulness.

The v0.1 output forms have no comparative learning evaluation, audited audio synthesis or personalized spaced-repetition schedule. Source-role exclusion also needs a contamination audit for duplicates or paraphrases in teaching files. Published retrieval and interleaving studies motivate the formats; Lamina's items and learner outcomes require their own tests.

Use a stratified, manually annotated source set to measure extraction precision and recall, parser omissions, merge/split accuracy, qualifier preservation, answer-token conservation and route usefulness. Report disagreements and denominators. A delayed learner comparison would measure retention and transfer.
