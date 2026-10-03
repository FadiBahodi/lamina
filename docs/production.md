# Production

Import source files, describe the artifact you need and run it from the CLI, Python or the local Projects app. All three interfaces use the same engine. A production run can write directly from a small collection, plan a larger collection or follow sections supplied by a person or another agent.

Models make the editorial decisions: what matters, which ideas belong together and how to explain them. Lamina supplies the reusable machinery around that work. It keeps source identities stable, records which call owns each passage, supplies context, measures requests, schedules independent work together and saves results for recovery or revision.

## Choose a workflow

| Workflow | Work performed | Use |
| --- | --- | --- |
| `auto` | Checks the writing and review workload limits and request capacity, then selects direct or planned work; `format=cards` selects the sweep | You want Lamina to choose from the declared limits |
| `sweep` | Reads every window straight to flashcards, suppresses near-duplicates locally, audits a sample of windows, exports the deck | You want cards from a textbook or notes, as fast as the reads allow |
| `direct` | Writes from all selected source units, reviews the result and can repair and recheck it | The collection fits in one writing task |
| `planned` | Reads the sources, organizes sections, assigns material, then writes and reviews each section | The collection needs to be divided around a shared outline |
| `assigned` | Writes and reviews supplied sections with explicit source assignments | A person or another agent has already chosen the structure |

Automatic selection measures the complete writing request and the possible review and repair requests before work begins. It measures actual drafts and findings when they exist. The receipt stores the decision and its measurements in `workflow_decision`. If an actual review is too large, the receipt remains in `review` and names the check that could not run.

A provider profile separates the endpoint's hard request capacity from the amount of work you want one call to attempt. Context tokens, output allowance and transport bytes bound the request the endpoint will accept. `workload` limits bound the input tokens or item count assigned to a stage. Planning, writing or reviewing several items in one call requires an explicit workload policy.

Planned mode checks the policies for planning, writing and review before it starts paid reading. Automatic mode reports missing setup if choosing a route would require it to combine unprofiled work. A single assigned source structure can run without a workload profile only when the request includes no other source units, form examples or retained observations. A declared limit makes the resource decision visible; it says nothing about the quality the model will produce at that limit. See [Adapters](adapters.md) for configuration.

Python entry points are `plan_production(workspace, provider, brief, source_ids, options=None)`, `run_production(workspace, provider, plan, options=None)` and `build_production`, which combines both. A brief is text or `{goal, audience?, constraints?}`. Selected sources must have the teaching role.

## Sweep: straight to cards

`format="cards"` runs the sweep, the two-call-deep route Lamina grew out of. Every reader window is one independent call whose output is flashcards: each idea's title is the prompt (a question or a cloze sentence with `{{c1::hidden text}}`) and its explanation is the answer, with exact span citations. Nothing waits on a planner.

After reading, near-duplicate cards are suppressed with local similarity (provider embeddings when the adapter offers `embed(texts)`, otherwise TF-IDF; no model calls). A later card is dropped only when its similarity to a card already kept reaches `dedup_threshold`, so a chain of progressively different claims cannot collapse into one. Suppressed cards remain in the plan as explicit omissions with the card they duplicate and the score.

A deterministic sample of windows (`audit_rate`, default 0.25) then receives one `sweep_audit` call that sees the window's source text and its cards and reports omissions (a testable fact in the core that no card covers) and unsupported cards, each with exact evidence. Findings are attached to the receipt under `audit_findings`; they never remove a card. A window that fails to read is listed in `unresolved_reads`; the deck stays `ready` because every enabled check completed.

Exports add `cards.tsv` (prompt, answer, tags; Anki-importable) and `cards.json` (every card with its source, locator, unit IDs and quotations) beside the usual document. Receipt metrics report cards, suppressed duplicates, audited windows and audit findings.

## Read and organize the sources

The planned route begins with complete source structures such as a Markdown block, PDF page or PowerPoint slide group. Without a reading workload profile, each call owns one of those structures. A configured profile can put several structures from the same source in one call while respecting both the workload and request limits. Slide text, tables and speaker notes stay together. The plan stores each unit once and refers to it by ID. See [Parsing](parsing.md) for the retained structures.

A natural structure can still be dense, poorly parsed or difficult for the selected model. If one structure exceeds the configured limit, it needs explicit decomposition or a different policy. A valid JSON response proves that the response follows the data contract; it does not prove that the model understood the page.

