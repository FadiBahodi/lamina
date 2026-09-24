# Engineering decisions

Lamina grew from several production systems: reference books, differential atlases, course extraction, podcasts and practice cases. They shared scheduling and recovery needs, but the work inside a model call differed. A reader identifying a few differentials can use a different workload from a writer building an explanation or an examiner designing staged disclosures.

The design keeps a common execution layer and makes source ownership, context, output requirements and checks specific to each stage.

## What we considered

| Problem | Alternatives | Choice |
| --- | --- | --- |
| Reading units | Paragraph calls, heading sections, fixed windows, semantic chunking | Group adjacent prose by section; preserve page and slide structures; measure per-stage limits. Request a neighboring group when a boundary blocks interpretation. |
| Evidence addresses | Copied quotations, paragraph IDs, sentence IDs, structured document blocks | Sentence-sized addresses over immutable source text. Tables, lists and code stay whole. Writers use markers; code derives quotations and claim records. |
| Sentence detection | Custom rules, syntok, spaCy | Conservative rules initially. Boundaries affect address convenience; source offsets and text establish the quotation. Evaluate a language-specific splitter when the failure corpus warrants it. |
| Structured output | Expected-shape prompts, JSON Schema, Pydantic, Instructor, BAML | Keep the current expected-shape prompts and Lamina's semantic source and ownership checks. Adapters use a real JSON Schema only when a request supplies one. Additional retry layers would duplicate the existing correction and accounting contract. |
| Execution | Local SQLite, Prefect, Temporal | Keep SQLite leases, fencing and the dependency scheduler for local runs. A hosted distributed deployment would justify revisiting an external workflow service. |
| Workload selection | Fixed universal sizes, manual settings, optimizer-driven tuning | Ship initial stage settings and a reproducible measurement command. Promote a tested setting when stored acceptance criteria pass. |
| Prompt optimization | Hand changes, DSPy | Establish held-out quality measurements before introducing an optimizer. Otherwise the optimizer can improve the chosen proxy while losing useful content. |

The W3C [Web Annotation model](https://www.w3.org/TR/annotation-model/) separates position and quotation selectors. Lamina uses the same design principle: a source revision plus deterministic character ranges, with quotations reconstructed from the stored source. Its evidence records are internal rather than a Web Annotation implementation.

[syntok](https://github.com/fnl/syntok) preserves token offsets; [spaCy](https://spacy.io/usage/linguistic-features#sbd) offers rule-based and trained sentence detection. Their value here would be more convenient boundaries in difficult text. A range can span several addresses when a condition crosses a boundary.

[Prefect caching](https://docs.prefect.io/v3/concepts/caching) and [Temporal workflows](https://docs.temporal.io/workflows) address broader execution environments. Lamina already has durable local jobs, owner leases and stale-writer fencing. Adding another scheduler now would introduce a second persistence and retry contract. Distribution should follow a concrete deployment need.

[DSPy optimizers](https://dspy.ai/learn/optimization/optimizers/) require a metric and examples. Lamina's immediate need is a trustworthy evaluation set and comparable runs across configurations. Optimization becomes useful once that measurement exists.

## What the earlier systems tell us

A September 2026 audit recovered 1,019 ROUNDS reader receipts with nonzero token counts. Prompt tokens had a median of 3,143 and a 90th percentile of 4,591. Output tokens had a median of 454 and a 90th percentile of 791. Planning requests held a median of 24 candidate ideas, a 90th percentile of 45 and a maximum of 75. Across 1,148 cached reader results, ideas per window had a median of two and a 90th percentile of four. Historical route sections had a median of one assigned idea and a 90th percentile of five.

Those measurements suggest initial reader experiments around 2,000–8,000 prompt tokens and writer experiments around one to six ideas. They describe the original model, prompts and source packets; the current protocol is measured separately.

The other systems used different structures. Differential extraction assigned 18 source units with two neighbors on each side. The exam factory used roughly 1,500 source words with three neighboring cards. ROUNDS used roughly 260 answer words with four neighboring cards. The common mechanism was clear ownership with context appropriate to the source. A single universal halo would discard that distinction.

Reference synthesis also needed family and global passes after extraction. One historical corpus contained 1,473 entries before consolidation. Local readers could recover candidates; deciding which concepts belonged together required a wider view. A smaller reader workload does not imply that every later stage should see equally little material.

## The next decisions depend on measurements

- **Source families:** evaluate reference writing, podcast design and case generation separately. A correct generic section is not sufficient evidence that a case has sensible reveal order or an audio script survives speech generation.
- **Planning:** retain global reconciliation where ownership or cross-family conflicts require it. Test earlier release of independent families against a full-plan baseline before removing the barrier.
- **Caching:** compare repeated runs and selective repairs using source, prompt, model and workload identities. Record where a reused result came from when adding cross-project reuse.
- **Reusable methods:** store applicability, context requirements and observed outcomes together. Evaluate whether a later task chooses or changes its method because of that record.

[Live model results](live-model-evaluation.md) record the first experiments. [Calibration](calibration.md) provides the experiment path. [System origins](system-origins.md) and [workflow design](workflow-design.md) describe the production mechanisms behind these decisions.
