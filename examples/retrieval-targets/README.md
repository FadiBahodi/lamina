# Retrieval targets: deterministic example

From an installed Lamina environment, run `python examples/retrieval-targets/demo.py`.
The example uses four original engineering notes and a deterministic provider; it
needs no API key. Two notes describing the same ordinary worker handoff become
one retrieval target. A recovery question keeps the same supported answer as a
separate target because its presentation differs. The resulting plan shows both
the canonical target catalog and route; the guide shows the selected prompts and
source-backed answer groups.

This exercises the real production validation and artifact path. It does not
measure model quality, semantic correctness, or learning. With a model adapter,
the `production_targets` stage makes the semantic decisions; code verifies
ownership and exact source support rather than inferring equivalence from words.