`reading="task"` is the default. It asks readers to select useful ideas for the current brief. `reading="reusable"` creates an inventory independent of the brief and output format, recording statements, quantities, qualifications and relationships for later projects. Reuse avoids repeated extraction, but a missed idea can affect every project that uses that inventory. Evaluate it on the tasks it will support. Quotation matches and agreement between readers do not establish recall. The original passages accompany later writing so reviewers can inspect the source directly.

Readers cite bounded source references instead of copying whole quotations. Code resolves those references to exact spans in the original units. Unknown references and invalid ranges remain validation errors. Each idea must cite a core anchor; supporting references may also cite adjacent material actually supplied to that reader. These support dependencies accompany writing and review and participate in cache identity. A valid reference establishes location; semantic support still requires review.

A reader owns the structures assigned to it. By default it also sees a boundary halo: the last `reader_context_spans` sentence spans of the preceding unit and the first of the following unit, shown with their real span IDs so a citation of a halo span resolves against the complete unit. The halo shrinks to fit the reader budget rather than rejecting owned material. A reader can still ask for adjacent context with a reason; the first request in a direction completes the partial unit, the next steps to the following structure. Context clarifies a boundary without becoming a second source of extracted ideas. If a response is truncated, Lamina divides the owned material along complete structure boundaries and releases the children into the same worker pool with a fresh halo on their inner edge. Prepared reading batches start while later batches are still being measured. One oversized structure needs more capacity or explicit decomposition. A reading batch that fails after its retry is recorded in `plan.planning.unresolved_reads`; by default the run continues on the successful reads and the receipt says what was not read (`reading_failures="abort"` stops instead).

The planner receives an idea card with a title, explanation and evidence references for each extracted idea. Lamina removes repeated quotation text from the planning request and restores the references afterward. If the cards do not fit one outline call, grouping calls summarize them level by level. Level-0 batches keep source order, so a grouping call relates the adjacent cards that share a structure; cross-source mixing happens at the summary levels and in assignment. The tree streams: a grouping call at the next level starts as soon as a full batch of summaries exists, and only once the summaries that have arrived already exceed the outline budget. Each summary carries one original card as an exemplar into the outline call. Final assignment returns to every original card, gives it one section owner or records why it was omitted. The model decides the relationships across documents.

The engine then measures each planned section's writing and source-review requests. Assignments exceeding declared limits are subdivided into smaller coherent sections without discarding their material. The outline, each indivisible idea or target, and any required context must ultimately fit the configured limits.

## Give writers and reviewers the right context

A writer receives its assignment, the original supporting passages, any declared earlier evidence, relevant shared relationships and the titles and purposes of its immediate neighbors. A repeated source unit appears once in the request. Direct and assigned routes use original units without first creating extracted idea cards.

A reviewer is a model call with the draft, assignment and source context. It looks for missing meaning, unsupported claims, altered conditions, contradictions and leaked assessment answers. A concrete finding triggers one repair and recheck. Any remaining finding leaves the result in `review`.

Writers place compact source markers after supported statements. Lamina resolves each marker against only the source spans supplied to that section, reconstructs the exact quotations, derives claim records and removes the markers before export. Legacy adapters can still return the earlier body, evidence and claim-map shape. Lamina also checks that planned ideas have been accounted for, or that a direct or assigned section reports which source units it used and omitted. These checks make the trail inspectable. Review still has to decide whether the prose says what the source supports and covers what the artifact needs.

`document_review=true` compares completed neighboring sections and sections connected by a declared source, candidate or shared-context relationship. The receipt lists the checked pairs, their findings and any pair that could not fit or failed. It does not search for every possible relationship. Findings remain available for an explicit revision.

## Controls and their reasons

