# Documentation

Install Lamina and configure a model using the [repository README](../README.md). Then use the local app, CLI or Python API with your own source files.

| Need | Guide |
| --- | --- |
| Generate, export or revise an artifact | [Production](production.md) |
| Connect a model and set request limits | [Adapters](adapters.md) |
| Understand parsing, source boundaries and OCR | [Parsing](parsing.md) |
| Choose the work and context for a particular product | [Workflow design](workflow-design.md) |
| Follow scheduling, caching and recovery in code | [Architecture](architecture.md) |
| Define a custom graph of jobs | [Methods](methods.md) |
| Check what is implemented | [Capability status](architecture-status.md) |

For deeper technical detail, see [ownership and context](design.md), [evidence and batching](evidence-execution.md), and [latency and resource limits](flow-geometry.md). [Calibration](calibration.md) and [quality evaluation](quality-evaluation.md) describe how to assess a model on your material; [live-model results](live-model-evaluation.md) and [benchmarks](benchmarks.md) retain measured outcomes and their limits.

[Request grouping comparison](matched-execution.md) reports planned, grouped and direct runs on the same sources.

[System origins](system-origins.md) records the earlier reference, audio and exam systems. [Engineering decisions](engineering-decisions.md) preserves alternatives considered. Older [procedure APIs](procedures.md) and the [technical paper](paper/lamina.tex) remain available; use the current guides above for runtime behavior.
