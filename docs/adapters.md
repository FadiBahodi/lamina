# Command adapters

Lamina handles storage, evidence, scheduling, and export; command adapters interpret and write. An adapter reads JSON on standard input, returns JSON on standard output, logs to standard error, and exits nonzero on failure. Lamina invokes without a shell.

```bash
lamina build --workspace .lamina --adapter 'python my_adapter.py' --output ./site
```

The command adapter's cache identity includes its argument vector, readable script-file hashes, timeout, and configured version. Set `LAMINA_ADAPTER_VERSION` or `--adapter-version` when an endpoint, model, prompt, policy, or other behavior changes without altering those inputs. The executable returns stage JSON, not its own identity. The [HTTP example](../examples/adapter/README.md) uses `LAMINA_API_BASE`, `LAMINA_MODEL`, and `LAMINA_API_KEY`; Lamina does not store their values. Requests default to a 2 MB maximum. Large global reconciliation or planning requests may require a narrower corpus or another adapter design.

## Stages

| Stage | Input | Required output |
| --- | --- | --- |
| `extract` | Teaching unit and bounded neighboring context | Concepts with titles, explanations, and exact quotes |
| `reconcile` | Extracted concepts and evidence | Canonical concepts accounting for every member and its evidence once |
| `plan` | Canonical concepts | Ordered lessons, concept IDs, earlier prerequisites, and explicit deferrals |
| `author` | Planned lesson and concept evidence | Text, source-backed sections, practice questions where useful, and speech/pause script |
| `review` | Authored lesson and checks | `pass` or `revise`, with actionable issues |

Installed JSON schemas define exact envelopes and fields. The evidence shape is:

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

See the runnable [example adapter](../examples/adapter). Quotes must occur exactly in known teaching units; IDs resolve in the request or workspace. Reconciliation preserves every raw concept and its evidence. Planning assigns or defers every canonical concept. Authored lessons cover planned concepts and use supported question modes where useful, without a mode or question quota. `revise` blocks publication.

## Assessment holdout

Import question banks or assessments with `--role assessment`. Their text stays out of extraction, planning, authoring, review, and export. Use them separately for evaluation. Duplicates, paraphrases, or answer leaks in teaching files can still contaminate the test set.

## Operation and limits

Extract and author calls may overlap; keep adapters stateless where possible. Return complete JSON without logs on standard output. Bounded retries can recover process errors; persistent invalid output should fail clearly. Inspect evidence, lessons, and questions before scaling. Keep private documents and credentials out of published adapters; hosted workbenches expose teaching text.
