# Architecture

Lamina is a local document-to-learning pipeline with a static reader. Its central invariant is that semantic decisions may change while source identity and evidence remain inspectable. The core uses Python 3.11+ and SQLite; the exported workbench uses plain browser assets.

## Data flow

1. **Ingest.** A document receives a SHA-256 digest, source ID, title, filename, and role. Text is divided into ordered units with stable IDs and locators. Ingestion does not claim to understand the text. Identical writes are idempotent. PDF support extracts text; it does not interpret figures, OCR scanned pages, or establish that layout survived extraction.
2. **Retrieve.** Search ranks known units with lexical and heading signals. An optional caller-supplied vector lane can contribute cosine similarity. The default search does not pretend to provide semantic embeddings. Scores and contributing lanes are returned for inspection.
3. **Extract.** An adapter sees bounded windows of teaching units, including adjacent context. It proposes concepts with exact quoted evidence. Validation rejects unknown units, invented quotes, and evidence from held-out assessment sources. This stage is the narrowest point where source content becomes a proposed interpretation.
4. **Reconcile.** A global pass may merge overlapping raw concepts into a canonical concept. Every raw concept must belong to exactly one canonical concept, and all member evidence must survive. This is semantic consolidation with mechanical conservation checks, not string-similarity deduplication.
5. **Plan.** A global pass sees the canonical concepts and creates lessons in prerequisite order. Every canonical concept must be assigned or explicitly deferred with a reason. This proves accounting over the extracted set; it cannot prove the set is complete.
6. **Author and review.** Each lesson gets a summary, source-backed sections, three kinds of question, and a script with speech/pause segments. A separate review stage can pass or request revision. A revision blocks export until the issue is addressed. The default reviewer is another call through the same adapter, so independence is not implied.
7. **Export.** A validated bundle is written as JSON and as a static workbench. The same bundle can produce a source-linked Markdown handout or a paginated PDF with practice and answer sections. The bundle contains teaching sources and units for traceability. Assessment text is excluded from adapter requests and the exported artifacts. No stage synthesizes or audits audio.

In v0.2, a validated, data-only **procedure** supplies an audience, bounded teaching instructions, selected outputs, and local worker width. Its content-derived revision enters every semantic request and cache key; planning and authoring also receive the brief as explicit guidance. The local Studio serves the same curated example as the public static site, but accepts new sources and starts real background builds only when an adapter was configured at startup. Every run produces the base lesson bundle. Selecting SAMP adds a separate short-answer generation and review pair, with source-bound answer points and checked mark totals; selecting an oral case requires an authored scenario. The procedure and finished outputs are saved together. A SAMP review is another configured-adapter reading, not independent assessment validation.

## Identity, cache, and recovery

The cache key includes stage, canonical request content, adapter identity, and prompt/schema revision. A changed source, adapter, or contract therefore requires a new result. Completed stage results survive retries and can be reused. SQLite claims work atomically with a lease; after a process disappears, an expired claim can be retried. Retry counts are bounded and errors remain visible. This is a local concurrency and crash-recovery mechanism, not a distributed job system.

The adapter must include its model, prompt, or workflow revision in its identity. Otherwise Lamina cannot know that the meaning of a returned result changed while the JSON request stayed the same. A cached result is a record of a prior stage response, not a certification that the response was good.

## Validation boundaries

| Check | Establishes | Does not establish |
| --- | --- | --- |
| Source digest and unit locator | Which extracted text was processed | That PDF extraction understood images or tables |
| Exact quote within a known unit | The quoted bytes occur in the allowed source | That the concept is clinically or scientifically correct |
| Reconciled member and evidence accounting | No extracted concept or its evidence silently disappears in a merge | That the merge preserves every useful distinction |
| Assigned or deferred concept accounting | No extracted concept silently disappears | That all important concepts were extracted |
| Question-mode requirements | Recall, contrast, and apply prompts are present | That those prompts improve learning |
| Review pass | The configured reviewer accepted its stated rubric | Independent expert review or validated assessment |
| Local self-rating | What a learner reported after practice | Predicted mastery or exam performance |

Lamina does not implement a calibrated spaced-repetition scheduler. Local ratings can guide a learner's next choice, but they are not an efficacy measure.

The distinction matters because a polished export can still be thin, repetitive, or mistaken. Lamina makes those failures easier to find; it does not claim to solve them automatically.

## Extension points

The [adapter protocol](adapters.md) is the primary semantic extension point. Ingestion can later add document types while preserving stable source/unit identities. Retrieval can accept external vectors while retaining the lexical baseline. The static bundle format allows alternate readers without moving authoring logic into the browser.
