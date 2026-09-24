# From source structure to a checked artifact

Lamina v0.10 separates the production problem into five decisions:

```text
source structures
    -> bounded source reading or direct source assignments
    -> editorial objects and section ownership
    -> section-local context and execution dependencies
    -> writing, review, repair and artifact checks
```

The route changes with the task. A small source collection can go directly to a writer. A larger one can use parallel readers and bounded hierarchical planning. A caller that already knows the structure can supply assignments. The engine preserves the same source, execution, validation and reuse boundaries around each route.

## 1. Preserve source structure before dividing work

Ingestion stores exact source revisions and ordered units with locations. Markdown paragraphs, lists, tables, code blocks and quotations remain intact. PDF text retains page boundaries. PowerPoint components remain separately citable but share a slide-level structural group. Optional OCR adds a searchable text layer before normal PDF extraction.

These boundaries are evidence supplied by the parser, not claims of semantic independence. A PDF page may continue an argument from the previous page. A slide's notes may qualify its table. When a reader cannot interpret its owned structure without adjacent material, it can request the missing neighboring context with a reason. That context remains unowned.

Without an evaluated reading workload profile, a reader owns one complete parser structure or structural group. A declared profile may combine structures while enforcing complete-request token, item and byte limits. An indivisible structure that does not fit is reported rather than silently truncated.

## 2. Keep source consideration, extraction and selection distinct

For planned production, readers return task-specific ideas by default. Each idea cites source-span identifiers; code resolves them to exact original text. An explicit reusable-reading mode instead compiles a broader source inventory that can be reused across goals. Reuse also preserves any interpretation or omission in that inventory, so it is never automatic.

The planning record distinguishes:

- **considered source units:** structures supplied to readers;
- **cited units:** structures supporting returned ideas;
- **assigned ideas or units:** material owned by a finished section;
- **explicit omissions:** material excluded with a reason;
- **output citations and claim links:** source material named by the finished section.

One count cannot substitute for another. Full structural scan coverage does not establish extraction recall, and a valid output citation does not establish semantic support.

## 3. Plan within bounded requests without losing original objects

Planning cards contain complete idea titles and explanations plus evidence handles. Exact quotation text is removed from repeated planning requests and restored mechanically.

If every card fits in one route request, a model chooses sections, representations, ownership, context and explicit omissions directly. If it does not fit, bounded grouping calls make a smaller outline. A final assignment pass then revisits every original card against that outline. Code requires every original ID to occur exactly once as an assignment or omission.

This second pass matters. A summary group is useful for navigation, but it cannot replace the complete qualifications in the original ideas. Cross-document contradictions, variants and source roles remain visible when ownership is finalized.

For guides and assessments, optional retrieval-target reconciliation occurs before section routing. The model decides whether prompts are equivalent, compatible variants or different contexts. Code keeps every member idea and exact answer evidence. An explicitly different-context relation cannot be merged away. The merge remains a semantic judgment that needs evaluation.

After routing, Lamina measures the complete writing and review inputs for every section. A model can subdivide an oversized section into smaller coherent assignments under a no-omission contract. One indivisible idea, retrieval target or required context set may still be too large.

## 4. Express context according to what crosses the boundary

A section plan uses different relationships for ownership, source context and completed results.

Consider a guide about reliable background jobs:

- The section **“Lease expiry”** owns passages defining a lease and explaining expiry.
- The section **“Fencing stale writes”** owns a fencing-token definition and an incident example.
- “Lease expiry” may receive the fencing definition as **shared evidence** so it can explain that expiry does not prove the first worker stopped. It still does not own that passage.
- A shared relationship can state, with exact evidence, that lease expiry and fencing solve different parts of the failure.
- If a final editor must use the **completed prose** of both sections, it waits for their results in a Method dependency graph. A planned relationship alone does not provide that prose.

Production represents these boundaries with assigned units or ideas, contextual source units, earlier section evidence and scoped shared relationships. Writers also see their own section, immediate neighbors and declared context sections in the route. Unrelated assignments remain outside the request.

