# Command adapters

Lamina's core handles identities, storage, evidence checks, scheduling, and export. A command adapter handles interpretation and writing. It receives JSON on standard input and returns JSON on standard output. It should write diagnostics to standard error, never mix logs into standard output, and exit nonzero on failure. Lamina invokes the command as an argument vector without a shell.

```bash
lamina build --workspace .lamina --adapter 'python my_adapter.py' --output ./site
```

Lamina computes the command adapter's cache identity from its argument vector, readable script-file hashes, timeout, and a configured version. Set `LAMINA_ADAPTER_VERSION` or pass `--adapter-version` when changing an endpoint, model, prompt, policy, or other behavior that those inputs do not capture. The executable returns stage JSON, not its own identity. The [HTTP example](../examples/adapter/README.md) uses `LAMINA_API_BASE`, `LAMINA_MODEL`, and `LAMINA_API_KEY`; Lamina itself does not store those values. The command adapter accepts at most 2 MB per request by default. Reconciliation and planning are global passes, so a large extracted concept set may exceed that bound and require a narrower corpus or a different adapter design.

## Stages

| Stage | Input | Required output |
| --- | --- | --- |
| `extract` | One teaching unit and bounded neighboring context | Concepts with titles, explanations, and exact quote evidence |
| `reconcile` | All extracted concepts and their evidence | Canonical concepts with member IDs; all members and their evidence accounted for exactly once |
| `plan` | All canonical concepts | Ordered lessons with concept IDs and earlier-lesson prerequisites; explicit deferred concepts |
| `author` | One planned lesson and its concepts/evidence | Lesson text, source-backed sections, recall/contrast/apply questions, and speech/pause script |
| `review` | One authored lesson and the stated checks | `pass` or `revise`, with actionable issues for revision |

The JSON schemas in the installed package are authoritative for exact request envelopes and required fields. The shape below shows the central evidence rule; inspect the bundled [example adapter](../examples/adapter) for a runnable protocol implementation.

```json
{
  "concepts": [
    {
      "id": "proposed-id",
      "title": "A concept title",
      "explanation": "An original explanation of the source idea.",
      "evidence": [{"unit_id": "known-unit-id", "quote": "Exact words in that unit"}]
    }
  ]
}
```

The quote must occur exactly in a known teaching unit. Unit IDs and concept IDs must resolve within the current request or workspace. Reconciliation must include each raw concept exactly once and preserve all of its evidence. The planner then assigns or defers every canonical concept. An authored lesson must cover its planned concepts and use only supported question modes when practice is useful; no mode or question quota is imposed. A review result of `revise` blocks publication.

## Assessment holdout

Import question banks or assessments with `--role assessment`. Their text is excluded from extraction, planning, authoring, review requests, and the exported bundle. Use them separately for evaluation. A role flag does not by itself make a good test set: duplicates, paraphrases, or leaked answers in teaching files can still contaminate an evaluation.

## Operational advice

- Keep the adapter stateless where possible. Lamina may run independent extract and author requests concurrently.
- Return complete JSON for each request. Avoid streaming partial objects to standard output.
- Make failures explicit. A bounded retry can recover a transient process error; a persistently invalid response should fail with an actionable message.
- Inspect a small build before scaling to a large corpus. Compare quoted evidence, lesson usefulness, and question quality yourself.
- Keep private documents and credentials out of the adapter source you publish. An exported workbench contains teaching text and should be treated as public if hosted.
