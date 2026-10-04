# Where a production run spends its time

A run takes longer when it repeats work, waits for a prerequisite, or queues for a busy resource. Adding workers helps only the work that can proceed independently. This note describes the current routes, then uses small calculations to explain their tradeoffs. None of the calculations is a Lamina performance measurement. Each is either derived from its definitions, and so holds whenever the definitions apply, or depends on an assumption that a run may violate:

| Calculation | Basis |
| --- | --- |
| Completion-time lower bound `max(D, max_r W_r/c_r)` | Derived from the definitions of service work, capacity and dependency chain |
| Simplified bound `max(W/P, d)·t` | Assumes identical call durations and one worker pool |
| Section chains versus stage barriers | Derived for fixed durations and unlimited capacity; finite pools need measurement |
| Planned-route chain of `5 + L` calls | Derived from the route's dependencies, assuming no repair, extension or subdivision |
| Halo multiplier `H` and context amplification `A` | Definitions; the halo example assumes equal unit sizes |
| Probability that some window needs a follow-up | Assumes independent, identical per-window probabilities |
| Batch-size table | Assumed toy timings and unchanged quality |
| Prefix-cache saving `M·P·h·(c_u − c_c)` | Derived cost expression; `h` and prices are assumed inputs |
| Repair cost `R(o)` | Accounting definition over declared dependencies |
| Run success `(1 − q)^n` | Assumes independent, identical failures |

## Follow the dependencies

The card sweep gives each reader a source window and asks it to write finished cards. After the reads finish, local similarity suppresses near-duplicates. A sample of windows then receives a source audit. With no retries or reading extensions, an audited card has two model calls in its dependency chain: reading and audit. If there are `N_r` reader windows and `N_a` audited windows, the model-call count is `N_r + N_a`. The default audit rate is one quarter. Deduplication and publication still take time even though they make no generation calls.

A planned guide, podcast or assessment needs more shared decisions:

| Work | What it waits for | What can overlap |
| --- | --- | --- |
| Read source windows | A measured request and available reader capacity | Other reads and preparation of later requests |
| Group ideas | Enough completed reads, in source order, to fill a group | Remaining reads and independent groups |
| Build higher grouping levels | A full batch of lower-level summaries, once the arrived summaries exceed the outline allowance | Other branches of the grouping tree |
| Choose the outline | The material needed for the complete outline | Work outside this plan |
| Assign original ideas | The outline | Independent assignment batches |
| Subdivide an oversized section | Its assignment and measured writing/review requests | Other independent subdivisions |
| Write, review, repair and recheck | The preceding result for that section | Other section chains |
| Check relationships across sections | The completed sections being compared | Checks on other pairs |
| Synthesize speech | A section leaving review and a free speech slot | Writing, review and other permitted speech work |

The optional evidence-comparison and retrieval-target paths collect readings before their whole-inventory work. The default planned path streams reading into grouping. Source-order delivery can still wait on an earlier slow read even when a later one has finished. The outline and assignment remain shared decisions; streaming reduces waiting without removing those dependencies.

The default production worker limit and bundled Gemini adapter concurrency are both 16. Stage and provider limits can reduce that number. Speech uses its own adapter limit. These are operator settings, not estimates of the best concurrency for every workload.

## Separate total work from the longest chain

Let `W_r` be total service time needed on resource `r`, `c_r` its capacity, and `D` the duration of the longest dependency chain. Any schedule has the lower bound:

```math
T \geq \max\left(D,\max_r \frac{W_r}{c_r}\right)
```

For identical calls of duration `t`, one pool of `P` workers, `W` total calls and a longest chain of `d` calls, this simplifies to:

```math
T \geq \max(W/P,d)\,t.
```

The first bound is derived: no schedule finishes before its longest chain, and no resource delivers more than `c_r` units of service per unit time. The second assumes every call takes the same time `t`. Real calls differ in length and compete for provider admission, network connections and output capacity. Retries and human review add more work. Use measured service durations for the first formula whenever possible. Jobs that need several resources at once need further scheduling analysis.