Assessment information has another explicit boundary. A blind solver sees the current candidate prompt and only declared earlier candidate prompts. A separate judge sees the blind answer, marking material and cited evidence. Exported candidate and examiner files remain separate. This reduces accidental answer leakage but cannot prove that a stateful external provider forgot earlier calls.

## 5. Execute independent section chains under shared limits

Every production section follows:

```text
write -> review -> optional repair -> recheck
```

One worker ceiling bounds total simultaneous production calls. Reader, writer and reviewer ceilings can reduce activity within a stage. Review begins when an individual section finishes, so unrelated sections do not wait at a global review barrier. A flagged section uses one bounded repair; unresolved findings leave the receipt in `review`.

Reading and bounded planning batches can also run concurrently, but planned production has a real planning barrier: writing starts after extraction, routing and necessary section refinement establish stable ownership. The final shared outline must fit one route request.

The separate Method runtime schedules ready DAG nodes within named resource lanes. A node receives selected task fields and the completed results of its declared dependencies. Failed nodes skip descendants while independent branches may finish. Remaining dependency depth determines priority; it is a structural heuristic, not a model-duration estimate.

## 6. Reuse exact validated requests

The local workspace stores sources, parsed units, search indexes, jobs and receipts in SQLite. A model request's cache identity includes its stage, protocol revision, adapter identity and complete semantic input. Only a validated JSON result becomes a successful cache entry.

During production writing, exact source-revision pointers are replaced with canonical local references while semantic source text, roles, assignments and context stay in the request identity. After validation, Lamina restores references to the selected source revision. This lets equivalent local work be reused without losing current provenance.

Changing a brief rereads sources by default. Explicit reusable reading can preserve matching inventories. A section revision changes that section's request and can reuse unrelated section work. Changes to headings, packing boundaries, source meaning, dependencies, model configuration or relevant context can invalidate more work. No source edit has a constant-cost reuse guarantee.

Concurrent callers for one cache key share a durable job. Renewable leases recover abandoned work, and an owner token fences a superseded worker from committing stale output. Failed or partially validated replies are not published as successful cache entries. Independent completed requests remain available after another request fails.

## 7. Check mechanical invariants and report semantic uncertainty

Code can establish that:

- a source reference resolves to an exact supplied span;
- an idea originated from an owned source unit;
- every planning object has one owner or an explicit omission;
- supplied claim mappings occur in the named output field and link to allowed source text;
- candidate and examiner fields remain structurally separate;
- configured request, workload and resource limits were respected;
- only fully validated results entered the cache.

Model review asks whether a draft lost assigned meaning, changed a condition, introduced an unsupported claim or leaked an answer. Optional document review compares completed neighboring or explicitly related sections. These checks can miss defects. Receipts therefore retain missing claim maps, unperformed comparisons, unresolved findings and `semantic_recall: "unmeasured"`.

Quality experiments follow selected facts through extraction, assignment and finished output. [Live model results](live-model-evaluation.md) record the actual calls, failed trials and output checks. The scripted fixtures isolate scheduling and injected failures.

## Current boundaries

Lamina does not generally interpret figures, reconstruct arbitrary PDF layout or guarantee OCR associations. It does not automatically retrieve a subset of a large imported collection for production. It does not provide live staged oral-case administration, listened audio validation, automatic method discovery or demonstrated learning from retained observations.

The general Method runtime supplies graph execution, lanes, caching and selected observations. It does not automatically inherit Production's source ownership, evidence resolution, workload calibration, output review or export contracts. Older fixed lesson and procedure APIs remain separate package capabilities rather than the current general architecture.

See [Architecture](architecture.md) for module responsibilities, [Production](production.md) for public controls, [Adapters](adapters.md) for model and workload contracts, [Parsing](parsing.md) for source structures, and [Measurement](measurement.md) for evaluation requirements.
