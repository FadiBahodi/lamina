# Document-workflow design

Lamina helps educators, training teams and developers turn source collections into learning material. A reusable procedure controls the audience, authoring instructions, outputs and concurrency.

The product walkthrough follows the work from input to use:

1. Open the sources, their roles and accepted text.
2. Edit the procedure and export it as portable JSON.
3. Read the guide, answer a short-answer management problem, use the examiner sheet or follow the audio script.
4. Follow an answer back to its sources and grouping decisions.

## An engineering example

The public collection explains leases, idempotency and evidence. Two passages distinguish lease expiry from worker termination. Consolidation keeps both passages, and the guide explains the distinction. An incident assessment asks what to do when an old worker finishes after its replacement, then introduces information that changes the decision. The examiner sheet gives marking points, answer limits and evidence.

The collection supports explanation, recall and decisions through different formats. It uses prepared examples and an original illustration:

![A lease expiry and stale completion illustrated](../src/lamina/studio/assets/lease-timeline.svg)

## Procedures and execution

A procedure sets the audience, instructions, outputs and worker width for the supported pipeline. Those settings enter the cache key and travel with the run. The engine supplies the stages and validation rules; the adapter is configured when the local app starts.

The public interface provides examples and a procedure editor. Files selected there are inspected in the browser. Generation runs in the local app, which stores imported material in its workspace and exposes finished artifacts. The service binds to loopback; credentials remain outside browser files. An adapter may send source text to its configured model service.

## Product direction

NotebookLM provides source-based study features. Google documents [flashcards, quizzes and reports](https://workspaceupdates.googleblog.com/2025/09/flashcards-quizzes-reports-notebook-lm-google-education.html), [slide decks, infographics and video overviews](https://blog.google/innovation-and-ai/products/notebooklm/notebooklm-google-io-2026/), and [structured data tables](https://blog.google/innovation-and-ai/models-and-research/google-labs/notebooklm-data-tables/). These pages were checked on 21 September 2026; availability may change.

Lamina's direction is a portable production process that people can modify: editable procedures, a chosen model adapter, intermediate data structures, source checks, local execution and reusable exports. Repeatable source-to-training work is the initial use case. Research synthesis and organizational knowledge work are further applications to evaluate.

## Limits and evaluation

Procedures configure the supported pipeline. They cannot add stage types, wire arbitrary graphs, supply commands or credentials, or choose filesystem destinations. A stage/plugin interface would require versioned inputs, outputs and execution rules. The illustrated example uses prepared content; PDF ingestion does not interpret arbitrary diagrams.

Feature parity, output quality, cost, demand and learning effectiveness require evaluation. Ask an unfamiliar educator to import a collection, adapt a procedure, generate material, find an unsupported or missing answer, correct it and rerun. Measure time to a usable artifact, successful corrections, cost per accepted output and use of intermediate views. Compare with their existing process on the same collection.

See [design alternatives](design.md), [quality evaluation](evaluation.md), and the [systems benchmark](benchmarks.md).
