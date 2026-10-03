# Flow geometry: where the time and the failures come from

This note models the planned production route as a dependency graph and
compares it with the sweep design Lamina grew out of (bounded reader windows
with a fixed halo, a local deduplication pass, and independent auditors). It
uses the repository's own measurements where they exist and labels every other
number as an assumption. The point is to make the shape of the pipeline
visible: how many serial model calls sit on the critical path, how many
barriers wait on the slowest call of a batch, how many calls can each kill the
whole plan, and what the reader halo was actually buying.

Notation. `t` is the mean latency of one model call. `P` is the effective
concurrency, `P = min(workers, provider concurrency)`. `W` is the total number
of calls. `D` is the number of calls on the longest dependency chain. `q` is
the probability that one logical call still fails after its `max_attempts`.
`N_p` pages, `N_r` reader windows, `N_i` extracted ideas, `S` output sections.

## 1. The two geometries

**Sweep (original design).** Pack the source into windows of `c` core units
with `h` neighbouring units on each side. Every window is one independent
call whose output is the finished unit of work (cards). Deduplicate locally
with embeddings (no model calls). Audit each window's output in a second
independent call. Deliver.

    D_sweep = 2                           (read, audit)       derived
    W_sweep = 2 · N_r                                         derived
    B_sweep = 1 barrier (read → dedup); audit can stream      derived

**Planned route (current `production.py`).** Stages in dependency order, each
with its call count and whether it is a barrier (all calls must finish before
the next stage starts):

| Stage | Calls | Serial depth | Barrier |
| --- | ---: | ---: | --- |
| Pack windows | 0 model calls; `countTokens` probes with the Gemini adapter | — | generator, overlaps with reads |
| Read | `N_r` | 1 + extensions (≤ 2) + splits | yes |
| Compare relations (opt-in) | `N_i · k` nominations, `k = relation_neighbors = 20` | ≤ 3 | yes |
| Group, per level | `N_i / (C_group · ρ^ℓ)` with `C_group = 24` | 1 per level | yes, per level |
| Outline | 1 | 1 | yes |
| Assign | `N_i / C_assign`, `C_assign = 24` | 1 | yes |
| Refine | one planning call per oversized section, per round | 1 per round | yes, per round |
| Write / review / repair / recheck | `S · (2 + 2·p_f)` | 2 to 4 | no (pipelined per section) |
| Document review (opt-in) | pairs | 1 | yes |
| Audio | segments, after `status == "ready"` | `S / P_audio`, `P_audio` default 1 | yes |

Grouping levels: each grouping call compresses `C_group` cards into `g`
summaries, so the compression ratio per level is `ρ = C_group / g`. With the
starter policy (`C_group = 24`) and `g ≈ 6` natural groups per batch
(assumed), `ρ ≈ 4`. The hierarchy stops when the summaries fit one outline
call of `C_route = 64` cards:

    L = ⌈ log_ρ (N_i / C_route) ⌉                             derived

    N_i =   400  →  L = 2
    N_i = 2 800  →  L = 3

Critical path of the planned route, best case (no context extension, no
split, no refine round, no repair):

    D_min = 1 + L + 1 + 1 + 2 = 5 + L                         derived

Realistic case (one context extension, one refine round, one repair on the
longest section):

    D_real = 2 + L + 1 + 1 + 1 + 4 = 9 + L  ≈ 11 to 12        derived

So before any throughput argument, the planned route has five to six times
the serial depth of the sweep. At `t = 8 s` (the September live runs averaged
roughly 6–10 s per Gemini 2.5 Flash call with a 1 024-token thinking budget;
assumed from the 35 s / 14-call ready trial) that is 90–100 s of pure chain,
with infinite workers.

## 2. Throughput and the concurrency defaults

Lower bound, from `architecture.md`:

    T ≥ max( W / P , D ) · t                                  derived

