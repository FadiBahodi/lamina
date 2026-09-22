# Producing a document

The CLI, Python API and local Projects app use the same engine. Import sources, describe the result, then run. Models choose meaning and wording; code assigns source ownership, checks references and schedules calls.

## Choose a workflow

| Workflow | What happens | When to use it |
| --- | --- | --- |
| `auto` (default) | Chooses direct writing for small inputs; otherwise uses the planned path | Start here |
| `direct` | A writer receives the selected source text, then a reviewer checks its result | The collection fits one request |
| `planned` | Readers extract cited ideas; a planner assigns them to sections; sections are written and reviewed | The collection needs a shared editorial plan |
| `assigned` | The caller supplies sections and source assignments; sections are written and reviewed | An agent or person already knows the structure |

Automatic selection uses serialized input size, with a conservative 24 KB ceiling and space reserved for instructions and output. This is a transport decision, not an estimate of intellectual difficulty. A request that exceeds its budget fails before the model call; no text is silently dropped to fit.

`plan_production(workspace, provider, brief, source_ids, options=None)` creates a saved plan. `run_production(workspace, provider, plan, options=None)` writes it. `build_production` does both. A brief is text or `{goal, audience?, constraints?}`. Selected sources must have the teaching role.

In the planned path, readers own complete source units. Optional neighboring units provide context but cannot originate a second reader's ideas. The planner sees ideas and their cited excerpts, then assigns each idea once or explains its omission. Each writer sees a short outline, its assigned ideas and source passages, and explicitly requested context. Source passages let it check qualifications and relationships that an extracted idea may omit. Repeated unit IDs are sent once per request.

In direct and assigned paths, there is no model-generated idea layer. Writers account for assigned source units with `used_unit_ids` and `omitted_units`. This proves explicit accounting, not that every fact reached the output.

### Caller-supplied sections

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

Every selected factual unit needs one section owner or an omission `{unit_id, reason}`. Context may be shared. `context_section_ids` requests earlier sections' source evidence; `candidate_context_ids` requests earlier candidate prompts during assessment checks. Neither means waiting for earlier finished prose. The general [method runtime](methods.md) supports dependencies on completed outputs.

## Controls

| Option | Default | Meaning |
| --- | --- | --- |
| `format` | `document` | Also `guide`, `assessment`, `podcast-script` |
| `workers` | 8 | Total simultaneous model calls in a production phase |
| `reader_workers`, `writer_workers`, `review_workers` | Inherit `workers` | Optional stage ceilings within that total |
| `core_words` | 1600 | Approximate reading batch target; dense text also counts by byte size |
| `halo_units` | 0 | Extra neighboring units on either side, within the source |
| `max_input_bytes` | 120000 | Maximum serialized stage request size, including instructions |
| `max_request_bytes` | 1500000 | Compatibility transport ceiling; the smaller ceiling applies |

Worker counts accept 1–128; `core_words` accepts 100–2000; `halo_units` accepts 0–8; byte ceilings accept 4096–2000000. These limits control resources. They do not choose topics or impose a lesson count. Adapters enforce the selected model's token budget separately.

A complete `source_policy` map can mark sources `authority`, `supplement`, `historical`, or `form_exemplar`. All default to authority. Form exemplars supply bounded structural samples and cannot support factual citations. `observation_ids` selects up to 20 saved observations within `method_family` (default `document-production`). Their interpretation remains a model decision.

For guides and assessments, `retrieval_targets=true` adds a stage that groups equivalent prompts and source-backed answers. It requires the planned path; automatic mode selects that path when enabled. It is optional because many documents do not need a question catalog.

## Writing, review and revision

Each section proceeds through writing and review as soon as capacity permits. A finding triggers one repair and recheck. Unresolved findings leave the result in `review`. Sections retain their planned order in the export.

Pass `section_notes={section_id: "requested change"}` to revise a saved plan. Unchanged requests reuse cached results. The browser retains earlier revision notes. Plans contain source snapshots and are tied to their goal and provider configuration; changing those requires planning again. Unchanged reader input can still reuse its cached interpretation after a source-file edit, with citations rebound to the current snapshot.

Receipts record request sizes, cache hits, elapsed times and reported token usage. Logical request bytes include cached requests; `provider_request_bytes` counts only calls actually attempted. Missing provider usage is not a zero-cost claim. Timings from deterministic fixtures do not measure model quality or production latency.

## Assessments and audio

Assessments export separate candidate and examiner files. Blind solves receive the current candidate prompt and only explicitly declared earlier candidate prompts. A separate judge receives the answer, marking guide and exact source excerpts. Solver/judge pairs run independently within the shared call limit. Findings stay in examiner/operator records.

A ready podcast script can be rendered through a separate audio adapter. The current implementation synthesizes the whole script under a per-user process lock, validates PCM WAV structure and duration, and records the submitted text. It does not yet provide section-level speech rendering or a listened audio audit.

## Export and recovery

`export_production(receipt, plan, output_path)` writes Markdown, HTML, a JSON report, the saved plan, and PDF when the `pdf` extra is installed. Plans and reports contain source text and may contain assessment keys.

The local app runs one project at a time with parallel calls inside it. It persists plans and receipts separately from compact progress records. After restart, unfinished projects become `interrupted`; resume reuses completed cached requests and restarts interrupted calls. Renewable SQLite leases and owner tokens protect cache commits.

| HTTP request | Result |
| --- | --- |
| `POST /api/projects` with `{brief, source_ids, options}` | Start a project |
| `GET /api/progress/{id}` | Compact progress without source text or receipt |
| `GET /api/runs/{id}` | Full plan, receipt and output links |
| `GET /api/projects` | Recent projects |
| `POST /api/projects/{id}/revise` with `{section_notes}` | Revise selected sections |
| `POST /api/projects/{id}/resume` with `{}` | Resume retained work |

Adapters are configured at server startup. Keep this local app on loopback; project IDs are not authentication credentials.

## Limits

The planned path still makes one global planning request. Oversized collections need caller-supplied assignments or a narrower project; automatic hierarchical planning is not implemented. Quote checks prove exact provenance, not factual truth or semantic completeness. Separate assessment calls require a stateless provider to maintain their information boundary. PDF figures, live oral-case administration and automatic method learning remain outside this implementation. See [parsing](parsing.md) and [architecture status](architecture-status.md).