| Option | Default | Meaning and reason |
| --- | --- | --- |
| `format` | `document` | Also `guide`, `assessment`, `podcast-script`, `cards`; selects the output contract. `cards` selects the sweep workflow. |
| `workflow` | `auto` | Selects the route above. |
| `reading` | `task` | Reads for the current brief. `reusable` explicitly shares an unassessed inventory across goals. |
| `reader_context_spans` | `6` | Boundary halo: every reader also sees the last *n* sentence spans of the preceding unit and the first *n* of the following unit, with their real span IDs, so a boundary cut is visible without a second serial call (0–64; shrinks to fit the budget). `0` relies on context requests alone. See [flow geometry](flow-geometry.md#4-what-the-halo-was-for). |
| `reading_failures` | `continue` | `continue` plans from the successful reads, records unresolved windows in `plan.planning.unresolved_reads` and the receipt, and leaves a planned receipt in `review`. `abort` stops the plan on any unresolved read. |
| `audit_rate` | `0.25` | Sweep: fraction of reader windows that receive one source-centred audit call (0–1; sampling is deterministic per window). |
| `dedup_threshold` | by method | Sweep: similarity at or above which a later card is suppressed as a duplicate (0.92 for embeddings, 0.80 for TF-IDF). |
| `relation_threshold` | by method | `compare_relations`: similarity at or above which a pair is nominated for a model comparison (0.72 for embeddings, 0.20 for TF-IDF). |
| `episodes` | `auto` | Podcast scripts: number of episodes (1–64), or `auto` to let the outline choose from the amount of material. An explicit count greater than 1 forces the planned route. |
| `episode_minutes` | `20` | Podcast scripts: target listening time per episode; the outline receives a spoken-word budget of 150 words per minute and gives every section an `episode` and `target_words`. |
| `workers` | `16` | Local maximum simultaneous calls. A configurable resource ceiling, with no claim of optimal throughput. The bundled Gemini adapter admits 16 by default; raise both together. |
| `reader_workers`, `writer_workers`, `review_workers` | Inherit `workers` | Optional stage ceilings within the same total. |
| `max_attempts` | `2` | Original attempt plus one eligible correction/retry. A bounded resource policy; accepts 1–5. |
| `max_request_bytes` | `1500000` | Outer transport ceiling. The adapter may impose a smaller byte or token allowance. |
| `max_input_bytes` | Unset | Optional stricter byte allowance for a project. |
| `sections_per_request` | `1` | Opt-in maximum short sections in one writing or review request (1–32). Complete grouped requests must fit the stage workload and hard budget. Section identities, validation, repair and cache entries remain separate. |
| `compare_relations` | `false` | Compare nominated evidence groups before planning. Pairs are nominated by local similarity above `relation_threshold` plus same-unit and same-structure lanes; only nominated pairs reach a model call. Requires a `production_compare` workload profile; automatic workflow selection chooses planned reading. |
| `relation_neighbors` | `20` | Maximum similarity nominations per idea (1–100). Comparison may request additional evidence; this is a workload limit, not a completeness claim. |
| `document_review` | `false` | Adds the explicitly scoped cross-section checks above. |
| `retrieval_targets` | `false` | For guides/assessments, groups equivalent prompts and supported answers before section assignment. Requires planned mode. |

Worker settings accept 1 through 128. Byte limits accept 4096 through 2000000. Provider context and output limits, along with per-stage workload policies, belong in the [adapter profile](adapters.md). The other numeric defaults bound resource use and should be evaluated against the actual workload.

Legacy `core_words` and `halo_units` remain available for comparisons with older workflows. There is no default word target. A fixed halo requires an explicit `core_words` value and supports zero through eight neighboring units. By default, the reader asks for missing context when it needs it.

A complete `source_policy` map can mark sources `authority`, `supplement`, `historical` or `form_exemplar`; the default is authority. Form exemplars supply bounded structural samples and cannot support factual citations. `observation_ids` selects up to 20 retained observations in `method_family` (default `document-production`). The model interprets these supplied policies and observations.

## Caller-supplied sections

Use `workflow="assigned"` with an `assignments` object:

```json
{
  "title": "Wind turbines",
  "summary": "Explain the conversion from wind to electricity.",
  "sections": [{
    "id": "blades",
    "title": "Blades and rotation",
    "purpose": "Explain how wind turns the rotor.",
    "unit_ids": ["selected-unit-id"],
    "context_unit_ids": [],
    "representation": {
      "kind": "explanation",
      "rationale": "Describe the physical sequence.",
      "requirements": []
    }
  }],
  "omitted": [],
  "shared_context": []
}
```

Every selected factual unit needs one section owner or an omission `{unit_id, reason}`. Context may be shared. `context_section_ids` requests earlier sections' source evidence. `candidate_context_ids` requests earlier completed candidate prompts during assessment checking. Dependencies on finished prerequisite prose use the general [method runtime](methods.md).

## Reuse, revision and failure

Pass `section_notes={section_id: "requested change"}` to revise a saved plan. The browser retains earlier revision notes. Every cache key includes the semantic inputs and adapter identity, so an unchanged request can reuse its result while an affected request runs again. Reusable readings omit the current brief and output format from that identity. A section request includes its local assignment, visible outline and declared context. After reuse, Lamina binds citations to the selected revision of the source.

Edits can change packing boundaries or required context and invalidate additional work. There is no constant-cost guarantee for source edits. A new brief still plans across the complete extracted inventory; automatic retrieval-based subset selection is unavailable.

Plans retain source snapshots and provider configuration. Changed goals, source content, format or source policy require replanning, which can reuse eligible readings.

When extraction returns invalid rows, a correction request identifies those rows and preserves the accepted ones. Lamina validates the combined result afterward. A malformed response envelope or broader contract failure can require the model to replace the whole result. Legacy quote-based replies use conservative normalization for formatting differences while returning the exact original span. Provider-declared transient failures can retry within `max_attempts`.

Invalid material remains visible as unresolved work, and only a fully validated result enters the successful cache. Independent jobs can finish and retain their results after a sibling fails. A restart reuses completed requests. Renewable leases and owner fencing prevent an expired worker from writing over its replacement.

Receipts record request sizes, attempts, failures, cache hits, elapsed times and reported token usage. `provider_request_bytes` counts actual provider attempts, including failed attempts; missing usage remains unknown. Coverage reports distinguish source material considered, reader citations, assignment and output citations. These counts cannot detect every silently omitted fact. The [quality evaluation protocol](quality-evaluation.md) tests fragile facts across workload sizes and follows them into the finished output. Semantic recall and live model performance require those separate measurements.

## Export documents, assessments and podcast scripts

Assessments export separate candidate and examiner files. A blind solver receives the current candidate prompt and only the earlier prompts declared as context. A judge receives the answer, marking guide and source quotations. Solver and judge pairs run independently within the shared worker limit. Their findings stay in examiner and operator records. Use stateless adapters to preserve these information boundaries.

A podcast script is planned in episodes. The outline numbers every section with an `episode` and a `target_words` budget sized from `episode_minutes` (150 spoken words per minute); sections of one episode are consecutive in listening order, and a subdivided section's children inherit its episode and share its words. Writers are told their episode and word target. The receipt carries `episodes`, the export writes `episode-NN.md` and `.html` per episode, and audio delivery assembles `episode-NN.wav` per episode beside the full `narration.wav`. An outline that does not number sections produces one episode unless a count was requested.

A podcast script uses a separate speech adapter. When the adapter is given to `run_production` (the CLI and the local app do this), each section is synthesized on a speech lane the moment it leaves review, bounded by the adapter's declared `audio_concurrency`, as the same cached segment delivery later assembles; speech overlaps writing instead of following it, and the receipt's `speech_prefetch` metric lists the sections rendered that way. Delivery assembles matching PCM formats in order on disk. Only affected segments rerender after revision. Receipts without section objects retain whole-script compatibility. Individual adapter responses retain the 20 MB limit; the assembled WAV does not travel as base64 and may be larger. A failed segment leaves successful segment files and cache results available for recovery. By default (`--audio-when any`) a script still in `review` renders too; the audio manifest names the sections with remaining findings as `provisional_sections` and the receipt stays in `review`. `--audio-when ready` withholds audio until every check passes. Someone still needs to listen for pronunciation, pacing, fidelity and educational quality.

`export_production(receipt, plan, output_path)` writes Markdown, HTML, a JSON receipt, the plan and an optional PDF. Plans and receipts contain source text and can include assessment keys. `ready` means that the enabled checks completed. The plan and receipt also record `semantic_recall: "unmeasured"`, and plan validation protects that declaration from silent removal. Evaluate factual accuracy and delivery quality on the exported artifact.

The local app runs one project at a time and allows parallel calls inside that project. It polls compact `/api/progress/{id}` records, obtains up to ten bounded previews from `/api/section-updates/{id}/{cursor}`, fetches the full result from `/api/runs/{id}` and stores plans separately from receipts. Previews remain provisional until all enabled project checks finish. Assessment previews contain candidate text only. The raw-file upload route accepts up to 256 MiB per file and writes bounded chunks to temporary disk; the older JSON upload route retains its original limits. An interrupted project can resume from cached work. Keep the app on loopback because project identifiers do not provide authentication.

Writer source references use compact markers such as `[s3]` and `[s3-s5]`. Escape a literal marker with a Markdown backslash (`\[s3]`) when discussing that notation. Evidence records store a source unit and its quotation; identical repeated quotations within one unit share the same quote locator.

See [evidence and execution changes](evidence-execution.md) for the grouping, comparison, cache, measurement and delivery contracts.
