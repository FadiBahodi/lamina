# Where Lamina's production methods came from

Lamina grew from several kinds of source work: reference PDFs, educational audio, written exam questions and staged oral cases. Each required agents to read more material than one writer could use at once. The reusable design question was how to divide that reading, carry the right context into each decision, and deliver an object people could actually use. The answer changed with the task. A differential reference organizes what a patient presentation asks the reader to distinguish; an audio series needs a route that remains intelligible when heard; an oral case reveals information over time.

A recurring failure across these systems was a polished artifact with an important answer missing or badly explained, while its source citations and processed-page counts looked correct. The design therefore needs a traceable chain:

```text
source region -> claim or answer -> editorial decision -> section or omission -> review -> repair -> delivered version
```

An editor should be able to find the source, understand an omission and open the delivered revision.

## One source library, several valid products

A large reference library first produced a broad differential atlas. Readers worked through bounded page and slide windows, each with owned core material and neighboring context. They returned candidate lists with source identities. The build preserved a large source-derived inventory and offered interactive question fields; conservative grouping left many related fragments as separate drills. A later design pass changed the unit of work: independent readers proposed question objects within clinical families, family editors reconciled equivalent questions, and a whole-book editor chose a study route. Code checked that each source member and its answer material survived the merge. A final, stricter pass assigned one owner to each original question object while allowing the same diagnosis to appear in genuinely different presentations. The first atlas recorded 1,473 entries across 1,579 pages; a later, narrower question atlas recorded 122 canonical objects across 270 pages.

A separate reference book took another route. It made the *presentation* the unit: a short case, alternative diagnoses with discriminating clues, a narrowing step, dangers and an answered change in the case. Contents, bookmarks and a diagnosis index let readers move between presentations where a finding has a different meaning. Its 205 presentation sheets occupied 263 pages. This form serves a reader trying to reason from a symptom; the canonical question atlas serves direct retrieval. One universal template would erase that difference.

These page counts describe different output scopes and the design progression. They do not establish relative quality or speed, and the saved receipts provide no matched cold-build comparison.

The same library also contained short markable lists, treatment sequences, procedural steps and questions whose original case context was missing. The list-vault build routed 1,376 source objects to their appropriate destination, including a quarantine for prompts requiring their original case to be answerable. That routing decision came before layout and kept incomplete questions out of finished study pages.

## What travels between projects

An agent can reuse a **method contract** across projects. It states the requested output and acceptance test; inventories available sources and their roles; identifies stable source units with ownership and neighboring context; chooses a representation suited to the reader's question; sets when workers share a plan or wait for completed results; and checks the delivered artifact. The agent adapts the answer schema, source policy and worker graph to each product.

Models make semantic decisions: whether two prompts ask the same thing, how answer items belong together, what deserves a study-first place, and how to explain it. Code handles source identity, one-owner accounting, resource limits, cache keys, provenance and exact output checks. That division lets independent reading proceed concurrently while family-wide or whole-product decisions wait for the context they need. It also makes a local revision possible: a corrected section can reuse unaffected reading and writing. Historical PDF receipts show these work boundaries and reuse opportunities; a matched cold-run comparison would measure the resulting speed.

The other source families make the same context question visible in different ways. Audio writers need a common route and exact evidence; a callback to an earlier idea may require completed prose. Speech generation then occupies a separate resource lane, followed by an audio and player check. Written question generation needs a setter's intended answer, a blind candidate solve and a separate examiner judgment. An oral case additionally needs staged reveal, consequences of candidate actions and a private examiner marking view. Each output uses the shared ingestion ideas under its own delivery contract. [Workflow design](workflow-design.md) describes how the current engine serves each family.

## What the earlier workloads measured

A September 2026 audit recovered 1,019 reader receipts with nonzero token counts from the audio lesson system. Prompt tokens had a median of 3,143 and a 90th percentile of 4,591. Output tokens had a median of 454 and a 90th percentile of 791. Planning requests held a median of 24 candidate ideas, a 90th percentile of 45 and a maximum of 75. Across 1,148 cached reader results, ideas per window had a median of two and a 90th percentile of four. Historical route sections had a median of one assigned idea and a 90th percentile of five. These figures suggested initial reader experiments around 2,000–8,000 prompt tokens and writer experiments around one to six ideas. They describe the original model, prompts and source packets; [live model results](live-model-evaluation.md) measure the current protocol.

The systems used different neighboring context. Differential extraction assigned 18 source units with two neighbors on each side. The exam factory used roughly 1,500 source words with three neighboring cards. The audio lesson system used roughly 260 answer words with four neighboring cards. Each kept clear ownership and sized context to its source. The current halo is likewise a setting (`reader_context_spans`), and readers can request more context with a reason.

Reference synthesis also needed family and global passes after extraction. One historical corpus contained 1,473 entries before consolidation. Local readers could recover candidates; deciding which concepts belonged together required a wider view. A small reader workload therefore does not imply that every later stage should see equally little material.

## Historical audio timings

These observations come from saved records in the audio lesson system's 4 September 2026 infrastructure review. They do not measure current Lamina performance.

| Historical audio observation | Sample and clock |
| --- | --- |
| 109.06 seconds to saved script, median | 82 rendered audio parts; measured from engine start and excluding queue wait. |
| 336.65 seconds to ready part, median | The same 82 parts; parts shared setup and contended for local media capacity. |
| 575.54 seconds job service, median | 19 completed course jobs; one job could produce several parts. |
| 5,042.11 seconds queue wait, median | The same 19 jobs in that saved batch. |
| 73.754 seconds planning; 4.122 seconds for the slowest of eight writers | One recorded part; call timers included provider-gate waiting. |

The 82-part sample included four recorded model-cache hits and had a median delivered duration of 18.47 minutes. Subtracting the median script and ready times does not recover one stage duration, because jobs and parts shared setup and waited on different resources. The private source text and production logs are outside this repository.

## From these systems to the current engine

Lamina's card sweep keeps the two-call-deep route the engine grew out of: independent readers write finished cards and a sampled audit checks them, with no planner in between. [Capability status](architecture-status.md) lists what the current engine implements and its limits.

An earlier fixed-format builder ran one extract, reconcile, plan, author and review pipeline with a fixed amount of neighboring context for every source. The source-aware production engine replaced it, and the builder has since been removed.

## Limits

Reference work: retrieval targets cover extracted ideas, not an audited cross-PDF inventory of original question objects. There is no router that sends procedural steps or context-dependent prompts to separate products, and PDF export has no atlas-scale visual and navigation acceptance pass. Text extraction does not interpret arbitrary figures or tables.

Audio: WAV structure checks do not establish spoken fidelity. Spoken-turn repair, transcript comparison, a timed transcript and a phone player remain outside the engine.

Questions and cases: exported assessments are not live staged oral cases. The engine has no single setter over a staged case and does not repeat the solve-and-judge loop after a repair.
