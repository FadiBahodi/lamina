# Technical brief example

This fictional task combines two sources. `SPEC-2026` describes export-worker behavior; `RUNBOOK-2024` contains an older instruction and an incident observation. The brief must explain the lease rule, preserve the distinction from the old 60-second timeout, and identify what to check before changing a retry timer.

Six nodes perform the work. Two readers extract claims with source IDs and excerpts. A reconciler applies the source policy, keeps the timeout conflict and creates a shared outline with evidence. Two writers use it in parallel: one explains behavior, the other addresses the decision and operational checks. A reviewer receives the outline and drafts, then returns the assembled brief, findings and a `ready` or `revise` verdict.

Each node receives selected task fields and the outputs of its **direct** dependencies. The writers depend on the reconciler, which must carry their source evidence forward. The reviewer depends on the reconciler and both writers.

Validate the method from the repository root:

```sh
lamina method validate examples/methods/technical-brief.json
```

Run it with a configured adapter:

```sh
lamina method run \
  --method examples/methods/technical-brief.json \
  --task examples/methods/technical-brief-task.json \
  --workspace .lamina \
  --adapter 'python ./my_method_adapter.py' \
  --adapter-version my-adapter-v1
```

Replace the adapter command with yours. `examples/adapter/http_chat.py` is compatible when its endpoint and credentials are configured. Model selection, endpoints, credentials and executable paths stay outside the method and task files.

Edit the task file to set sources, audience, decision, scope and source policy. State uncertainty about authority when it is unresolved. The runtime saves a local receipt and reuses node results when task fields, instructions, dependencies and adapter identity match.

## Limits

The reviewer receives the reconciler's evidence and both drafts; the original source text stays outside its input. Check final judgments against the original documents. Important figures, tables or attachments must be extracted and checked before this text-only method can use them.

Nodes must return JSON objects; `expected_shape` describes the requested structure but has partial enforcement. A `revise` verdict requires the user to inspect findings, change the task or method and rerun. Method updates and learning remain user-directed.