Independent section chains let a section's review start when its own draft is ready; a stage barrier makes every review wait for the slowest draft. For fixed nonnegative durations `τ[i,s]` of section `i` in stage `s`:

```math
\max_i \sum_s \tau_{i,s} \leq \sum_s \max_i \tau_{i,s}.
```

The inequality is derived (each section's total is at most the sum of the stage maxima), but it describes unlimited capacity. With a finite shared pool, changing priority changes which work gets a worker, and provider rate limits, service-time variation, retries and cancellation also affect the schedule. The [scheduling fixture](benchmarks.md#scheduling-fixtures) compares both policies under the same capacity, work and failures and includes a constructed case where barriers finish first.

Ordering ready work by estimated size would borrow from longest-processing-time-first scheduling, whose classical bound assumes known processing times on identical workers. Request bytes estimate only one component of a model call; output generation, reasoning and provider queues can dominate. The classical bound does not transfer to byte counts, so size-based priority needs a matched comparison. Removing a call can save both its own work and the time spent waiting for it, provided the output still meets the same acceptance conditions.

For a planned route with `L` grouping levels, the simplest chain is reading, `L` groups, outline, assignment, writing and review: `5 + L` calls. Context extensions, subdivision and repair lengthen some paths. Streaming allows different branches to overlap; it cannot start a group before the material it needs exists. A two-call card route and a longer document route also produce different objects. Comparing them fairly requires a common requested result and a quality assessment.

Earlier versions of this note estimated call duration from a complete run's elapsed time and call count. Parallel calls make that inference invalid. The [live-model results](live-model-evaluation.md) record actual experiments; stage-level receipts are the appropriate input to a latency model.

## Measured in every receipt

The bound above is computed for every plan and receipt from the run's own call records (`geometry` in `plan.json` and `report.json`; `src/lamina/geometry.py`). Each tracked call records its start and end, its model attempts, and the calls it declared it waited for. The planner declares the reads that fed each grouping batch, the batches that fed the outline and the outline each assignment batch waited for; a section's review follows its write, a repair follows its review, a section's first write follows the last planning call, a sampled audit follows its window's read, and a whole-document check follows every section call. Those stage rules are written in `implied_after` so they can be disputed, and a predecessor counts only if it ended before its dependent started.

From the graph the receipt reports `model_ms` (`W`), `critical_path_ms` and `critical_path_depth` (`D` and its length in calls, with the chain itself), `bound_ms = max(W/P, D)` with `bound_binding` naming which term, `wall_ms` and `wall_over_bound`, `peak_in_flight` and `mean_in_flight`, `serial_fraction` (the share of the span with at most one call running), and `amplification_bytes` (request bytes sent, instructions included, over distinct source bytes). A `timing` field says `measured` for a live adapter and labels a fixture's synthetic latency. Exported documents end with the timeline and these numbers; `lamina demo --synthetic-latency` produces one from the bundled fixture.

The receipt's `wall_over_bound` is the quantity to watch on a live run. Near 1.0 the schedule is as good as its dependency structure allows and only the chain or the worker limit can be changed; well above 1.0 the time went somewhere the bound does not count: provider admission, token counting, cache writes, preparation, or a worker limit that the provider did not honour.

## Why a small halo can help

A source boundary can split a list or hide the condition that qualifies a rule. Supplying nearby text may let a reader finish in one call. With equally sized core units `c` and neighboring units `h` on each side, the input multiplier is:

```math
H = \frac{c+2h}{c}.
```

For example, 18 core units and two neighbors on each side give `H ≈ 1.22`; two core pages with one neighboring page on each side give `H = 2`. The formula assumes equally sized units. Real structures vary in length, so bytes or tokens give a better measurement than page count, and the reader-stage source exposure defined below is the measured form of `H`.

Lamina's default halo uses sentence spans. Six spans on each side at an assumed 25 tokens per sentence would add about 300 tokens. The actual halo shrinks to fit the reader's request allowance. A reader can ask to complete a neighboring unit when this partial view is insufficient.

A halo is a tradeoff. Extra input can increase call time and reduce how many owned units fit. It also causes changes near a boundary to invalidate neighboring reads. Measure how often it prevents a follow-up and whether it preserves the needed distinctions. It cannot guarantee a faster run, and local context cannot expose every qualification elsewhere in the source collection.

Under the narrow assumption that each of `N_r` windows independently needs one extra call with probability `p`, the chance that at least one window needs a follow-up is:

```math
1-(1-p)^{N_r}.
```

For `p = 0.10` and `N_r = 80`, that is about 99.98%. This explains why a rare per-window dependency can occur in most large runs. It does not establish its duration or prove that a larger halo resolves it.

## Context amplification

Context amplification measures how much input a run sends for each token of accepted source text:

```math
A = \frac{\sum_j \text{input tokens in request } j}{\text{tokens of distinct accepted source text}}.
```

`A` is an accounting definition. Repeated instructions, summaries, halos, shared context and retries all enter the numerator. Counting only source text in the numerator gives source exposure; for readers with equal units and a whole-unit halo it equals `H`. Report `A` by stage and overall, beside the largest request, source regions never sent in usable form, and accepted output quality. Some repetition prevents boundary errors, so a lower `A` is better only when quality holds; a higher `A` may spend time and money without improving the result.

## Batch size changes waiting as well as cost

Grouping compatible tasks in one request can reduce repeated instructions and connection overhead. It also puts their outputs into one generation stream and gives the model more material to distinguish.

Consider a toy workload with twelve outputs, four request slots, two seconds of startup per request and three seconds of serial generation per output. Assume grouping leaves quality unchanged and there are no other bottlenecks. For batch size `g` dividing twelve:

```math
T(g)=\left\lceil\frac{12/g}{4}\right\rceil(2+3g),
\qquad
W(g)=\frac{12}{g}(2+3g).
```

| Outputs per request | Requests | Elapsed time | Worker-seconds |
| ---: | ---: | ---: | ---: |
| 1 | 12 | 15 | 60 |
| 3 | 4 | 11 | 44 |
| 6 | 2 | 20 | 40 |
| 12 | 1 | 38 | 38 |

The largest batch uses the least total work in this example, while batches of three finish first. A live model may change both latency and answer quality when tasks share a request. Test tasks alone, with compatible peers, with misleading peers and in a different order before choosing a default.

If several tasks use overlapping evidence sets `E_i`, the potential source savings are:

```math
\sum_i |E_i|-\left|\bigcup_i E_i\right|.
```

Those savings require a transport that serializes each shared passage once and records which tasks may use it. Lamina's grouped section requests retain separate task inputs, so this evidence-union saving is not currently guaranteed. Local source aliases protect references; they cannot prove that one task's text had no effect on another task's reasoning.

Repeated prefixes are a separate saving. Let `M` eligible calls each share a prefix of `P` tokens, with cache-hit fraction `h`, uncached token price `c_u` and cached token price `c_c`. The possible input-cost reduction is:

```math
M\,P\,h\,(c_u-c_c).
```

The expression is derived; `h` and both prices are assumptions until the provider reports them. The logical input still contains the prefix. Its size, exact encoding, provider behavior and observed cache hits determine whether savings occur, and output cost and live latency need separate measurement.

The [recorded grouping fixture](benchmarks.md#request-grouping-comparison) reduced serialized request bytes by 21.9%, with slightly higher local elapsed time in a test without network latency. That measures the fixture's request packing. It does not establish a live-model speedup.

## Release results when their own work is complete

A request can contain two section drafts and return one valid draft and one invalid draft. The valid section's reviewer has everything it needs. Making it wait for the other section's correction adds a dependency that the product never required.

After a grouped response arrives and its rows are validated, Lamina records accepted section results as completed work and returns failed rows or request splits to the existing scheduler. It does not stream partial provider JSON. That keeps the shared worker limit meaningful and lets each accepted section advance. The relevant regression test blocks one sibling retry and observes whether another section reaches review before that retry is released. Timing a fast fixture is less informative than proving that event order.

Source recovery has a related distinction. Looking through already extracted ideas can recover an overlooked relationship between them. It cannot recover a qualification that every reader omitted. Optional evidence-comparison follow-ups can search full permitted original source units, including units with no extracted ideas. Search uses local lexical similarity and exact unit IDs or headings. Each comparison permits up to three queries, each returning at most one new original unit, within the existing three-comparison limit. Records show the source snapshot, searches, reopened passages and unresolved questions. A request that cannot fit the full passage remains unresolved; it does not truncate the qualification it was meant to recover. Search results supply evidence for interpretation; a matching phrase alone does not resolve a contradiction.

See [architecture status](architecture-status.md) for the implemented behavior and [production](production.md) for its options. Neither mechanism chooses a new workflow automatically.

## Repair cost and convergence

An observation `o` (a review finding, a source edit, a reported defect) invalidates a set of jobs `I(o)`: the jobs whose request identities change, plus the descendants of any job whose result changes. Its repair cost is:

```math
R(o) = \sum_{j \in I(o)} s_j,
```

where `s_j` is the service cost of job `j`, reported beside reviewer time and the number of delivered artifacts replaced, each in its own units. This is an accounting definition. `I(o)` comes from declared dependencies and request identities, so an undeclared semantic dependency escapes it. A local defect should incur a local cost, while a defect that changes the global route should still reopen the decisions that depend on it. The [measurement protocol](measurement.md) seeds both kinds.

A smaller finding count does not establish improvement. One removed finding may conceal a more severe new error, and successive reviewers may word the same defect differently. Bounded repair limits cost; a stopping rule should keep unresolved findings and report why it stopped. A quality claim needs the final artifact and an independent acceptance check.

## Treat failure rates as workload-specific

Under an independent, identical failure model, a run that requires all `n` calls to succeed with residual failure probability `q` has success probability `(1-q)^n`; the arithmetic matches the follow-up example above. If a call first fails with probability `f` and a retry recovers it with conditional probability `r`, then `q = f(1-r)` under the same model. Both probabilities need measurement on the chosen model and corpus, and an assumed rate must never be reported as a measured engine failure rate. Production failures are often correlated: an unsuitable schema, one provider outage or a repeated bad planning assumption can affect many calls. A few complete-run failures cannot establish a universal per-call rate. Accepting only valid fragments changes the success criterion: unresolved material still needs a recorded disposition, and a successful process exit cannot stand in for complete coverage.

Current Lamina records unresolved reads and continues by default; `reading_failures="abort"` changes that policy. Planned output retains the reading gaps for review. The sweep can be marked ready while listing unresolved windows, because that status records completion of its enabled checks. Inspect those gaps before treating a deck as complete.

Validated cache entries preserve successful work across a restart when their request identities still match. Grouping, outline or assignment failures can still prevent a plan from completing. A saved cache reduces repeat work; it does not guarantee that the remaining call will succeed.

Audio also has its own publication policy. Scripts with unresolved review findings render by default and name the provisional sections. WAV checks establish structure and duration. They do not establish pronunciation, medical correctness or a useful spoken explanation.

## Research questions worth testing

Independent drafting, sequential drafting and concurrent drafting from agreed common details have different dependencies. A shared scenario, definition or callback can sometimes replace a dependency on an entire earlier section. Whether the chosen common details are sufficient needs whole-output evaluation: do the parts explain the same distinction, use consistent terms and avoid accidental repetition?

Source recovery should face both kinds of perturbation: changing a relevant qualifier should change the answer, while changing an irrelevant detail should leave it stable. Test an omitted source unit, a qualification outside an extracted quotation, distant supporting material and a change to the searched collection. An absence claim depends on where the system looked, as well as what it cited.

A complementary reader can be useful even if it is weaker on average. On a fixed evaluation set, let `S_a` contain the tasks approach `a` solves correctly. The additional correct candidates from approach `b` are:

```math
\left|S_b\setminus\bigcup_{a\in A}S_a\right|.
```

This counts newly discovered correct candidates. Separately measure whether the final writer or selector uses them without damaging correct work. Communicating workers can change each other's results, so fixed success sets are only a starting model.

For each comparison, record the same source scope and requested product, accepted output quality, time to first usable result, completion time, request cost and human editing time. Fixture tests can establish source access, cache behavior and scheduling order. Claims about better teaching or faster live production need matched model runs and review of the delivered result.
