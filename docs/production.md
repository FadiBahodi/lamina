# Production

Import source files, describe the artifact you need and run it from the CLI, Python or the local Projects app. All three interfaces use the same engine. A production run can write directly from a small collection, plan a larger collection or follow sections supplied by a person or another agent.

Models make the editorial decisions: what matters, which ideas belong together and how to explain them. Lamina supplies the reusable machinery around that work. It keeps source identities stable, records which call owns each passage, supplies context, measures requests, schedules independent work together and saves results for recovery or revision.

## Choose a workflow

| Workflow | Work performed | Use |
| --- | --- | --- |
| `auto` | Checks the writing and review workload limits and request capacity, then selects direct or planned work | You want Lamina to choose from the declared limits |
| `direct` | Writes from all selected source units, reviews the result and can repair and recheck it | The collection fits in one writing task |
| `planned` | Reads the sources, organizes sections, assigns material, then writes and reviews each section | The collection needs to be divided around a shared outline |
| `assigned` | Writes and reviews supplied sections with explicit source assignments | A person or another agent has already chosen the structure |

Automatic selection measures the complete writing request and the possible review and repair requests before work begins. It measures actual drafts and findings when they exist. The receipt stores the decision and its measurements in `workflow_decision`. If an actual review is too large, the receipt remains in `review` and names the check that could not run.

A provider profile separates the endpoint's hard request capacity from the amount of work you want one call to attempt. Context tokens, output allowance and transport bytes bound the request the endpoint will accept. `workload` limits bound the input tokens or item count assigned to a stage. Planning, writing or reviewing several items in one call requires an explicit workload policy.

Planned mode checks the policies for planning, writing and review before it starts paid reading. Automatic mode reports missing setup if choosing a route would require it to combine unprofiled work. A single assigned source structure can run without a workload profile only when the request includes no other source units, form examples or retained observations. A declared limit makes the resource decision visible; it says nothing about the quality the model will produce at that limit. See [Adapters](adapters.md) for configuration.

Python entry points are `plan_production(workspace, provider, brief, source_ids, options=None)`, `run_production(workspace, provider, plan, options=None)` and `build_production`, which combines both. A brief is text or `{goal, audience?, constraints?}`. Selected sources must have the teaching role.

## Read and organize the sources

The planned route begins with complete source structures such as a Markdown block, PDF page or PowerPoint slide group. Without a reading workload profile, each call owns one of those structures. A configured profile can put several structures from the same source in one call while respecting both the workload and request limits. Slide text, tables and speaker notes stay together. The plan stores each unit once and refers to it by ID. See [Parsing](parsing.md) for the retained structures.

A natural structure can still be dense, poorly parsed or difficult for the selected model. If one structure exceeds the configured limit, it needs explicit decomposition or a different policy. A valid JSON response proves that the response follows the data contract; it does not prove that the model understood the page.

`reading="task"` is the default. It asks readers to select useful ideas for the current brief. `reading="reusable"` creates an inventory independent of the brief and output format, recording statements, quantities, qualifications and relationships for later projects. Reuse avoids repeated extraction, but a missed idea can affect every project that uses that inventory. Evaluate it on the tasks it will support. Quotation matches and agreement between readers do not establish recall. The original passages accompany later writing so reviewers can inspect the source directly.

Readers cite bounded source references instead of copying whole quotations. Code resolves those references to exact spans in the original units. Unknown references, invalid ranges and citations outside the owned material remain validation errors. A valid reference establishes location; semantic support still requires review.

A reader owns the structures assigned to it and can ask for adjacent context with a reason. That context can clarify a boundary without becoming a second source of extracted ideas. It must also fit the request budget. If a response is truncated, Lamina divides the owned material along complete structure boundaries and retries the smaller readings. One oversized structure needs more capacity or explicit decomposition. Failed readings remain unresolved; independent successful readings stay in the cache.

The planner receives an idea card with a title, explanation and evidence references for each extracted idea. Lamina removes repeated quotation text from the planning request and restores the references afterward. If the cards do not fit, bounded calls group them into a smaller outline. Final assignment returns to every original card, gives it one section owner or records why it was omitted. The model decides the relationships across documents.

The engine then measures each planned section's writing and source-review requests. Assignments exceeding declared limits are subdivided into smaller coherent sections without discarding their material. The outline, each indivisible idea or target, and any required context must ultimately fit the configured limits.

## Give writers and reviewers the right context

A writer receives its assignment, the original supporting passages, any declared earlier evidence, relevant shared relationships and the titles and purposes of its immediate neighbors. A repeated source unit appears once in the request. Direct and assigned routes use original units without first creating extracted idea cards.

A reviewer is a model call with the draft, assignment and source context. It looks for missing meaning, unsupported claims, altered conditions, contradictions and leaked assessment answers. A concrete finding triggers one repair and recheck. Any remaining finding leaves the result in `review`.

Writers link exact spans of their output to supporting quotations. Lamina validates those links and reports claims without a map. It also checks that planned ideas have been accounted for, or that a direct or assigned section reports which source units it used and omitted. These checks make the trail inspectable. Review still has to decide whether the prose says what the source supports and covers what the artifact needs.

`document_review=true` compares completed neighboring sections and sections connected by a declared source, candidate or shared-context relationship. The receipt lists the checked pairs, their findings and any pair that could not fit or failed. It does not search for every possible relationship. Findings remain available for an explicit revision.

## Controls and their reasons

| Option | Default | Meaning and reason |
| --- | --- | --- |
| `format` | `document` | Also `guide`, `assessment`, `podcast-script`; selects the output contract. |
| `workflow` | `auto` | Selects the route above. |
| `reading` | `task` | Reads for the current brief. `reusable` explicitly shares an unassessed inventory across goals. |
| `workers` | `8` | Local maximum simultaneous calls. A configurable resource ceiling, with no claim of optimal throughput. |
| `reader_workers`, `writer_workers`, `review_workers` | Inherit `workers` | Optional stage ceilings within the same total. |
| `max_attempts` | `2` | Original attempt plus one eligible correction/retry. A bounded resource policy; accepts 1–5. |
| `max_request_bytes` | `1500000` | Outer transport ceiling. The adapter may impose a smaller byte or token allowance. |
| `max_input_bytes` | Unset | Optional stricter byte allowance for a project. |
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

A ready podcast script can use a separate speech adapter. Lamina sends the whole script, caches the result and validates the PCM WAV structure and duration. Someone still needs to listen for pronunciation, pacing, fidelity and educational quality.

`export_production(receipt, plan, output_path)` writes Markdown, HTML, a JSON receipt, the plan and an optional PDF. Plans and receipts contain source text and can include assessment keys. `ready` means that the enabled checks completed. The plan and receipt also record `semantic_recall: "unmeasured"`, and plan validation protects that declaration from silent removal. Evaluate factual accuracy and delivery quality on the exported artifact.

The local app runs one project at a time and allows parallel calls inside that project. It polls compact `/api/progress/{id}` records, fetches the full result from `/api/runs/{id}` and stores plans separately from receipts. An interrupted project can resume from cached work. Keep the app on loopback because project identifiers do not provide authentication.
