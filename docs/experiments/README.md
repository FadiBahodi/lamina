# Current method runtime fixture

Run from the repository root:

```bash
.venv/bin/python benchmarks/run_method_example.py
```

The script first runs `tests.test_method_runtime`, then calls `method_demo()` ten times. Each call uses a fresh temporary workspace and executes the incident-guide fixture in three stages: initial guide; edited deployment note; operator-selected observation. It asserts the exact executed/cached node patterns, declared dependency context, captured worker requests, same-family observation selection, and changed final guide before writing [`current-runtime.json`](current-runtime.json). A failed assertion or test prevents a passing report.

`wall_ms` comes from the runtime's monotonic clock receipt. The file reports all ten samples, their median, and nearest-rank p95: sort the samples and take position `ceil(0.95 × n)`, counting from one. With ten samples, p95 is the maximum. These are local fixture and SQLite timings. They do not measure LLM speed, token cost, source understanding, guide quality, learner benefit, or delivery. The output contains original fixture text and aggregate measurements; it contains no private source material or credentials.
