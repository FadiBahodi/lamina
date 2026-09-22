# Method runtime fixture

Run from the repository root:

```bash
.venv/bin/python benchmarks/run_method_example.py
```

The script runs `tests.test_method_runtime`, then calls `method_demo()` ten times in fresh workspaces. Each call creates a guide, edits a deployment note and applies a selected observation. Assertions check cached and executed nodes, dependency context, captured requests, observation family and the changed guide. Passing runs write [`current-runtime.json`](current-runtime.json).

`wall_ms` comes from the runtime's monotonic clock. The report contains all samples, the median and nearest-rank p95: sorted position `ceil(0.95 × n)`, counting from one. With ten samples, p95 is the maximum.

## Limits

The timings cover local fixture execution and SQLite. Model latency, token cost, source understanding, guide quality, learning and delivery require other measurements. The output uses original fixture text and aggregate results, with private sources and credentials excluded.
