# Designing a workflow with Lamina

Start with the result a person needs to use. A reference helps someone find and compare answers. A spoken lesson explains ideas in an order a listener can follow. An assessment gives a candidate enough information to make a decision, then gives an examiner a way to mark it. Those uses determine the work you divide among models.

The [website](https://fadibahodi.github.io/lamina/) has a setup for each of these jobs. Select one to see its stages, worker context and output, then choose **Use this setup** to load its brief and settings into Projects. Edit the brief for your audience, add sources, assign their roles and run it in the local app. You can download the same setup for an agent to use from Python.

## A reference organized around the reader's question

Suppose several documents discuss the same presenting problem. A writer assigned to each document will tend to repeat the shared material. A reference becomes easier to use when it gives that question a home and combines its supported answers there.

The historical PDF builds explored several units of organization:

| Product | Unit of work | Design consequence |
| --- | --- | --- |
| Broad differential atlas | Source-derived list | Preserved variants close to their source; related fragments occupied many separate drills. |
| Reconciled question atlas | Question with a complete answer group | Family editors decided which prompts were equivalent and which conditions justified a variant. |
| Presentation book | Presenting problem with discriminating findings | A diagnosis could recur under several presentations because each comparison taught a different decision. |
| List collection | Self-contained answer list | Procedures, differentials and prompts needing their original case were routed to other destinations. |

The broad atlas recorded 1,473 entries and 1,579 pages. A later question atlas had 122 owned questions across 270 pages; a separate presentation book had 205 sheets across 263 pages. These counts describe different scopes and organizing decisions. The historical receipts provide no matched full-build timing comparison.

In Lamina, select **Study guide** and enable **Merge equivalent questions**. Readers return ideas with quotations from their assigned passages. A model groups the ideas into questions and answer items. Code checks that every idea has one owner and that the cited answer text appears in its source. The planner assigns those groups to sections, and writers receive the common route plus their evidence.

Review should examine the complete answer group: its conditions, exceptions and useful variants. A list of three therapies under one condition may become wrong when merged with a list for another condition. Source membership makes the merge traceable; an expert still has to assess the clinical or technical meaning.

For a large collection, the older atlas used local windows, then reconciliation within families, then a whole-book route. This hierarchy spreads reading across workers while bringing broader context into the decisions that need it. Lamina's production engine currently uses one global grouping call. Its custom method runtime can run a declared hierarchy when the task needs a different graph.

## A lesson that several writers can produce together

Educational audio introduced a different dependency. Each section belongs in a teaching sequence, but requiring every writer to wait for all preceding prose lengthens the run and repeatedly sends more text.

The earlier audio factory used one editorial route. Writers received their assigned source evidence, the route, earlier planned ideas and evidence for selected callbacks. This allowed section writing to overlap. Where a transition depends on the words a previous writer actually used, a method can instead make that completed section a prerequisite. The tradeoff is a longer dependency chain and more repeated context.

Lamina's **Spoken lesson** setup uses the shared-plan arrangement. Its output is a script. A speech adapter configured at startup can then produce WAV audio and a synthesis transcript. Uncached local speech calls share a process-safe lane so simultaneous projects can coordinate access to the renderer.

The earlier factory also used transcription to check delivered speech and published it through a phone player. Those delivery components remain specific to that system. Lamina checks WAV structure, duration and hashes; listening and transcription checks can follow the export.

## An assessment with distinct writer, candidate and examiner inputs

In the earlier exam factory, one setter owned the case opening, question order, new findings and marks. Question writers worked in parallel from that plan and their assigned evidence. Candidate solvers attempted each question using only the case prefix available at that point. A judge then compared their answers with the marking guide and source material. Repairs named affected question IDs and triggered another solve and judgment.

This information flow helps find a question whose intended answer depends on an unrevealed finding. It also exposes prompts that ask for two answers while the marking guide expects four, or that leave several interpretations equally reasonable.

Lamina's **Assessment** setup carries teaching sources through a shared plan and parallel writing. The production path exports candidate and examiner files separately. Its blind solve receives the current and preceding candidate sections; the judge receives the answer, marking text and cited evidence. Review findings remain in the examiner report. The adapter should use isolated calls for these roles.

For an oral encounter, the product needs another layer: requestable history, findings released by the examiner, treatment-linked reassessment and a marking sheet usable during conversation. Resus Room supplied that live interface. Lamina's exports can supply static assessment material; a live-session application owns release timing and participant access.

## Choose the context and dependencies deliberately

Each production reader owns a core passage and can inspect neighboring units, called the *halo*. Ownership tells the engine where a new extracted idea belongs. The halo helps a reader follow a list or qualification across a boundary.

Smaller cores create more independent jobs and smaller local decisions, while repeating more neighboring material and instructions. In an archived audio analysis, answer-word exposure ranged from 1.53 times the unique source answer words for one collection to 5.57 times for another. These counts exclude prompts and metadata. They show why context size needs its own measurement alongside runtime.

A useful exposure measure is:

```math
A = \frac{\sum_j \text{source tokens sent in request }j}{\text{distinct accepted source tokens}}
```

Record extraction coverage, the largest request and output quality beside this ratio. A lower ratio can save work but may remove context a reader needed.

For a custom graph, declare a dependency when a job needs a completed result. Share selected task fields when jobs can work from the same plan. Assign a resource lane when jobs compete for the same capacity. In the [method runtime](methods.md), these choices determine the actual requests, run order and cache reuse.

## Where time went

The following figures come from saved production records analyzed in the earlier audio project's 4 September 2026 infrastructure review. The observations describe that system and batch. Lamina's synthetic scheduler measurements appear below in a separate table.

| Historical audio observation | Sample and clock |
| --- | --- |
| 109.06 seconds to saved script, median | 82 rendered V8 parts; measured from engine start, excluding queue wait. |
| 336.65 seconds to ready part, median | The same 82 parts. Parts share setup and contend for local media capacity. |
| 575.54 seconds job service, median | 19 completed course jobs; a job can produce several parts. |
| 5,042.11 seconds queue wait, median | The same 19 jobs in that saved batch. |
| 73.754 seconds planning; 4.122 seconds slowest of eight writers | One recorded part. Call timers include provider-gate waiting. |

The 82-part sample included four parts with recorded model-cache hits. Its median delivered part lasted 18.47 minutes. Subtracting the median script and ready times would not recover a stage duration: jobs and parts share setup and wait on resources differently. The archived review supplies aggregate statistics; the private course texts and production logs remain outside this repository.

These observations led to practical choices: measure queue time from admission, separate script readiness from audio readiness, keep expensive local media within its machine's capacity, and inspect the slowest dependent step before increasing writer count.

Lamina's checked-in [scheduler experiment](../benchmarks/results/production-widths.json) runs 64 reader jobs, two serial global steps and 16 author/review chains through real local persistence. Each handler sleeps for a declared duration and returns a small object.

| Worker capacity | Cold wall time | Peak simultaneous handlers |
| ---: | ---: | ---: |
| 1 | 6.001 s | 1 |
| 4 | 1.690 s | 4 |
| 16 | 0.777 s | 16 |
| 32 | 0.626 s | 30 |

Each width has one recorded run on Darwin arm64, Python 3.14.7 and SQLite 3.53.4. Warm runs made zero handler calls. Model inference, parsing and media rendering belong in a full workflow measurement with their own stage times.

For total service work on resource `r`, `W_r`, capacity `c_r`, and longest dependency chain `D`, completion time has the lower bound:

```math
T \geq \max\left(D,\max_r \frac{W_r}{c_r}\right)
```

The first term explains why a shared planning step can dominate after writers become fast. The second explains why many ready audio jobs still wait for one renderer. Admission delays, retries, serialization and operator review add to elapsed time. A useful comparison measures time and cost to an accepted result under the same source scope and quality criteria; the [measurement protocol](measurement.md) describes that experiment.

## Reuse a setup

Download a setup from the website. Its JSON contains `brief` and `options`, the same fields used by the production engine. Save it as `setup.json`, edit the brief, and ingest your sources:

```sh
lamina ingest ./sources --workspace .lamina
```

From a clone with the [model adapter](../examples/adapter/README.md) configured:

```python
import json
import sys
from pathlib import Path
from lamina.store import Workspace
from lamina.providers import CommandProvider
from lamina.production import plan_production, run_production
from lamina.production_export import export_production

setup = json.loads(Path("setup.json").read_text())
workspace = Workspace(Path(".lamina"))
provider = CommandProvider([sys.executable, "examples/adapter/http_chat.py"])
source_ids = [s["id"] for s in workspace.sources() if s["role"] == "teaching"]
plan = plan_production(workspace, provider, setup["brief"], source_ids,
                       options=setup["options"])
receipt = run_production(workspace, provider, plan)
export_production(receipt, plan, Path("output/my-project"))
```

All selected sources default to authority. Add `source_policy` to the options when some are supplements, historical accounts or form examples; Projects exposes the same choice per file. The optional audio adapter is configured separately through the app or CLI. The Python example above exports the text artifacts.

A setup specifies the goal and production settings. A [custom method](methods.md) specifies the graph itself: jobs, selected task inputs, completed-result dependencies and resource lanes. Use Projects for source-to-document production. Use **Projects → Advanced tools → Custom workflow** to import a method JSON when you need that additional control.

After a run, keep a useful observation about the source, representation or review decision. Select that observation for a later plan or method node when it applies. The next request then includes the note, making its effect available for inspection. Selection remains a decision by the person or agent running the workflow.
