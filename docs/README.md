# Documentation

Install Lamina and configure a model using the [repository README](../README.md). The guides below cover the local app, the CLI and the Python API.

| Task | Guide |
| --- | --- |
| Generate, export or revise cards, guides, podcast scripts and assessments | [Production](production.md) |
| Connect a model, set request and workload limits, configure speech | [Adapters](adapters.md) |
| Import Markdown, text, PDF and PowerPoint files, with optional OCR | [Parsing](parsing.md) |
| Run a custom graph of jobs and reuse selected observations | [Methods](methods.md) |
| Choose the work and context for a reference, podcast or practice exam | [Workflow design](workflow-design.md) |
| Measure workload limits and fact preservation on your model and material | [Calibration](calibration.md) |

## Design

| Document | Contents |
| --- | --- |
| [Architecture](architecture.md) | Source structure, reading and evidence, organization, ownership, evidence comparison, checks, execution, reuse, alternatives considered and the code map |
| [Flow geometry](flow-geometry.md) | Dependency chains, the completion-time bound and how every receipt measures it, halo and batching tradeoffs, context amplification, repair cost and failure accumulation |
| [Capability status](architecture-status.md) | Implemented behavior and remaining limits by area |

## Evaluation and results

| Document | Contents |
| --- | --- |
| [Measurement](measurement.md) | Rules, evaluation layers and the protocol for quality-matched comparisons with other approaches |
| [Benchmarks](benchmarks.md) | Fixture commands and recorded results for grouping, the workflow matrix, scheduling and the method runtime |
| [Live model evaluation](live-model-evaluation.md) | Gemini runs from September 2026, their failures and the fixes they prompted |

## History and paper

| Document | Contents |
| --- | --- |
| [System origins](system-origins.md) | The reference, audio, exam and staged-case systems Lamina grew from, with their recorded workloads and timings |
| [Technical paper](paper/README.md) | PDF, LaTeX source and build instructions |
| [Release notes, v0.12.0](releases/v0.12.0.md) | Card sweep, streaming planner, boundary halo and podcast episodes |
