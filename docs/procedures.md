# Procedures and operating modes

A procedure is a small portable JSON document that conditions Lamina's supported production pipeline. It declares an audience, authoring instructions, selected outputs, and worker count. You can inspect, edit, import, and export it in Studio, then use it with the local engine.

```json
{
  "schema_version": "1",
  "id": "incident-training",
  "name": "Incident-response practice",
  "description": "Turn operational notes into explanations and progressive decisions.",
  "audience": "Engineers preparing for their first on-call rotation.",
  "instructions": "Teach the causal model before assessment. Preserve failure conditions and exceptions. Use progressive incidents in which new evidence changes the next action. Keep explanations separate from candidate prompts.",
  "outputs": ["study-guide", "samp"],
  "workers": 4
}
```

The schema accepts only these fields. IDs are short lowercase slugs, instructions are bounded, output names come from an allowlist, and worker counts are limited. Unknown fields are rejected. A procedure cannot configure an executable adapter, credentials, or a filesystem destination. Those settings belong to the operator's local command.

The selected audience, instructions, and outputs enter semantic stage requests and their cache keys. Changing them therefore invalidates the affected cached requests. The procedure describes behavior within the installed pipeline; it cannot create arbitrary stages or plugins. Every run exports the shared lesson bundle and reader, including their standard practice, scenario, and script content where present. Selection adds artifacts and guides authoring; it does not isolate or conceal the other content in that shared bundle. SAMP selection adds its own generation and review stages and separate exports.

## Hosted Studio

The [public site](https://fadibahodi.github.io/lamina/) is a static application. It displays the original engineering collection and its curated outputs. Text files selected there are previewed in the browser; the page has no public generation backend. Imported procedure files can be edited and exported. To generate from a new collection, use the local engine.

The example is a product walkthrough, not a hidden call to a model. Its evidence links and output artifacts are real, but its content was curated for the bundled sources. The lease diagram is an original explanatory figure, not an image-extraction result.

## Local Studio

```bash
lamina studio --workspace .lamina --port 8048 \
  --adapter 'python examples/adapter/http_chat.py' \
  --adapter-version my-model-config-v1
```

Start without `--adapter` to explore the interface and import material without generation. With an adapter configured, the Run action starts a real background build. Completed outputs are available from the run. Failed stages report their error, while successful stage results remain cached for the next attempt. The local service binds to loopback and accepts same-origin requests; it is not a multi-user hosted generation service.

Text/Markdown sources are supported by the base engine. PDF extraction requires the optional `pdf` dependency and cannot interpret scanned or graphical content. Source roles matter: assessment sources are held out of generation. A user-selected remote adapter can transmit teaching sources to its configured service; local hosting does not mean local inference.

The sample command adapter uses environment variables described in [Adapters](adapters.md). Do not put credentials into a procedure file or a public export.

## CLI reuse

Save the example JSON as `incident-training.json`, ingest the desired documents, and run:

```bash
lamina ingest ./notes --workspace .lamina
lamina run --procedure incident-training.json --workspace .lamina \
  --adapter 'python examples/adapter/http_chat.py' --output ./site
```

This uses the same procedure-conditioned pipeline as local Studio. See [SAMP production](samp.md) for the separate short-answer artifact and its validation boundaries. See [Design](design.md) for the proposed richer claim graph and hierarchical reconciliation; a procedure does not imply those mechanisms already exist.
