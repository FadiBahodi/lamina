# Designing a workflow with Lamina

Start with the object a person needs to use. A reference guide gives a question one place to live. A podcast script carries a listener through an explanation in a sensible order. A practice exam gives the candidate enough information to answer and gives the examiner a separate marking view. These products can share source handling and execution machinery, but they do not have the same natural unit of work.

Lamina provides that shared machinery: structured source import, exact source references, bounded model requests, parallel execution, saved plans, local revision and receipts. The goal and source roles still determine the production design. A setup is an editable starting point, not a universal workflow.

## Read source structures before dividing the product

Current Lamina does not divide every file into fixed passages with a fixed neighboring halo. Import preserves the structures the parser can identify:

- Markdown headings, paragraphs, lists, tables, quotations and code blocks;
- PowerPoint slide text, tables, shapes and speaker notes, with material from one slide kept together;
- PDF pages as text units, with an explicit warning that extraction does not interpret figures or guarantee reading order.

Without a reading workload policy, one call groups up to eight adjacent prose blocks from the same section. PDF pages and slide groups remain indivisible. When a configured policy permits several structures in one call, Lamina packs complete structures within the measured request and workload limits. It does not cut a list, table or slide group merely to fill the available context.

No neighboring source structure is sent by default. A reader that cannot interpret its owned material at a boundary can request the structure immediately before or after it and state the missing dependency. Lamina adds the complete neighboring structure and records that request. The added material supplies context; it does not become that reader's source ownership.

This policy handles local boundaries. It does not find every distant relationship. A generic rule qualified many pages later, two equivalent questions in different files, or a callback to an earlier lesson needs a later planning or reconciliation decision over the relevant source-backed ideas.

## Build a reference around the reader's question

Suppose several documents discuss the same presenting problem. A chapter-per-file layout will repeat shared material and separate conditions that belong in one answer. A useful reference first decides what question the reader is trying to answer.

Historical reference builds used several valid objects:

| Product | Unit of work | Design consequence |
| --- | --- | --- |
| Broad differential atlas | Source-derived list | Preserved variants close to their source; related fragments occupied many separate drills. |
| Reconciled question atlas | Question with a complete answer group | Family editors decided which prompts were equivalent and which conditions justified a variant. |
| Presentation book | Presenting problem with discriminating findings | A diagnosis could recur under several presentations because each comparison taught a different decision. |
| List collection | Self-contained answer list | Procedures, differentials and prompts missing their original case were routed elsewhere or quarantined. |

The broad atlas recorded 1,473 entries across 1,579 pages. A later direct-question atlas recorded 122 owned questions across 270 pages. A separate presentation book contained 205 sheets across 263 pages. These products had different scopes and organizing questions. Their page counts do not establish relative quality or speed, and the saved receipts do not provide a matched cold-build comparison.

Lamina's planned guide path reads source structures into source-backed ideas. When retrieval targets are enabled, models group equivalent tasks and compatible variants while retaining answer items and their supporting passages. If the planning request is too large, Lamina builds a provisional hierarchy of groups, designs an outline from the reduced cards, and then reassigns every original idea against that outline. Transport groups never become final source owners. Writers receive their assigned answer groups, original evidence, the common route and only the declared cross-section context.

This path does not reproduce every historical reference mechanism. It starts from model-extracted ideas rather than an independently audited inventory of all original question objects. It has no built-in router for sending procedures, treatments and context-dependent prompts to separate products, and PDF export has no atlas-scale bookmark, widget, link and page-inspection acceptance pass. Use a custom method when the work requires family-by-family reconciliation or an explicit routing and quarantine stage.

Review a complete answer group, including its conditions, exceptions and meaningful variants. Two lists can share most of their words while applying to different situations. Exact source membership makes the decision inspectable; it does not make the merge semantically correct.

## Plan a podcast before dividing the script

A podcast has a dependency that an ordinary reference does not: each section belongs in a route the listener must be able to follow without scanning the whole artifact. The historical audio factory therefore separated these decisions:

1. local readers recovered idea families from ordered source material;
2. one topology pass chose the natural episode or series shape;
3. a sparse pass resolved only distant relationships and conflicts that several sections needed;
4. one route assigned teaching jobs, objectives, useful callbacks and evidence;
5. section writers worked concurrently from that route, their assigned evidence, earlier planned ideas and selected callback evidence;
6. local factual checks and targeted turn repairs preceded speech, transcription checks and phone publication.

The writers did not need the exact preceding prose when a shared route was sufficient. If a transition, summary or later decision depends on what an earlier writer actually produced, the later job must instead depend on that completed result. That dependency lengthens the critical path and should be declared only when the finished text matters.

Lamina's current podcast format uses the shared-plan arrangement. It creates a source-grounded script whose sections can be written and reviewed concurrently. A configured speech adapter can synthesize the finished script as WAV audio through a capacity-limited resource lane.

The current engine does not implement the historical episode topology, spoken-turn roles, sparse relationship board, turn-level audio repair, transcription comparison, timed transcript or phone player. Its WAV checks establish file structure, duration and hashes. Listening, pronunciation, pacing and educational quality require checks on the delivered audio and listener surface.

## Give a practice exam distinct candidate and examiner inputs

A practice exam needs an information boundary. Candidate prompts must not contain the answer key, and later findings must not make an earlier question answerable only in retrospect.

The historical written-case factory used one setter to own the case opening, reveal order, questions and marks. Question-specific marking guides and candidate solves then ran concurrently. The solver for each question saw only the case prefix available at that point. One examiner compared the assembled paper, keys, blind answers and exact evidence. A material finding named the affected question, after which the factory repaired it and ran the solves and judgment again.

Lamina's current assessment path plans source-backed sections and writes candidate and examiner material separately. Each blind solve receives the current candidate section and only the earlier candidate sections declared as required context. A separate judge receives that answer, the marking text and cited source passages. These calls can run concurrently because the engine constructs a separate information-limited request for each section. Use a stateless adapter or isolated provider sessions when the blind boundary matters.

The current path does not install one setter over a whole staged case, repair named questions from blind-solve findings, or repeat the solve-and-judge loop after that repair. Findings remain in examiner and operator records. A live oral encounter needs additional behavior—requestable findings, examiner-controlled release, action-linked reassessment, exhibits, private scoring and participant access—which belongs in a stateful application rather than a static export.

## Keep the product-specific work visible

Reference guides, podcasts and practice exams differ in more than their final file format. They ask readers to recover different objects, make different decisions with the combined evidence and test different delivered surfaces. Current Lamina supplies useful common infrastructure, while some product-specific work remains outside the production engine:

| Product | Current Lamina production | Product-specific work still needed for the fuller historical method |
| --- | --- | --- |
| Reference guide | Structured reading, source-backed ideas, optional retrieval targets, hierarchical planning, reassignment of original ideas, parallel sections and local revision | An audited original-question inventory, explicit routing or quarantine across product types, family-level reconciliation when required, and atlas-scale navigation/render checks |
| Podcast | Shared teaching route, assigned source evidence, concurrent section writing and review, optional whole-script WAV synthesis | Natural episode/series topology, sparse distant-relationship resolution, spoken-turn and segment repair, transcript comparison, and a tested listener/player journey |
| Practice exam | Separate candidate and examiner text, declared earlier candidate context, blind answers and separate key/evidence judgments | One setter-owned staged case, question-level marks and repairs, repeat solve/judge after a change, and live oral-state behavior when the product is an encounter |
| Reusable method | Operator-declared nodes, completed-result dependencies, resource lanes, receipts and selected same-family observations | Evidence-based selection among methods and a measured result showing that a retained observation improved a later run |

These are separate extension paths. A reference router does not belong in every podcast, and a case setter does not belong in every guide. Reuse the source, execution and receipt machinery where it fits; keep each product's meaning and acceptance test explicit.

