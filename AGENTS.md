# Working on Lamina

Read `docs/system-origins.md`, `docs/architecture-status.md` and `docs/production.md` before changing the architecture. They separate the mechanisms that motivated the project from the capabilities implemented here. If a local `docs/active-design-contract.md` exists, read it for the current task's scope and ownership; it is not a public capability claim.

Preserve the distinct source families: document/reference generation, extraction and reconciliation, educational audio, question generation, staged oral cases and reusable methods with retained observations. Do not quietly replace the whole design problem with one of these applications.

Models make semantic and editorial choices. Code controls identity, ownership, provenance, ordering, resources, persistence and explicit contracts. Do not substitute keyword rules, fixed lesson quotas or a fixed worker count for task design. Keep source consideration, editorial selection, finished-output coverage and observed usefulness separate.

Owned source material differs from neighboring context. A shared plan differs from completed prerequisite prose. A candidate artifact differs from an examiner key. A script differs from delivered audio. A passing record check differs from semantic correctness. Preserve these distinctions in code, UI and documentation.

Keep bounded, independent implementation work parallel when the user requests it. Assign file ownership to avoid concurrent edits; use the workspace's current code as the integration contract. Record decisions, unresolved mechanisms, validation results and deployment status in a durable task handoff before a context handoff. Do not reduce the task to the last narrow subtask.

Run meaningful tests for changed behavior. Browser-facing work requires an actual connected journey, not only syntax checks. Package and deployment checks must cover the same revision. Synthetic timing and deterministic fixtures must be labeled; competitive quality claims require a matched evaluation.

Public examples use original material. Do not publish private source documents, conversation dumps, credentials or local research artifacts. The source audit describes general mechanisms without exposing those inputs.
