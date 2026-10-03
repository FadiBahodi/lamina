# Where a production run spends its time

A run takes longer when it repeats work, waits for a prerequisite, or queues for a busy resource. Adding workers helps only the work that can proceed independently. This note describes the current routes, then uses small calculations to explain their tradeoffs. The calculations are models with stated assumptions; they are not Lamina performance measurements.

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

Real calls differ in length and compete for provider admission, network connections and output capacity. Retries and human review add more work. Use measured service durations for the first formula whenever possible.

For a planned route with `L` grouping levels, the simplest chain is reading, `L` groups, outline, assignment, writing and review: `5 + L` calls. Context extensions, subdivision and repair lengthen some paths. Streaming allows different branches to overlap; it cannot start a group before the material it needs exists. A two-call card route and a longer document route also produce different objects. Comparing them fairly requires a common requested result and a quality assessment.

Earlier versions of this note estimated call duration from a complete run's elapsed time and call count. Parallel calls make that inference invalid. The [live-model results](live-model-evaluation.md) record actual experiments; stage-level receipts are the appropriate input to a latency model.

## Why a small halo can help

A source boundary can split a list or hide the condition that qualifies a rule. Supplying nearby text may let a reader finish in one call. With equally sized core units `c` and neighboring units `h` on each side, the input multiplier is:

```math
H = \frac{c+2h}{c}.
```

For example, 18 core units and two neighbors on each side give `H ≈ 1.22`; two core pages with one neighboring page on each side give `H = 2`. Real structures vary in length, so bytes or tokens give a better measurement than page count.

Lamina's default halo uses sentence spans. Six spans on each side at an assumed 25 tokens per sentence would add about 300 tokens. The actual halo shrinks to fit the reader's request allowance. A reader can ask to complete a neighboring unit when this partial view is insufficient.

A halo is a tradeoff. Extra input can increase call time and reduce how many owned units fit. It also causes changes near a boundary to invalidate neighboring reads. Measure how often it prevents a follow-up and whether it preserves the needed distinctions. It cannot guarantee a faster run, and local context cannot expose every qualification elsewhere in the source collection.

Under the narrow assumption that each of `N_r` windows independently needs one extra call with probability `p`, the chance that at least one window needs a follow-up is:

```math
1-(1-p)^{N_r}.
```

For `p = 0.10` and `N_r = 80`, that is about 99.98%. This explains why a rare per-window dependency can occur in most large runs. It does not establish its duration or prove that a larger halo resolves it.

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

The recorded grouping fixture reduced serialized request bytes by 21.9%, with slightly higher local elapsed time in a test without network latency. That measures the fixture's request packing. It does not establish a live-model speedup.

## Release results when their own work is complete

A request can contain two section drafts and return one valid draft and one invalid draft. The valid section's reviewer has everything it needs. Making it wait for the other section's correction adds a dependency that the product never required.

After a grouped response arrives and its rows are validated, Lamina records accepted section results as completed work and returns failed rows or request splits to the existing scheduler. It does not stream partial provider JSON. That keeps the shared worker limit meaningful and lets each accepted section advance. The relevant regression test blocks one sibling retry and observes whether another section reaches review before that retry is released. Timing a fast fixture is less informative than proving that event order.

Source recovery has a related distinction. Looking through already extracted ideas can recover an overlooked relationship between them. It cannot recover a qualification that every reader omitted. Optional evidence-comparison follow-ups can search full permitted original source units, including units with no extracted ideas. Search uses local lexical similarity and exact unit IDs or headings. Each comparison permits up to three queries, each returning at most one new original unit, within the existing three-comparison limit. Records show the source snapshot, searches, reopened passages and unresolved questions. A request that cannot fit the full passage remains unresolved; it does not truncate the qualification it was meant to recover. Search results supply evidence for interpretation; a matching phrase alone does not resolve a contradiction.

See [architecture status](architecture-status.md) for the implemented behavior and [production](production.md) for its options. Neither mechanism chooses a new workflow automatically.

## Treat failure rates as workload-specific

Under an independent, identical failure model, a run that requires all `n` calls to succeed with residual failure probability `q` has success probability `(1-q)^n`. Production failures are often correlated: an unsuitable schema, one provider outage or a repeated bad planning assumption can affect many calls. A few complete-run failures cannot establish a universal per-call rate.

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