Call counts for a 200-page textbook section. Assumptions: 2.5 pages per reader
window under the 96-span starter policy (`N_r = 80`); `g ≈ 6`; three ideas per
section (`S = N_i / 3`; the historical median was one, which makes this
worse); repair fraction `p_f = 0.3`.

    W_planned ≈ N_r + N_i/18 + 1 + N_i/24 + (N_i/3)(2 + 0.6)
              ≈ 80 + 0.96 · N_i                                derived

    N_i =   400  (sparse, ~2 ideas/page):  W ≈   465
    N_i = 2 800  (dense, ~14 ideas/page):  W ≈ 2 770

    W_sweep = 2 · 80 = 160

The default engine `workers` is 8 and the bundled Gemini adapter's
`max_concurrency` is 4, so `P = 4` unless both are raised:

    T_planned(P=4,  t=8 s)  ≈  465/4 · 8  ≈   930 s  (sparse, 15 min)
                            ≈ 2770/4 · 8  ≈ 5 540 s  (dense,  92 min)
    T_planned(P=72, t=8 s)  ≈  max(465/72, 11) · 8 ≈ 90 s   (chain-bound)
                            ≈  max(2770/72, 11) · 8 ≈ 310 s

    T_sweep(P=72, t=30 s)   ≈  max(160/72, 2) · 30 ≈ 67 s

The sweep used `t ≈ 30 s` because each call wrote 50–70 cards (output-bound,
which is the "limited by Gemini output capacity" observation and why the USL
fit squeezed upward). The planned route's calls are shorter but there are
seventeen times as many of them, and at the shipped defaults the engine is
throughput-bound by a factor of ten to sixty. Raising `P` recovers the
throughput term; it cannot recover the chain term, which is where the sweep's
2 versus 11 shows up.

## 3. Barriers and tails

Every barrier waits for the slowest call in its batch. For `n` independent
calls with mean `t` and coefficient of variation `CV`, a Gaussian
approximation gives

    E[max of n] ≈ t · (1 + CV · √(2 ln n))                    approximation

Provider latency for structured-output calls with thinking has `CV ≈ 0.5`
(assumed). For a reading batch of 80 windows, `√(2 ln 80) = 2.96`, so the
barrier finishes at about `2.5 t`, not `t`. The planned route has
`B ≈ 1 + L + 1 + R ≈ 5–6` barriers (read, each grouping level, assign, each
refine round). The tail cost alone is therefore

    T_tail ≈ B · 1.5 t ≈ 6 · 12 s ≈ 70 s                      derived from the above

The sweep has one barrier. Audit calls can start as soon as their window's
cards exist, and card delivery can stream.

A reading batch is also serialised by the context round-trip. Without a halo,
a window whose boundary cuts a list, a table row or a qualification returns
`context_request` and is re-sent with one more group. If a fraction `p` of
windows need that:

    expected calls per window  = 1 + p + p²                   derived
    P(reading barrier ≥ 2 t)   = 1 − (1 − p)^N_r              derived

    p = 0.10, N_r = 80  →  99.98 %

With no halo the reading phase almost surely contains at least one two-call
chain, so its barrier is at least `2 t` plus the tail term. The September
log shows exactly this: the first eight-page trial's reader needed the next
page to finish a sentence, the extended request overran its policy and the
trial failed.

## 4. What the halo was for

With `c` core units and `h` units of neighbouring context on each side, the
token overhead per read is

    overhead(c, h) = (c + 2h) / c                             derived

    ROUNDS differential extraction:  c = 18, h = 2  →  1.22×   measured (engineering-decisions.md)
    unprofiled Markdown reader:      c ≤ 8,  h = 2  →  1.50×
    PDF reader, page units:          c = 2,  h = 1  →  2.00×

The halo converts a serial, probabilistic round-trip (section 3) into a
fixed, parallel cost. For `p > 0` and any barrier after reading, the halo is
strictly better in latency; it is worse only in input tokens by the factor
above. The "haloing we never understood" was the thing that kept reading at
depth 1.

Whole-unit halos are expensive when the unit is a PDF page. A span halo is
cheaper: show the last `m` sentence spans of the preceding unit and the first
`m` spans of the following unit, with their real span IDs so citations still
resolve against the full unit.

    span halo cost ≈ 2 · m · tokens-per-sentence
    m = 6, 25 tokens/sentence  →  ~300 tokens  ≈ 12 % of a 2 500-token read

