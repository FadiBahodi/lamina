# Producing a document

Import sources, describe the result, and run. The CLI, Python API and local Projects app use the same engine. Models choose what belongs together and how to explain it. Code preserves source identity, measures requests, checks ownership and schedules calls.

## Choose a workflow

| Workflow | Work performed | Use |
| --- | --- | --- |
| `auto` | Measures direct writing and source-review capacity; selects direct or planned | Default capacity-based choice |
| `direct` | Write from all selected source units, review, optional repair/recheck | A complete collection fits the chosen models |
| `planned` | Read sources, organize sections, assign material, write and review each section | The collection needs decomposition and a shared outline |
| `assigned` | Write and review caller-supplied sections with explicit source assignments | A person or another agent already chose the structure |

Automatic selection checks the complete writing envelope and review/repair envelopes with empty drafts. Actual drafts and findings are checked when available. The decision and measurements are saved in `workflow_decision`. If an actual review cannot fit, the receipt remains `review` and identifies the unperformed check.

A configured provider can supply its tokenizer, model context limit and output allowance. Generic adapters supply a byte transport guard. Size measurements govern capacity. Appropriate task size and output quality require evaluation. See [Adapters](adapters.md) for configuration.

Python entry points are `plan_production(workspace, provider, brief, source_ids, options=None)`, `run_production(workspace, provider, plan, options=None)` and `build_production`, which combines both. A brief is text or `{goal, audience?, constraints?}`. Selected sources must have the teaching role.

## Reading and organization

The planned route packs complete source structures into measured reader requests. Batches can cross headings within one source. Slide components stay together. Plans store units once and reference them by ID. See [Parsing](parsing.md) for the retained structures.

`reading="reusable"` creates a source inventory independent of the project's brief and output format. It preserves cited statements, quantities, qualifications and relationships for later projects. `reading="task"` selects useful ideas for the current brief during reading. Original source passages accompany later writing so omitted qualifications can be checked.

A reader may request adjacent source context with a specific reason. Added context cannot originate duplicate ideas and must fit the request budget. If a reader's output is truncated, the engine divides its owned material between complete structures and retries the smaller readings. A single oversized structure requires more capacity or explicit decomposition. Failed readings remain unresolved while independent successful readings stay cached.

The planner receives full idea titles and explanations with evidence references. Code removes repeated quotation text from planning requests and restores the original references afterward. When those cards exceed capacity, bounded model calls group them into a smaller outline. Final assignment revisits every original card and accounts for it once or records an omission. Models choose cross-document relationships.

The engine then measures each planned section's writing and source-review requests. Oversized assignments are subdivided into smaller coherent sections without discarding their material. The outline, each indivisible idea or target, and any required context must ultimately fit a request.

## What each writer and reviewer sees

A writer receives its assignment, original source passages, declared earlier evidence, relevant shared relationships, and the titles and purposes of its immediate neighbors. Repeated source unit IDs appear once per request. Direct and assigned workflows use original units without an extracted-idea layer.

A reviewer is a model call that compares the actual draft with that assignment and source context. It checks missing meaning, unsupported claims, altered conditions, contradictions and assessment leakage. A concrete finding triggers one repair and recheck. Unresolved findings leave the result in `review`.

Writers are asked to link exact output spans to supporting source quotations. Code checks supplied links and reports missing claim maps. It also checks explicit accounting for assigned ideas, or used/omitted source units in direct and assigned routes. Review must inspect whether the actual prose fulfills those reports. Source occurrence alone leaves semantic support and completeness unproven.

`document_review=true` adds checks between completed neighboring sections and sections connected by declared source, candidate or shared-context relationships. The receipt lists checked pairs, findings and pairs that could not fit or failed. Other possible relationships remain outside that review. Its findings remain available for explicit revision.

## Controls and their reasons

| Option | Default | Meaning and reason |
| --- | --- | --- |
| `format` | `document` | Also `guide`, `assessment`, `podcast-script`; selects the output contract. |
| `workflow` | `auto` | Selects the route above. |
| `reading` | `reusable` | Retains source interpretations across goals; use `task` for brief-specific reading. |
| `workers` | `8` | Local maximum simultaneous calls. A configurable resource ceiling, with no claim of optimal throughput. |
| `reader_workers`, `writer_workers`, `review_workers` | Inherit `workers` | Optional stage ceilings within the same total. |
| `max_attempts` | `2` | Original attempt plus one eligible correction/retry. A bounded resource policy; accepts 1–5. |
| `max_request_bytes` | `1500000` | Outer transport ceiling. The adapter may impose a smaller byte or token allowance. |
| `max_input_bytes` | Unset | Optional stricter byte allowance for a project. |
| `document_review` | `false` | Adds the explicitly scoped cross-section checks above. |
| `retrieval_targets` | `false` | For guides/assessments, groups equivalent prompts and supported answers before section assignment. Requires planned mode. |

Worker settings accept 1–128. Byte limits accept 4096–2000000. Provider context/output limits belong in the [adapter profile](adapters.md). The remaining numeric defaults bound resources and remain choices to evaluate against the actual workload.

Legacy `core_words` and `halo_units` remain explicit overrides for comparisons with older workflows. There is no default word target. A fixed halo requires an explicit `core_words` value; its supported range is 0–8 neighboring units. The default reader requests missing context as needed.

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

Pass `section_notes={section_id: "requested change"}` to revise a saved plan. The browser retains earlier revision notes. Unchanged requests reuse cached results. Reusable readings omit the current brief and output format from their request identity. Section requests include only their local assignment, visible outline and declared context. Citations are rebound to the selected source revision after reuse.

Edits can change packing boundaries or required context and invalidate additional work. There is no constant-cost guarantee for source edits. A new brief still plans across the complete extracted inventory; automatic retrieval-based subset selection is unavailable.

Plans retain source snapshots and provider configuration. Changed goals, source content, format or source policy require replanning, which can reuse eligible readings.

Retryable validation failures receive specific feedback. Conservative quote normalization can recover formatting differences while returning the exact original source span. Provider-declared transient failures can retry within `max_attempts`. Invalid material remains visible as unresolved work, and only a fully validated result is cached as successful. Independent jobs finish and retain their results after a sibling fails. Restarting reuses those completed requests under renewable leases and owner fencing.

Receipts record request sizes, attempts, failures, cache hits, elapsed times and reported token usage. `provider_request_bytes` counts actual provider attempts, including failed attempts; missing usage remains unknown. Coverage reports distinguish source material considered, reader citations, assignment and output citations. Semantic recall and live model performance require separate evaluation.

## Assessments, audio and export

Assessments export separate candidate and examiner files. Blind solves receive the current candidate prompt and only declared earlier candidate prompts. A judge receives the answer, marking guide and source quotations. Solver/judge pairs run independently within the shared limit. Findings stay in examiner/operator records. Keep adapters stateless to preserve these information boundaries.

A ready podcast script can use a separate speech adapter. Current audio synthesis covers the whole script, caches results and validates PCM WAV structure and duration. Listening quality and spoken fidelity require a separate check.

`export_production(receipt, plan, output_path)` writes Markdown, HTML, a JSON receipt, the plan and optional PDF. Plans and receipts contain source text and can contain assessment keys. `ready` records completion of enabled checks. Factual accuracy and delivery quality require evaluation.

The local app runs one project at a time with parallel calls inside it. It polls compact `/api/progress/{id}` records, fetches full `/api/runs/{id}` results, and persists plans and receipts separately. Interrupted projects can resume cached work. Keep the app on loopback; project identifiers do not provide authentication.
