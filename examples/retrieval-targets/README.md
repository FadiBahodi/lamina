# Question-merging example

Run `python examples/retrieval-targets/demo.py` from an installed Lamina environment. It uses four original engineering notes and fixed responses, with no API key required.

Two notes about the same worker handoff merge into one retrieval target. A recovery question remains distinct because it asks about a different situation, even though the answer is the same. The plan records the targets and assignments; the guide includes selected prompts and cited answer groups.

With a model adapter, `production_targets` chooses the groupings. Code checks ownership and source quotations. This fixture exercises that process; evaluation of model grouping and learning outcomes is covered separately.