## Choose plan sharing and completed-result dependencies deliberately

Two jobs can run together when they need the same finished plan and different owned evidence. A later job must wait when it needs an earlier job's actual result. These are different kinds of context:

| Context | Use it when | Cost |
| --- | --- | --- |
| Owned source structure | A reader must interpret one intact list, table, slide or page | Local model work |
| Requested neighboring structure | A local boundary hides a necessary qualifier or continuation | Repeated adjacent source context |
| Shared route | Writers need the same intended order, ownership and requirements | One global planning dependency |
| Selected earlier evidence | A writer needs a planned callback or common definition | Small repeated source context |
| Completed prior result | Exact earlier wording or output changes the later job | Longer dependency chain and more context |
| Resource lane | Jobs can be ready together but compete for one renderer or constrained service | Queue time without an informational dependency |

A custom [method](methods.md) declares completed-result dependencies, selected task fields and resource lanes directly. The production planner uses a shared route and declared source context. Do not make every writer wait for prior prose to improve continuity by assumption; do not let parallel writers proceed without the route and evidence needed to remain coherent.

For source exposure, a useful diagnostic is:

```math
A = \frac{\sum_j \text{source tokens sent in request }j}{\text{distinct accepted source tokens}}
```

Record source extraction results, the largest request, repeated context and output quality beside this ratio. A lower ratio may remove context a reader needed. A higher ratio may spend time and money without improving the result. Capacity establishes what fits; an evaluated workload policy establishes how much work a stage has shown it can handle.

## Keep historical and current timing evidence separate

The following observations come from saved records in the earlier audio system's 4 September 2026 infrastructure review. They do not measure current Lamina performance.

| Historical audio observation | Sample and clock |
| --- | --- |
| 109.06 seconds to saved script, median | 82 rendered audio parts; measured from engine start and excluding queue wait. |
| 336.65 seconds to ready part, median | The same 82 parts; parts shared setup and contended for local media capacity. |
| 575.54 seconds job service, median | 19 completed course jobs; one job could produce several parts. |
| 5,042.11 seconds queue wait, median | The same 19 jobs in that saved batch. |
| 73.754 seconds planning; 4.122 seconds for the slowest of eight writers | One recorded part; call timers included provider-gate waiting. |

The 82-part sample included four recorded model-cache hits and had a median delivered duration of 18.47 minutes. Subtracting the median script and ready times does not recover one stage duration because jobs and parts shared setup and waited on different resources. The private source text and production logs are outside this repository.

Lamina uses scripted fixtures to check scheduling, recovery and cache reuse, and [live model runs](live-model-evaluation.md) to measure actual requests and failures. The 0.10 fixture deliberately returns valid cited records while dropping a required fact; the quality evaluator catches the omission. The live experiments also test the evaluator itself against real PDF text.

For total service work on resource `r`, `W_r`, capacity `c_r`, and longest dependency chain `D`, completion time has the lower bound:

```math
T \geq \max\left(D,\max_r \frac{W_r}{c_r}\right)
```

The first term explains why a route, setter or other global decision can dominate after local workers become fast. The second explains why many ready audio jobs still wait for one renderer. Admission delay, retries, provider limits and operator review add to elapsed time. Compare workflows by time and cost to an accepted result under the same source scope and quality criteria; the [measurement protocol](measurement.md) describes that experiment.

## Run and retain a workflow

Ingest the source files and assign their roles before production:

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

All selected factual sources default to authority. Use `source_policy` when some sources are supplements, historical accounts or form examples. Use task-specific reading when the brief should guide source selection; choose reusable reading only when you need a source inventory that can support later briefs. The inventory remains a model interpretation and does not prove complete semantic capture.

A setup specifies the goal and production options. A custom method specifies the graph itself. After a run, retain a useful observation about applicability, representation or review only when it can guide a later decision. Selecting that observation for a later run makes its effect inspectable. Storage alone does not show that Lamina learned a better method.
