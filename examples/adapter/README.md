# JSON chat command adapter

This executable reads a Lamina stage request from standard input and writes a JSON result to standard output. You configure the model, credentials and `/chat/completions` compatible endpoint.

Set `LAMINA_API_BASE`, `LAMINA_MODEL`, and `LAMINA_API_KEY`, then run:

```sh
lamina build --workspace .lamina --adapter 'python examples/adapter/http_chat.py' --output ./site
```

Change `LAMINA_ADAPTER_VERSION` when the endpoint configuration, model behavior or prompts change to invalidate cached results. Command identity also includes the adapter script's hash. The stage instruction treats documents as reference data and tells the model to ignore embedded operational instructions.

## Response contract

The adapter expects a JSON object in the assistant's response. Adjust it for services with a different response envelope. Lamina checks source IDs, quotations, assignments and lesson structure before caching. Interpretation and teaching quality need content review.

## Thinking budgets by stage

`GeminiProvider(thinking_tokens=1024)` sets the default thinking budget. Mechanical stages get none by default (`thinking_by_stage` = `{"production_review": 0, "production_consistency": 0, "sweep_audit": 0, "assessment_judge": 0}`): a thinking budget adds time to first token on every call there and rarely changes a check's verdict, while composition stages (reading, grouping, outline, writing, repair) keep the default. Pass your own map to change it; the map is part of the configuration identity, so changing it starts a new cache namespace. The adapter already reports admission waits separately from transport time (`transport_metrics()`: `generation_admission_ms`, `count_admission_ms`), so a run can tell queueing on the local semaphore from provider latency.
