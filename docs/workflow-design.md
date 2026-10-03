# Designing a workflow with Lamina

Start with the object a person needs to use. A reference guide gives a question one place to live. A podcast script carries a listener through an explanation in a sensible order. A practice exam gives the candidate enough information to answer and gives the examiner a separate marking view. These products can share source handling and execution machinery, but they do not have the same natural unit of work.

Lamina provides that shared machinery: structured source import, exact source references, bounded model requests, parallel execution, saved plans, local revision and receipts. The requested product and source roles determine how to use it.

## Read source structures before dividing the product

Import preserves the structures the parser can identify:

- Markdown headings, paragraphs, lists, tables, quotations and code blocks;
- PowerPoint slide text, tables, shapes and speaker notes, with material from one slide kept together;
- PDF pages as text units, with an explicit warning that extraction does not interpret figures or guarantee reading order.

Without a reading workload policy, a call owns up to eight contiguous units from one heading section, a single PDF page or one slide group. A configured policy can allow several structures from the same source in one call, within the measured request and workload limits. Lists, tables and slide groups stay intact. An oversized structure needs explicit decomposition or a larger allowance.

Each reader also receives a small boundary halo by default: up to six sentence spans from the preceding unit and six from the following unit, reduced when needed to fit the request. If those spans leave a dependency unresolved, the reader can request more context and give a reason. The first request completes the partial neighboring unit; another request steps farther in that direction. These passages remain context, with separate source ownership.

This policy handles local boundaries. A generic rule qualified many pages later, two equivalent questions in different files, or a callback to an earlier episode needs a later planning or reconciliation decision. Optional evidence comparison can request a bounded search of the permitted original source units when extracted ideas leave a question unresolved. It can reopen a unit no reader represented, but its lexical search can still miss relevant material.

## Build a reference around the reader's question

Suppose several documents discuss the same presenting problem. A chapter-per-file layout will repeat shared material and separate conditions that belong in one answer. A useful reference first decides what question the reader is trying to answer.

Historical reference builds used several valid objects:

| Product | Unit of work | Design consequence |
| --- | --- | --- |
| Broad differential atlas | Source-derived list | Preserved variants close to their source; related fragments occupied many separate drills. |
| Reconciled question atlas | Question with a complete answer group | Family editors decided which prompts were equivalent and which conditions justified a variant. |
| Presentation book | Presenting problem with discriminating findings | A diagnosis could recur under several presentations because each comparison taught a different decision. |
| List collection | Self-contained answer list | Procedural sequences, differentials and prompts missing their original case were routed elsewhere or quarantined. |

These products had different scopes and organizing questions; [system origins](system-origins.md) records their sizes.

Lamina's planned guide path reads source structures into source-backed ideas. When retrieval targets are enabled, models group equivalent tasks and compatible variants while retaining answer items and their supporting passages. If the planning request is too large, a grouping tree forms a provisional hierarchy of groups as reads complete, a model designs an outline from the reduced cards, and every original idea is then reassigned against that outline. Transport groups never become final source owners. Writers receive their assigned answer groups, original evidence, declared cross-section context and a local outline containing their neighbors' titles and purposes.

This path does not reproduce every historical reference mechanism. It starts from model-extracted ideas rather than an independently audited inventory of all original question objects. It has no built-in router for sending procedural sequences, treatments and context-dependent prompts to separate products, and PDF export has no atlas-scale bookmark, widget, link and page-inspection acceptance pass. Use a custom method when the work requires family-by-family reconciliation or an explicit routing and quarantine stage.

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

Lamina's current podcast format uses the shared-plan arrangement. It creates a source-grounded script whose sections can be written and reviewed concurrently. A configured speech adapter can synthesize sections as they leave review, then assemble the cached segments into episode and programme WAV files.

The current planner numbers sections into episodes and assigns word targets from the requested episode length. This is less extensive than the historical factory's editorial choice of a natural episode or series shape. Spoken-turn roles, a shared board for distant relationships, turn-level audio repair, transcription comparison, a timed transcript and a phone player remain outside the current engine. WAV checks establish file structure, duration and hashes. Listening, pronunciation, pacing and educational quality require checks on the delivered audio and listener surface.

## Give a practice exam distinct candidate and examiner inputs

A practice exam needs an information boundary. Candidate prompts must not contain the answer key, and later findings must not make an earlier question answerable only in retrospect.

The historical written-case factory used one setter to own the case opening, reveal order, questions and marks. Question-specific marking guides and candidate solves then ran concurrently. The solver for each question saw only the case prefix available at that point. One examiner compared the assembled paper, keys, blind answers and exact evidence. A material finding named the affected question, after which the factory repaired it and ran the solves and judgment again.

Lamina's current assessment path plans source-backed sections and writes candidate and examiner material separately. Each blind solve receives the current candidate section and only the earlier candidate sections declared as required context. A separate judge receives that answer, the marking text and cited source passages. These calls can run concurrently because the engine constructs a separate information-limited request for each section. Use a stateless adapter or isolated provider sessions when the blind boundary matters.

