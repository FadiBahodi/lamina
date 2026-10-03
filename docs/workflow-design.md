# Choosing and changing the work

Lamina should let an agent take a large job, choose a useful way to divide it, and change that division when the work reveals a better approach. The agent should also be able to use what earlier projects taught it: which source material mattered, why a particular structure worked, and what the user wanted.

The current engine provides source reading, planning, parallel writing, review, caching and custom job graphs. This document describes the design for connecting those capabilities into a method the model can revise during a project. The runtime changes described below are proposed; [Production](production.md) and [Methods](methods.md) document the available interfaces.

## Start with the requested result

Keep the user's goal, audience, source permissions, delivery format and relevant preferences with the project. Identify which sources supply content, which demonstrate style or format, and which must stay held out for evaluation. A request for an answered reference book sets different requirements from a request for an exam that withholds its key. A preference given for one project needs its original context when reused.

The model chooses what to organise around. A source paragraph, a complete answer list, a clinical presentation, an episode and a staged case are all useful units for different jobs. The unit used to read a source need not become a chapter or episode in the result.

| Work | Decisions that shape the method | Finished result to inspect |
| --- | --- | --- |
| Extraction or reconciliation | Which source objects must survive; which are equivalent; which variants change the answer | An inventory whose members, merges and omissions can be traced to the originals |
| Reference book | Whether to organise around questions, presentations or procedures; where related material belongs | Complete answers and useful comparisons, with working contents, indexes and readable pages |
| Podcast | The explanation's order, episode boundaries, shared examples, terminology and callbacks | The spoken lesson, including pronunciation, transitions, transcript and playback |
| Written exam | The whole case, reveal order, questions, marks and information each candidate solve may receive | Candidate and examiner versions, attempted answers and repairs to ambiguous questions |
| Oral encounter | Patient states, requestable findings, consequences of actions and examiner controls | An encounter that can be run with a candidate, including exhibits and private marking |

Earlier projects used all of these forms. A differential atlas preserved source lists; a later atlas reconciled equivalent questions; another book organised material around presentations. Related diagnoses could recur because they answered different questions. The audio and exam systems needed their own teaching and information boundaries. [System origins](system-origins.md) preserves those decisions, sizes and timings.

## A podcast example

Suppose the sources describe a general operating rule and an exception for older equipment. The requested lesson should teach listeners when each applies.

Readers examine different source regions concurrently and keep links to the original passages. One finds the general rule. Another finds a conflicting addendum. A joint reading resolves whether the difference comes from the equipment version, operating conditions or a genuine disagreement.

Before commissioning a full script, the model can try a short explanation or worked example where the choice of teaching structure is uncertain. It might choose to introduce two similar machines that require different decisions. The resulting shared material states the example, the terminology and the condition that changes the answer.

Writers can then explain the rule, develop the example and write the closing questions at the same time. A writer making an exact callback to an earlier sentence waits for that sentence. Other writers can proceed from the agreed example and supporting evidence.

If a writer discovers that a source qualification was lost, it asks a specific question. The answer may require changing the shared example and the sections that use it. If two sections keep needing each other's drafts, the model can combine them. If a section contains unrelated explanations, it can split them. The finished episode is reviewed as a lesson before its delivery is accepted.

The earlier audio factory used parallel readers, a choice of episode structure, targeted checks of distant relationships, a shared teaching route, concurrent section writers, factual review, speech generation and audio checks. Current Lamina carries several of those parts. The new design makes the choice and revision of the method part of the running job.

## Give each worker what its decision needs

