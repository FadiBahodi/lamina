# Building the Lamina technical paper

The manuscript is `lamina.tex` and its bibliography is `references.bib`. The repository build wrapper uses Tectonic and packages the resulting PDF for the local and hosted Studio. From the repository root, run:

```sh
python3 tools/build_paper.py
```

The final outputs are `output/pdf/lamina-technical-paper.pdf` and `src/lamina/studio/assets/lamina-technical-paper.pdf`. Tectonic must be installed and on `PATH`; its first run may download TeX dependencies. The wrapper exits if compilation fails.

After changing the manuscript, re-run the wrapper, render and inspect every PDF page, extract the text to catch broken references, and confirm the packaged asset matches the output PDF byte for byte. The benchmark table cites checked-in sleep-only measurements. Update implementation-status claims against the release code and tests before distributing a new version; structural fixtures do not establish model output quality.