The current path does not install one setter over a whole staged case, repair named questions from blind-solve findings, or repeat the solve-and-judge loop after that repair. Findings remain in examiner and operator records. A live oral encounter also needs requestable findings, examiner-controlled release, reassessment after candidate actions, exhibits, private scoring and participant access. Those require a stateful application.

### Proposed case graph and publication check

A staged oral case needs state that the production engine does not hold. One design represents the case as a graph `G = (V, E)`. A node `v ∈ V` is a named patient state. An edge `e = (v, a, g, Δtₚ, v′) ∈ E` holds an examiner-asserted action `a`, a guard `g`, a simulated patient-time advance `Δtₚ` and a successor `v′`. Each edge carries candidate-safe releases, private interpretation, a next prompt, rubric IDs and source support. Oral time `tₒ` and patient time `tₚ` stay separate.

The examiner decides whether an utterance merits action `a`. Code selects the authored transition and computes the candidate's view `O(v, R, candidate)` from state `v` and the released set `R`; it does not infer treatment quality or biological response from free text. A run log replays decisions, releases, withdrawals, marks and both clocks. Static path tests look for contradictory branches and leaks, and two-person runs test plausibility and pacing.

Publication review would bind the exact case bytes, source-unit and media manifests, reviewer, rubric, verdict and open issues, so a changed branch, answer, source or image makes the pass stale. Lamina's caching and production review do not implement this independent exact-hash gate. Calling the same adapter again is not an independent expert review.

## Keep the product-specific work visible

Reference guides, podcasts and practice exams differ in more than their final file format. They ask readers to recover different objects, make different decisions with the combined evidence and test different delivered surfaces. Current Lamina supplies useful common infrastructure, while some product-specific work remains outside the production engine:

| Product | Current Lamina production | Product-specific work still needed for the fuller historical method |
| --- | --- | --- |
| Reference guide | Structured reading, source-backed ideas, optional retrieval targets, hierarchical planning, reassignment of original ideas, parallel sections and local revision | An audited original-question inventory, explicit routing or quarantine across product types, family-level reconciliation when required, and atlas-scale navigation/render checks |
| Podcast | Shared teaching route, assigned source evidence, concurrent section writing and review, episode and word-target planning, section WAV synthesis during writing | Editorial selection of natural episode/series topology, sparse distant-relationship resolution, spoken-turn and segment repair, transcript comparison, and a tested listener/player journey |
| Practice exam | Separate candidate and examiner text, declared earlier candidate context, blind answers and separate key/evidence judgments | One setter-owned staged case, question-level marks and repairs, repeat solve/judge after a change, and live oral-state behavior when the product is an encounter |
| Reusable method | Operator-declared nodes, completed-result dependencies, resource lanes, receipts and selected same-family observations | Evidence-based selection among methods and a measured result showing that a retained observation improved a later run |

Choose the source handling, execution and recording machinery that fits the requested product. Each product still needs its own editorial decisions and acceptance test.

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

A custom [method](methods.md) declares completed-result dependencies, selected task fields and resource lanes directly. The production planner uses a shared route and declared source context. Give concurrent writers the common decisions they need: terminology, conditions, an agreed example or an exact callback. They can develop separate parts once those decisions are available. A reference to an earlier writer's unplanned wording still needs the completed text.

When a handoff loses a condition that changes the answer, revisit the original source and revise the affected work. For example, a manual may allow eight bar generally but limit an older seal to five. A compact summary that drops the seal condition cannot resolve that difference. Optional evidence comparison can reopen the original addendum even if no reader extracted it. Search results supply evidence; a model must still interpret it.

Changing a declared dependency result changes its consumers' cache identities. Choosing or revising the workflow remains the method author's responsibility. Preserve the goal, source scope, relevant user preferences and reason for the division of work alongside the result. Selected observations can inform later runs; Lamina does not automatically choose a better method from them.

[Flow geometry](flow-geometry.md#context-amplification) defines context amplification, the input tokens sent across requests divided by the distinct accepted source tokens. Record it beside source extraction results, the largest request and output quality. A lower ratio may remove context a reader needed; a higher one may spend time and money without improving the result. Capacity establishes what fits; an evaluated workload policy establishes how much work a stage has shown it can handle.

Compare time and cost against an accepted result under the same source scope and quality criteria. [Live model results](live-model-evaluation.md) record current measurements, [system origins](system-origins.md) keeps the historical timings separate, and the [measurement protocol](measurement.md) describes evaluation.

## Run and retain a workflow

[Production](production.md) gives the CLI and Python calls. All selected factual sources default to authority. Use `source_policy` when some sources are supplements, historical accounts or form examples. Use task-specific reading when the brief should guide source selection; choose reusable reading only when you need a source inventory that can support later briefs. The inventory remains a model interpretation and does not prove complete semantic capture.

Production options select the route and output. A custom method specifies the graph itself. After a run, retain an observation about applicability, representation or review when it can guide a later decision. Selecting that observation for a later run makes its effect inspectable. Storage alone does not show that Lamina learned a better method.
