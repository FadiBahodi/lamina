# Building the Lamina technical paper

The source is `lamina.tex` with `references.bib`. From the repository root, build with Tectonic:

```sh
python3 tools/build_paper.py
```

The wrapper writes `output/pdf/lamina-technical-paper.pdf` and the identical Studio asset at `src/lamina/studio/assets/lamina-technical-paper.pdf`. Tectonic must be on `PATH`; its first run may download TeX dependencies.

After an edit, render and inspect every page, extract text to catch broken references, and compare the two PDF hashes. Check implementation claims against release code and tests. The benchmark table reports checked-in sleep-only measurements.
