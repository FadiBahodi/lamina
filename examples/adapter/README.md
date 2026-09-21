# JSON chat command adapter

This executable reads one Lamina stage request from standard input and writes one JSON result to standard output. It uses a user-configured `/chat/completions` compatible endpoint. Lamina itself does not select a model or store credentials.

Set `LAMINA_API_BASE`, `LAMINA_MODEL`, and `LAMINA_API_KEY` in your environment, then run:

```sh
lamina build --workspace .lamina --adapter 'python examples/adapter/http_chat.py' --output ./site
```

`LAMINA_ADAPTER_VERSION` can be set to a new value when changing endpoint configuration, model behavior, or adapter prompts. This invalidates prior cached stage results. The adapter script's file hash is also included in the command identity. Documents are untrusted reference data; the stage instruction tells the model to ignore operational instructions embedded in them.

The example expects a JSON object in the assistant's response. A service that returns a different envelope needs a small adapter change. Lamina validates each result's source IDs, exact quotes, assignments, and lesson structure before caching it. Valid structure and grounded quotes still require human review for factual interpretation and teaching quality.
