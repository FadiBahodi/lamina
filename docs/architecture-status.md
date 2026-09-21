# Architecture status

Lamina has two working execution paths. The guide builder reads a source collection and produces a reviewed, source-linked bundle through a fixed sequence of stages. The method runner executes a user-defined graph of JSON jobs. Both use a configured adapter and the same local job store. They do not yet form one source-aware workflow: a method graph cannot replace the guide builder's plan or authoring stages, and generic method jobs do not inherit its evidence checks.

The distinction matters when deciding what to build next. The guide is a concrete application with useful validation. The method runner makes dependencies, context, resource limits, reuse, and observations explicit for other work. The open problem is how to connect those strengths without making one fixed teaching recipe the answer to every source collection.

## From source to guide

[Ingestion](../src/lamina/ingest.py) hashes each file and stores ordered text units with locations. Markdown and plain text are handled directly; PDF support extracts text by page. Each extraction worker sees one unit with short adjacent text from the same source. [The pipeline](../src/lamina/pipeline.py) then reconciles proposed ideas in one global call, makes a global lesson plan, writes lessons in parallel, and asks the adapter to review each lesson. Authors receive their assigned evidence, a shared route, and exact evidence for prerequisite lessons. The shared route is a plan; parallel writers do not see one another's finished prose.

The [validators](../src/lamina/validation.py) check exact quotations, source ownership, concept membership, plan assignment or deferral, and the shape of lessons and reviews. These checks prevent certain lost records and fabricated citations. They cannot establish that parsing recovered a figure, that extraction found every important detail, that two ideas were merged correctly, or that a lesson will teach well. A model review response is recorded and can block export, but it is not an independent quality assessment.

The local browser app runs this fixed guide path through an editable [procedure](procedures.md), which sets audience, instructions, outputs, and worker count. The public example is curated and read-only. Its technical view can inspect the exported bundle and source trail. A procedure changes the guide's brief; it does not replace the execution graph.

## From method to run receipt

A [method file](methods.md) declares bounded jobs, prerequisite IDs, selected task fields, resource lanes, and an expected response shape. [The runner](../src/lamina/method_runtime.py) sends each ready job its instructions and only the completed results of its declared prerequisites. Ready jobs share a worker limit and lane capacities. SQLite caches a job by its semantic request and adapter identity. Changing one branch can leave another branch's result reusable; a failed dependency skips its descendants while unrelated jobs can finish.

Each run stores a receipt with node status, input size, duration, and result digest. A person can also record an observation about a run. An operator may put that observation's ID on a particular method node; the next run retrieves it from the same method family and includes it in that node's context. The observation is selected by the operator and remains attributed as an observation. Lamina neither decides that it applies to a new task nor revises the method on its own. A generic node's response is checked as a JSON object, so the adapter or an added validation step must supply task-specific quality rules.

## Decisions carried over from the original work

The engineering history behind Lamina raised several problems that a job graph alone cannot solve. The table states where each problem is handled today and what is still open. The historical conversations and study material remain private; the public examples use original sources.

| Design problem | Working mechanism | Open decision |
| --- | --- | --- |
| Models need the right physical source packet. | Text units have stable source IDs and neighboring context. | Figure crops, tables, scans, and cross-page meaning need a source-region inventory and a parser or reader that can use them. More prompt text cannot recover missing input. |
| Many workers need a shared understanding of the work. | Guide authors see the planned route and exact prerequisite evidence. Method nodes see declared dependency results. | Compare parallel writing from a shared plan with writing that waits for completed prerequisite prose. Measure duplicated context, coherence, and elapsed time on the same material. |
| Source consideration differs from editorial selection. | The guide accounts for ideas it extracted and assigns or defers each one. | A task must decide which facts deserve teaching, which may be omitted, and why. The right coverage unit varies by job; no single rule should force every source fact into the output. |
| The form should fit the material. | A lesson can have sections, optional questions, a scenario, and a speaking script. | Lists, mechanisms, contrasts, images, calculations, and audio need different treatments. The current bundle and review cannot prove the chosen form works for a learner. |
| A review finding should change the right work. | Cached stages and method dependencies can reuse unaffected results when requests change. A failed guide review blocks export. | There is no typed finding that traces a missed object back to extraction, grouping, planning, or authoring and reopens just the necessary work. |
| Reuse should carry observed experience into later work. | A method node can consume operator-selected observations from the local store. | Selecting a fitting method, testing a proposed revision on new tasks, and promoting it after evidence remain human or agent decisions outside the runtime. |
| Completion has to be visible where the result is used. | The guide exports a static reader and PDF or Markdown; the method runner saves receipts. | A speaking script is not an audited audio file. The browser's active-run registry is in memory, and no cross-device delivery or learner-use check is implemented. |

These are alternative mechanisms to investigate, not a plan to put every feature into one graph. A shared plan can keep independent writers parallel. Completed-prerequisite context may improve callbacks but lengthens a dependent path. An item inventory can expose omissions on a dense reference task while adding needless bookkeeping to a short guide. The choice should follow the source, the requested result, and measured repair cost.

## What would count as progress

An integration should let a new source collection change the work graph or the context sent to a worker, then show an effect in the finished artifact. One useful test is a source with overlapping evidence and a seeded omission. Build the guide, identify the omission in the reader, correct the upstream decision, and show which work reran and which finished pages changed. Run the same task with a fixed route and with a method-driven alternative. Compare the outputs at matched scope and review quality, including the operator's time.

The [measurement protocol](measurement.md) specifies source coverage, content quality, latency, context use, repair work, and a fresh operator's ability to reuse a method. The [systems benchmark](benchmarks.md) currently measures synthetic scheduling and cache behavior. It cannot tell us whether the new architecture makes a better guide.
