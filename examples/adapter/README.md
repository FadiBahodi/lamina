# JSON chat command adapter

This executable reads a Lamina stage request from standard input and writes a JSON result to standard output. You configure the model, credentials and `/chat/completions` compatible endpoint.

Set `LAMINA_API_BASE`, `LAMINA_MODEL`, and `LAMINA_API_KEY`, then run:

```sh
lamina build --workspace .lamina --adapter 'python examples/adapter/http_chat.py' --output ./site
```

Change `LAMINA_ADAPTER_VERSION` when the endpoint configuration, model behavior or prompts change to invalidate cached results. Command identity also includes the adapter script's hash. The stage instruction treats documents as reference data and tells the model to ignore embedded operational instructions.

## Response contract

The adapter expects a JSON object in the assistant's response. Adjust it for services with a different response envelope. Lamina checks source IDs, quotations, assignments and lesson structure before caching. Interpretation and teaching quality need content review.