That is what `reader_context_spans` implements (section 8). The reader keeps
the `context_request` path for the cases a boundary halo cannot cover, and the
first request in a direction completes the partial unit before stepping to
the next group.

## 5. Reliability: every planning call is a kill switch

`plan_production` raises if any reading batch is unresolved, any grouping,
outline, assignment or refinement call fails, or `refine_sections` cannot
subdivide. The plan is one object, so the probability the plan completes is

    P(plan) = (1 − q)^(N_r + N_group + 1 + N_assign + N_refine)     derived

The September 24 runs completed about half of their 14-call trials. Treating
those failures as independent per call gives `q ≈ 1 − 0.5^(1/14) ≈ 4.8 %`;
several were planning-specific (empty overview sections), so the per-call
rate on reads is lower and on planning higher. Using `q = 2 %` and `5 %`:

    sparse, 200 pages:  calls = 80 + 22 + 1 + 17 ≈ 120
        P(plan) = 0.98^120 ≈ 8.9 %      0.95^120 ≈ 0.2 %
    dense, 200 pages:   calls = 80 + 156 + 1 + 117 ≈ 354
        P(plan) = 0.98^354 ≈ 0.08 %     0.95^354 ≈ 10⁻⁸

The cache changes this from "impossible" to "restart until done": each restart
reuses completed calls and re-runs the failed ones, so the expected number of
attempts per item is `1 / (1 − q)` and the expected number of human restarts
is small. But each restart is a manual action and a full barrier tail, and the
app does not loop automatically. The sweep's failure model is per window:
a failed window loses its cards (or is retried alone); the run never dies.

    sweep:  P(run) = 1,     expected coverage = 1 − q        derived

`reading_failures = "continue"` (section 8) gives the planned route the same
property for the reading stage: unresolved windows are recorded in the plan
and the receipt, the run continues on what was read, and the receipt stays
in `review`.

## 6. The ready gate

`status == "ready"` requires zero remaining findings after one repair, zero
unresolved relation groups and passing document checks. Audio delivery
refuses anything else. With a residual per-section finding rate `p_r`:

    P(ready) = (1 − p_r)^S                                    derived

    p_r = 2 %, S = 130  →  7 %
    p_r = 5 %, S = 130  →  0.1 %

One of the four protocol-9 confirmation trials finished with unresolved review
findings on a six-section artifact, which is consistent with `p_r` in the few
percent range. On a textbook-sized script the podcast will essentially never
render without a manual revision pass. A reviewer finding on one section is
not a reason to withhold 129 others from the speech lane.

## 7. Where the PR #3 changes sit in this model

- **Support dependencies in cache keys.** Correct and cheap. It widens the
  invalidation set on source edits, which is a cost on revision, not on a
  cold run.
- **Grouped writer/reviewer requests (`sections_per_request = b`).** This
  amortises the fixed per-call overhead (time to first token plus the thinking
  budget), roughly `(b − 1) · (t_0 + thinking/TPS) ≈ (b − 1) · 6 s` per batch.
  It does not change the output-token work, so `W / P` in token terms is
  unchanged, and the grouped call's latency scales with `b` while the parallel
  version's does not. It also reintroduces the attention dilution that
  collapsed card density per page in the original system (70 → 40 cards when
  a reader was asked for too much in one output). The cheaper way to amortise
  the overhead is to drop the thinking budget on mechanical stages (review,
  recheck) and raise `P`, which the PR now permits up to 128.
- **Evidence comparison (`compare_relations`).** The nominator is a lexical
  inverted index with a frequency cutoff; the comparison is one model call per
  nominated pair with up to three serial expansions. Call count is
  `O(N_i · k)`:

      N_i = 1 000, k = 20  →  10 000–20 000 calls  →  at P = 8, t = 8 s: 3–6 h

  The original deduplication pass was `O(N_i²)` float operations over
  embeddings, or `O(N_i log N_i)` with an index, and zero model calls. Model
  comparison belongs only on pairs above an embedding-similarity threshold,
  and only when the task needs the relation kind (contradiction, supersession)
  rather than a merge decision. The relation kind "unresolved" also flips the
  receipt to `review`, which feeds section 6.