Readers keep source structures intact where possible: heading sections, lists, tables, PDF pages and slide groups. Nearby context helps with a list or qualification that crosses a boundary. The existing reader supplies a sentence-span halo and can request additional neighboring material. [Parsing](parsing.md) and [Production](production.md#read-and-organize-the-sources) describe the current limits.

Later work can need information far outside that neighborhood. A comparison may need an addendum no reader extracted. A writer may need the original table behind a short summary. Source access must therefore remain available throughout the job, including passages that never became extracted ideas.

Shared decisions can be ordinary small job results: an agreed definition, a case opening, an example or a resolved exception, with its source support. A worker depends on the decision it uses. Work requiring an earlier draft depends on that completed draft. Keeping decisions separate allows a changed example to affect its users without invalidating every section.

A planner should send enough context to make each decision well. Sending the same complete inventory to every worker increases cost; reducing it to a generic summary can lose the distinction the next worker needs. A targeted question is often the smaller useful exchange. The original passages stay available to resolve it. Targeted retrieval supplements any full-source coverage required by the brief.

## Let work ask questions and propose changes

Extend the existing method response so a worker can return finished outputs, questions that prevent completion, and proposed changes to the work. Control actions need a defined response shape that code validates. An ordinary sentence in a draft cannot change the schedule.

A question identifies the affected work, the missing information, the sources it may consult and what the worker has already established. It can request a passage, interpretation of conflicting evidence, a decision shared with other workers, or clarification from the user. Ask when the answer could change the requested result; record why an unresolved detail does not need to hold up completion.

The scheduler saves the unfinished work and releases the worker slot. A known passage can be fetched directly; interpretation runs as another model job within the same limits. When an answer arrives, the waiting work resumes with that answer and its earlier progress. Independent work continues. An unanswered question remains visible at a budget limit or interruption.

A proposed plan change identifies the plan and job revisions it used, the jobs to split, combine, replace or retire, the new dependencies and the reason. The model maintaining the plan decides whether to accept it against the original goal and current work. Code checks the graph, recorded source assignments and omissions, and source access and resource limits. A proposal based on an outdated revision returns for reconsideration before application.

This supports several ways of working. A simple conversion can finish directly. A large reference can use family editors before a book editor. A case setter can finish the staged scenario before question-specific marking and blind solving. The model chooses the jobs and their relationships; the engine runs them.

## Apply changes without losing useful work

Use the existing scheduler and worker pool. When a result arrives, apply any accepted plan change before releasing its dependent jobs. Stop dispatching retired work, keep unaffected jobs running, and schedule newly ready work within the current capacities.

Record a revision for the plan and for each job definition. A late response from an obsolete job still consumes its worker slot until the call ends, but cannot release current dependents or appear as the latest output. Immediate cancellation of a provider call is optional; retiring its result must work regardless.

Cache identity continues to depend on the instructions, selected inputs, dependency results and model configuration. A global plan revision belongs in the run history, not every cache key. Changed dependencies cause affected work to be reconsidered. Unchanged inputs can reuse completed results. Split or combined jobs retain links to the work they replace so required material cannot disappear during restructuring.

Searches also depend on the collection searched. An earlier finding of no exception becomes stale when a relevant source is added, even if its few citations are unchanged. The existing original-source comparison includes the permitted collection in its cache key; general source questions need the same treatment.

Save questions, accepted plan changes, completed work and reasons as they occur. Resuming should reconstruct the current job from these records and the original user request. A conversation summary can help explain the history, while the saved project determines what still needs doing.

## Review the delivered work

Local review checks a passage or answer against its sources. Whole-work review checks whether the parts serve the requested result: consistent terms, complete answer groups, useful examples, correct reveal order and sensible transitions. A finding names the affected material and explains the change needed. A wording problem can stay local; a misplaced explanation may require revising the plan.

The reference workflows also need decisions about procedural material, treatment lists and prompts whose case context is missing. Route these to a suitable destination or leave them unresolved with a reason. Preserve every source object required by the brief through reconciliation, then inspect the rendered book and its navigation.

For written exams, the setter owns the complete case and marks before question-level work starts. Each blind solve receives only the case information available at that point. A separate examiner compares the questions, keys, attempts and source evidence. Repair affected questions and repeat the relevant solves and judgment. Use isolated model sessions where the candidate/examiner separation matters.

Audio review includes the actual speech and player. A clean script can still produce a missing phrase, poor pronunciation or an awkward transition. Repair the affected script or recording, and reuse unchanged segments. Current Lamina supplies section synthesis and episode WAV files; the fuller method also needs transcription comparison, listening checks and playback review.

### Oral encounters

An oral case needs a stateful application. The existing proposal uses a graph `G = (V, E)`: each node is a patient state. An edge `e = (v, a, g, Δtₚ, v′)` describes a transition from state `v` to `v′` after an action `a` recorded by the examiner. The condition `g` must hold, and `Δtₚ` is the elapsed patient time. Each transition records what becomes visible to the candidate, private interpretation, the next prompt, rubric IDs and source support. Oral time `tₒ` and patient time `tₚ` are separate.

The examiner interprets the candidate's action. Code applies the authored transition and computes the candidate view `O(v, R, candidate)` from state `v` and the set of released findings `R`. The log records decisions, releases, withdrawals, marks and both clocks. Path checks examine contradictions and leaks; two-person runs assess plausibility and pacing.

The proposed publication review records the case version, source and media manifests, reviewer, rubric, verdict and open issues. Changing a branch, answer, source or image makes that review stale. This application and its publication check remain separate implementation work from exported assessments.

## Carry the approach into the next project

Retain the method used, the reasons for its important choices, the delivered version and what happened when it was used. Include the relevant user preferences with their context. Keep direct user feedback, observed defects and the model's explanation of a result distinguishable.

For example, a note that listeners lost track of an undefined term can justify introducing it earlier in a later episode. A request for fully answered material before an exam belongs with that study task. A future practice exam may need a separate answer key instead.

At the next project's design stage, retrieve potentially useful approaches and observations. The model decides which apply and records what it adopts or changes. Existing family names can help find candidates; the requested product and circumstances determine whether an approach fits. Keep inferred preferences labeled with their evidence; direct user instructions take precedence.

Current method observations provide a starting point for this record. They are selected manually and passed to named jobs. Choosing relevant experience, using it to revise the method and relating the outcome to a delivered result are the additional work. Compare the resulting artifact and the editing it needs; including a note in a prompt is only one step.

## Build on the current engine

| Existing part | Extension needed for the design above |
| --- | --- |
| `validate_method()` and `run_method()` | Let a model propose the initial method from the goal, source inventory and applicable experience. Preserve its reasons with the plan. |
| Adjacent reader requests and original-source comparisons | General questions with saved unfinished work, an answer job and resumption. Enforce the control response shape. |
| `DependencyGraph`, the shared pool and section continuations | Apply model-proposed graph changes as results settle; retire obsolete jobs and prevent late results from becoming current. |
| Request-based caching, leases and saved receipts | Persist method revisions and pending questions during execution. Track the current job revision separately from reusable request results. |
| Observations and run history | Find applicable approaches and feedback, preserve preference context, and pass selected experience into the next design. |
| Production review and exports | Supply the product-specific editorial and delivery checks described above. A generic JSON job does not inherit them. |

These changes belong in one complete project path. A useful first integration would create a lesson from conflicting source passages, ask a question that changes a shared decision, revise the affected work, recover through an interruption, and deliver the corrected result while preserving an unaffected section. A second task should use the saved experience to choose an appropriate method of its own.

Read the finished outputs and their source support alongside the run history. Track time to useful output, completion time, cost and human editing. [Flow geometry](flow-geometry.md) explains the scheduling tradeoffs; [Measurement](measurement.md) describes comparisons; [Capability status](architecture-status.md) separates implemented behavior from the additions proposed here.
