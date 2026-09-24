# Lamina documentation

Start with [Production](production.md) to make a guide, podcast script or practice exam. It covers the browser app, CLI and Python API.

| Task | Read |
| --- | --- |
| Connect a model and set request limits | [Adapters](adapters.md) |
| Understand file parsing and OCR | [Parsing](parsing.md) |
| Design the work for a particular output | [Workflow design](workflow-design.md) |
| Understand ownership, shared context and dependencies | [Design](design.md) |
| Follow execution, caching and recovery in the code | [Architecture](architecture.md) |
| Define a custom graph of jobs | [Methods](methods.md) |
| Check model quality at different workloads | [Quality evaluation](quality-evaluation.md) |
| Inspect live model runs and execution measurements | [Model evaluation](live-model-evaluation.md), [Benchmarks](benchmarks.md) |
| See implemented capabilities and remaining work | [Capability reference](architecture-status.md) |

[Product](product.md) gives a worked example from source files to a revised artifact. [System origins](system-origins.md) explains the reference, audio and exam systems that informed Lamina. [Workflow design](workflow-design.md#keep-the-product-specific-work-visible) records which parts of those systems are implemented and which still require their own workflow.

The [method runtime](methods.md) runs custom dependency graphs. Its nodes return JSON; the method author supplies the output checks their application needs. The document production engine adds source ownership, citations, review and exports.

The older [procedures](procedures.md) API uses a fixed lesson format and remains available under the app's advanced tools. The [technical paper](paper/lamina.tex) describes the earlier implementation and its measurements; use the guides above for the v0.11 runtime.

- [Calibration](calibration.md): run controls on your model and save workload profiles.
- [Engineering decisions](engineering-decisions.md): alternatives considered and the mechanisms carried forward.
