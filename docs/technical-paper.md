# Lamina technical paper

[Read the technical paper (PDF)](https://fadibahodi.github.io/lamina/assets/lamina-technical-paper.pdf). Its editable source is [LaTeX](paper/lamina.tex), with a [bibliography](paper/references.bib) and [build instructions](paper/BUILD.md).

The paper describes source policy, owned reading windows, task-specific representations, worker context, dependencies, resource limits, caching and repair. It connects those choices to historical differential-reference, spoken-lesson and staged-case workflows. A fictional engineering brief follows a current rule and a conflicting historical observation through the proposed method.

The historical audio section reports archived ROUNDS timings with their actual units: 82 rendered parts for script and ready-file times, and 19 completed jobs for service and queue wait. These observations explain resource and dependency choices; they are not Lamina performance results. The public [workflow design account](workflow-design.md) describes the archival method and the decisions without private source content.

The current release has a source-aware production engine in the CLI and Projects interface, an earlier fixed guide builder, and a separate method runtime. The paper identifies working source policy, retrieval targets, assessment checks and local PCM rendering, while visual interpretation, upstream repair and live case behavior remain open. Its scheduler benchmark uses synthetic sleeps; its engine fixture uses deterministic responses. The [measurement protocol](measurement.md) sets out a new-source, quality-matched comparison.
