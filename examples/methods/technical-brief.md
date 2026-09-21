# Evidence-led technical brief example

This example produces a decision brief from two selected text sources. The task is fictional. `SPEC-2026` states current export-worker behavior; `RUNBOOK-2024` records an older instruction and an incident observation. The brief needs to explain the current lease rule without turning the old 60-second timeout into current policy, then identify what to verify before changing a retry timer.

The method has six nodes. Two readers extract claims independently and keep a source ID and short excerpt with each claim. A reconciler applies the owner-supplied source policy, preserves the timeout conflict, and produces a shared evidence board and outline. Two writers then run in parallel from that same plan: one explains behavior, while the other addresses the decision and operational checks. A reviewer sees the plan and both drafts and returns an assembled brief, issues, and a `ready` or `revise` verdict.

The dependency edges matter. Lamina passes a node only the outputs of its **direct** dependencies and its selected top-level task fields. The two writers do not receive either reader's output directly, so the reconciler is instructed to carry forward the evidence they need. The reviewer depends on the reconciler as well as both writers so it can compare the drafts with the shared evidence board. The source text itself is not in the reviewer's context; a `ready` verdict is therefore a review of propagated evidence, not an independent reread of the originals.

From the repository root, validate the portable method without calling a model:

```sh
lamina method validate examples/methods/technical-brief.json
```

To run it with a configured JSON command adapter, use:

```sh
lamina method run \
  --method examples/methods/technical-brief.json \
  --task examples/methods/technical-brief-task.json \
  --workspace .lamina \
  --adapter 'python ./my_method_adapter.py' \
  --adapter-version my-adapter-v1
```

Replace the adapter command with your own configured adapter. The repository's `examples/adapter/http_chat.py` is one compatible option when its endpoint and credentials are configured outside these files. The method and task contain no model choice, endpoint, credentials, or executable path. A provider response must be a JSON object for each node; `expected_shape` describes the requested structure but is not fully enforced by the current runtime.

The task file is the place to replace the fictional sources, audience, decision, scope boundary, and source policy. Choose those deliberately before a run. If authority between sources is unknown, specify that uncertainty instead of pretending the method can infer it. This text-only example is unsuitable when a figure, table, or attachment holds important evidence until that content has been extracted and checked.

The runtime records a local receipt and can reuse unchanged node results when their selected task fields, instructions, dependencies, and adapter identity still match. It does not automatically rerun a section because the reviewer says `revise`, and it does not automatically learn from a run. An operator should inspect the assembled brief and review findings, revise the task or method if needed, and run again. Validate source references and the final judgment with the actual documents before using the brief to make a decision.
