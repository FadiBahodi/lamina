# Architecture

This page covers the structured lesson builder. The default Projects interface uses [source-aware production](production.md); [architecture status](architecture-status.md) compares both paths with the method runtime.

Lamina builds learning material from local documents and exports a static reader. Python 3.11+ and SQLite handle the pipeline; plain browser assets serve the workbench. Source identity and evidence remain inspectable across semantic stages.

## Data flow

1. **Ingest.** Each document gets a SHA-256 digest, source ID, title, filename, and role. Text becomes ordered units with stable IDs and locators. Repeated writes are idempotent. PDF support extracts text; it does not read images, scanned pages, tables, or layout reliably.
2. **Retrieve.** Search ranks units by lexical and heading signals. A caller-supplied vector lane can add cosine similarity. Scores and contributing lanes are returned; the default has no semantic embeddings.
3. **Extract.** An adapter sees bounded teaching-unit windows and adjacent context, then proposes concepts with exact quotes. Validation rejects unknown units, invented quotes, and held-out assessment evidence.
4. **Reconcile.** A global pass can merge raw concepts. Each raw concept belongs to one canonical concept, and all member evidence survives. Mechanical accounting protects extracted material; the model judges semantic overlap.
5. **Plan.** A global pass assigns canonical concepts to lessons in prerequisite order or defers them with reasons. It accounts for extracted concepts, not undiscovered source ideas.
6. **Author and review.** Lessons contain summaries, source-backed sections, optional task-appropriate practice questions, and speech/pause scripts. A separate adapter review can pass or request revision; unresolved revisions block export. The default reviewer uses the same adapter.
7. **Export.** Validated bundles become JSON and a static workbench, with optional source-linked Markdown or paginated PDF handouts containing practice and answers. Teaching sources and units stay in the bundle. Assessment text stays out of requests and exports. This path does not synthesize or audit audio.

Since v0.2, a validated data-only **procedure** supplies audience, bounded teaching instructions, outputs, and local worker width. Its content-derived revision enters semantic requests and cache keys; planning and authoring also receive its brief. Local Studio serves the curated public example and can accept new sources. It starts background builds only with an adapter configured at startup. Every run exports the base lesson bundle. SAMP adds short-answer generation and review with source-backed points and checked mark totals; an oral case needs an authored scenario. Procedures and outputs are saved together. A SAMP review is another adapter reading.

## Identity, cache, and recovery

Cache keys include stage, canonical request, adapter identity, and prompt/schema revision. Source, adapter, or contract changes require new results; completed stages survive retries. SQLite claims jobs atomically with a lease. Expired claims can be retried after a process disappears, with bounded attempts and visible errors. This is local recovery, not a distributed queue.

Adapter identity must include its model, prompt, or workflow revision. Lamina cannot detect a semantic change hidden behind identical requests and identity. A cache hit records a prior response, not its quality.

## Validation boundaries

| Check | Establishes | Limit |
| --- | --- | --- |
| Source digest and unit locator | Extracted text identity | Cannot establish visual PDF fidelity. |
| Exact quote within a known unit | Quote occurs in an allowed source | Cannot establish clinical or scientific correctness. |
| Reconciled member and evidence accounting | Extracted concepts and evidence survive merges | Cannot establish that distinctions remain useful. |
| Assignment or deferral | Every extracted concept is accounted for | Cannot detect missing concepts. |
| Question-mode requirements | Recall, contrast, and apply prompts are present where required | Cannot establish learning benefit. |
| Review pass | Adapter reviewer accepted its rubric | Not independent expert review. |
| Local self-rating | Learner's reported practice result | Not predicted mastery or exam performance. |

There is no calibrated spaced-repetition scheduler. Local ratings can guide a learner's next choice. Exported material can still be thin, repetitive, or mistaken.

## Extension points

The [adapter protocol](adapters.md) handles interpretation and writing. Ingestion can add document types while retaining source/unit identity. Retrieval can use external vectors alongside lexical search. The static bundle permits alternate readers without moving authoring into the browser.

## Reusable methods in v0.3

The CLI runs [method graphs](methods.md) with selected task fields, dependencies, resource lanes, and cached results. Guide authors in the lesson builder receive the shared lesson route and exact prerequisite evidence, not finished earlier prose. Practice forms follow the material without a universal three-mode quota.