- **Shared-pool reader splits, incremental packing, separate count/generation
  admission.** All correct; they remove self-inflicted serialisation and do
  not change the chain or barrier counts above.
- **Per-section speech segments.** Correct, and the prerequisite for
  synthesising a section the moment it is reviewed clean rather than after the
  last section finishes. That pipelining is the remaining step; today audio
  is a separate phase of `S / P_audio` with `P_audio = 1` by default.

## 8. What this branch changes

- `reader_context_spans` defaults to 6: a span halo on every budgeted reader
  window (section 4), shrinking to fit the reader budget rather than
  rejecting owned material. Packing measures the haloed window. The
  context-request path still works; a request in a direction whose adjacent
  unit is partial first completes that unit, then steps to the next group.
  The cost is wider invalidation on edits: an edit to one unit now rereads
  its two neighbours as well.
- `reading_failures` defaults to `continue`: unresolved reading batches are
  recorded in `plan["planning"]["unresolved_reads"]` and the receipt, reading
  proceeds with the successful windows, and a planned receipt stays in
  `review` (section 5). The sweep stays `ready` and reports the gap.
- `workflow="sweep"`, selected by `format="cards"`: the depth-2 route.
  Readers write cards; `similarity.py` suppresses near-duplicates locally
  against the kept set only (no chain merges, no model calls); a
  deterministic sample of windows (`audit_rate`) gets one source-centred
  audit call whose findings are attached, never gating; the deck exports to
  Anki. Reading is the whole critical path.
- Planning tree streams: a grouping level starts as soon as a full batch of
  the level below exists, and only after the arrived summaries already
  exceed the outline budget, so no grouping call is spent on a level that
  could have gone straight to the outline. Level-0 batches keep source
  order. The outline sees one original exemplar card per group. Barriers
  `B = 1 + L + 1 + R` (section 3) become `B = 1 + 1 + R`: the reading
  barrier and the outline call.
- `compare_relations` nominates by similarity (provider `embed` when
  offered, otherwise TF-IDF) above `relation_threshold`, plus same-unit and
  same-structure lanes. Model work is bounded by the threshold and `k`
  rather than by every lexical overlap (section 7).
- Podcast sections are synthesized the moment they leave review, on a
  speech lane bounded by the adapter's `audio_concurrency`, as the same
  cached segments delivery assembles. Audio overlaps writing. Scripts in
  `review` render by default; the manifest lists the provisional sections.
- `workers` and the Gemini adapter's `max_concurrency` default to 16.

Revised critical path for the planned route after these changes, best case:
read (1) + grouping levels still serial per card (L, but overlapped across
levels) + outline (1) + assign (1) + write + review (2) ≈ 5 + L calls with
far fewer barriers; realistic ≈ 8 + L. For the sweep: 1 read + 1 audit on
the sampled windows, the audit overlapping nothing because it is the last
step; `D = 2`.

## 9. What is still open, in order

1. Overlap reading with level-0 grouping: start grouping batches as reads
   complete rather than after the reading barrier. The streaming tree makes
   this a change in `_read_and_plan` only.
2. Measure. The one comparison that settles the direction: the same 80-page
   section through the sweep and the planned route, five cold runs each,
   recording time to first card, time to completion, completion rate, cards
   per page and human-judged coverage of twenty planted distinctions.
3. Thinking budget off for review and recheck before any request grouping
   is used; measure cards per page under grouping before it becomes a
   default anywhere.
4. Episode planning for podcasts: the orchestrator's legitimate job is to
   size episodes from the card inventory and route locality-grouped
   segments to writers; completed-prose callbacks remain a method-graph
   dependency.

## Limits

The latency figures use one assumed mean call time and one assumed
coefficient of variation; replace them with the receipt's `wall_ms`
distribution from a real run. The per-call failure rate is inferred from
fourteen-call trials, not measured per stage. Ideas per page and sections per
idea are taken from the ROUNDS audit and the September trials and will differ
by source. None of this measures output quality; it measures the shape of the
work.
