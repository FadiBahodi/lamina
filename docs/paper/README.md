# Lamina technical paper

[Read the technical paper (PDF)](https://fadibahodi.github.io/lamina/assets/lamina-technical-paper.pdf). Its editable source is [`lamina.tex`](lamina.tex), with the bibliography in [`references.bib`](references.bib).

The paper defines source policy, owned reading windows, task-shaped representations, context assembly, dependency and resource edges, cache identity and repair, and connects them to the historical reference, audio and staged-case workflows described in [system origins](../system-origins.md). Its current-implementation table summarizes the production engine and method runtime; [capability status](../architecture-status.md) is the maintained record of implemented behavior.

## Build

From the repository root, build with Tectonic:

```sh
python3 tools/build_paper.py
```

The wrapper writes `output/pdf/lamina-technical-paper.pdf` and the identical website asset at `src/lamina/site/assets/lamina-technical-paper.pdf`. Tectonic must be on `PATH`; its first run may download TeX dependencies. A standard TeX installation also builds the source with `latexmk -pdf lamina.tex` from this directory.

After an edit, render and inspect every page, extract text to catch broken references, and compare the two PDF hashes. Check implementation claims against release code and tests. The scheduling paragraph cites the checked-in finite-capacity fixture in `benchmarks/results/execution-scaling.json`.
