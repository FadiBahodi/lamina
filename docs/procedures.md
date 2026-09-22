# Procedures and operating modes

A procedure sets lesson audience, instructions, outputs, and workers in portable JSON. Studio can inspect, edit, import, and export it.

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

The schema allows only these fields: short lowercase IDs, bounded instructions, allowlisted outputs, and limited workers. Unknown fields fail. Executables, credentials, and destinations belong in local commands. Audience, instructions, and outputs enter semantic requests and cache keys. Procedures cannot add stages or plugins.

Every run exports the shared lesson bundle and reader with practice, scenario, and script content where present. Output selection guides authoring and adds artifacts without hiding shared-bundle content. SAMP adds generation, review, and separate exports.

## Hosted Studio

The [public site](https://fadibahodi.github.io/lamina/) is static. It shows the original engineering collection and curated outputs. Selected text files are previewed in the browser; there is no public generation backend. Procedures can be edited and exported. Use the local engine for new collections.

The example is a curated product walkthrough with real evidence links and output artifacts. Its lease diagram is original, not extracted from an image.

## Local Studio

```bash
lamina studio --workspace .lamina --port 8048 \
  --adapter 'python examples/adapter/http_chat.py' \
  --adapter-version my-model-config-v1
```

Without `--adapter`, Studio supports exploration and import. With one, Run builds in the background; failures report errors and successful stages stay cached. Studio binds to loopback with same-origin requests; it is not a multi-user host.

The base engine reads text and Markdown. PDF text extraction needs the optional `pdf` dependency and cannot interpret scanned or graphical content. Assessment sources stay out of generation. A chosen remote adapter may transmit teaching text to its service; a local UI does not imply local inference. Configure the sample adapter with the environment variables in [Adapters](adapters.md). Keep credentials out of procedures and public exports.

## CLI reuse

Save the JSON above as `incident-training.json`, ingest documents, then run:

```bash
lamina ingest ./notes --workspace .lamina
lamina run --procedure incident-training.json --workspace .lamina \
  --adapter 'python examples/adapter/http_chat.py' --output ./site
```

This uses the same procedure-conditioned pipeline as local Studio. [SAMP production](samp.md) covers the short-answer artifact. [Design](design.md) describes proposed claim graphs and hierarchical reconciliation; a procedure does not implement them.
