# What the optimization checks establish

Lamina has several ways to produce an artifact. Their usefulness depends on the
source, the requested output, the available model and the cost of checking the
result. A passing software test establishes a particular behavior. Choosing a
production workflow also requires a comparison of finished outputs.

## An end-to-end fixture

Run:

```sh
pip install '.[pdf,slides,tokens,test]'
python benchmarks/workflow_matrix.py --output benchmarks/results/workflow-matrix.json
```

The benchmark creates five PDFs and three PowerPoint files with original,
invented windmill specifications. The corpus includes a condition, a negation,
conflicting historical thresholds, repeated facts, a table and speaker notes.
A separate held-out examiner key must never reach a production request. PDF
and PowerPoint parsing use the production import path.

The provider is deliberately scripted. It copies the source, removes one known
exception during writing, identifies that defect during review, and restores
it during repair. The final oracle checks fifteen exact fixture facts, both
historical thresholds, the restored exception and absence of the held-out key.
This evaluates information flow, validation, repair and resource accounting.
It cannot establish how a real model interprets unfamiliar documents.

| Case | Question it exercises |
| --- | --- |
| Direct, planned and supplied assignments | Can each route preserve the same required fixture facts? |
| Identical rerun | Which exact requests are reused? |
| Changed brief | Which source interpretation can be reused across products? |
| One edited PDF page | How far does an edit invalidate reading and writing? |
| One invalid reader quote | Does bounded feedback repair recover the individual call? |
| Persistently invalid reader quotes | Does the engine preserve an honest failure state? |
| Deliberately unqualified draft | Does the review/repair boundary restore the known exception? |

The report contains request counts by stage, transmitted bytes, a reference
token count, cold and warm times, first draft, first review, and first terminal
section review. A terminal review may still contain unresolved findings. The
request delays follow a seeded lognormal distribution with four available
workers; their values describe the fixture. They are separate from live model
latency and provider billing. Reference tokens use `cl100k_base`; adapters must
report actual usage for cost accounting.

### Recorded fixture results

The [machine-readable run](../benchmarks/results/workflow-matrix.json) records
the exact implementation fingerprint and confirms it stayed unchanged during
the run. Every successful document route retained the fifteen required facts,
restored the deliberately removed exception, and excluded the held-out key.

| Provider calls | Direct | Planned | Supplied assignments |
| --- | ---: | ---: | ---: |
| Cold run, including a repair and recheck | 4 | 21 | 12 |
| Identical rerun | 0 | 0 | 0 |
| Changed brief | 4 | 13 | 12 |
| One edited PDF page | 4 | 4 | 2 |

Supplied assignments are prepared by the fixture. Their creation cost is
outside that engine run; a real comparison must count an external planner
unless those assignments already exist. The outputs preserve the same required
facts with different section structures. This comparison does not establish
equal prose quality.

The planned route reused all eight source reads after the brief changed. A
single malformed quote required one extra reader call and recovered. Persistently
invalid quotes exhausted two attempts per reader and left the plan failed;
invalid material was never counted as completed work.

A separate stress fixture required eighty distinct apparatus records under a
30,000-byte request ceiling. Hierarchical planning and writer subdivision
completed with 179 calls, a largest request of 29,897 bytes, and all eighty
required facts present. The fixture assigns one record per final section; that
section count is its scripted choice. Dense Unicode cases preserved four exact
multilingual and notation examples. Assessment and podcast-script cases retained
the required answer/script content; the assessment solver received no source
fact markers or examiner text.

Recorded cold elapsed times were 50.5 ms direct, 95.7 ms planned and 40.7 ms
with supplied assignments. The synthetic provider delays are only milliseconds,
so local database and interpreter work also contribute materially. These values
must not be extrapolated into live model speedups. Actual provider usage and
prices remain unmeasured. An explicit continuity review added five relationship
calls after cached section work on this fixture.

## Verification has distinct duties

| Check | What it establishes | What still needs judgment |
| --- | --- | --- |
| Exact source reference | The cited source contains the submitted quotation | Whether the source is correct, current or applicable |
| Reader disposition | A unit was considered and whether an idea cited it | Whether all relevant meaning was extracted |
| Editorial partition | Every extracted object has an owner or explicit omission | Whether grouping and omission serve the brief |
| Claim mapping | Claimed output text appears in a named body and links to source quotations | Whether the quotation supports the claim and its qualifications |
| Section review | A reviewer reported concrete support, coverage or consistency defects | Defects the reviewer missed |
| Relationship review | A reviewer compared completed sections connected by declared context or a shared source relationship | Undeclared relations and conflicts outside those pairs |
| Blind assessment solve | A separate request attempted the candidate material without the key | Whether real candidates can use it and learn from it |

`verification.validate_claims` accepts optional claim mappings with `id`,
`text`, `body_field` and exact `evidence`. One mapping may span a sentence,
table cell or a longer qualified statement. This avoids treating a sentence
splitter as a factual-claim detector. Missing mappings remain visible in the
receipt. Supplied mappings must resolve exactly to output and source text.
The semantic reviewer checks support, omitted qualifications and material
claims with no mapping in the same section review request.

`verification.coverage_report` keeps considered units, reader citations,
editorial assignment and output citations separate. It reports uncited unit
IDs so an operator or reviewer can inspect them. An uncited unit can contain
an irrelevant title, repeated content or a missed fact; the count alone cannot
distinguish those cases. Embedding similarity also cannot establish entailment.

`check_document_sections` examines completed sections connected by an explicit
source dependency, candidate prerequisite, or shared-context quotation linking
their owners. Consecutive sections can be included when a document continuity
review is requested. Each call keeps both completed bodies, claim mappings and
citations. An oversized pair remains explicitly unchecked and the audit stays
in `review`. Findings identify affected sections. Receipts report which pairs
were examined and how many other pairs exist. This defines the audit's actual
reach and keeps its extra calls visible.
Production enables this extra audit with `document_review=true`. A null
`document_checks` field means it was not performed. Explicit shared-context
section scopes determine which outputs a relationship concerns; legacy plans
fall back to the owners of the cited units.

## Mathematical claims and their assumptions

### Failure accumulation

If each of `W` required calls independently fails with probability `f`, first
attempt success is `(1-f)^W`. At assumed `f=0.02` and `W=300`, the value is about
0.00233. Correlated failures, different call difficulties and caching change
that model. The assumed rate must never become a measured engine failure rate.

A retry with conditional recovery probability `r` changes the individual
unresolved probability to `f(1-r)` under that model. Both probabilities need
measurement on the chosen model and corpus. Accepting only valid fragments
changes the success criterion: unresolved material still needs a recorded
disposition. A successful process exit cannot stand in for complete coverage.

### Barriers and shared capacity

For fixed nonnegative section-stage durations, `max_i sum_s L[i,s]` is no
greater than `sum_s max_i L[i,s]`. These describe independent section chains
and barrier stages when sufficient capacity is available. With finite shared
workers, changing priority changes who gets that capacity. Provider rate
limits, service-time variation, retries and cancellation also affect the
schedule. Compare both policies with the same capacity, work and failures.

For any valid schedule, elapsed time is at least the longer of the dependency
critical path and total service work divided by available workers. Adding
workers cannot remove a serial planning dependency. Removing a call can save
both its own work and the time spent waiting for it, provided the output still
meets the same acceptance conditions.

### Size estimates and priority

The longest-processing-time-first scheduling bound assumes known processing
times on identical available workers. Request bytes are an estimate of one
component of a model call. Output generation, reasoning and provider queues
can dominate. Ordering by estimated work needs a matched comparison; the
classical bound does not transfer automatically to byte counts.

### Prefix reuse and cost

Let `M` eligible calls each share a prefix of `P` tokens, with cache-hit
fraction `h`, uncached token price `c_u` and cached token price `c_c`. The
possible input-cost reduction is `M P h (c_u-c_c)`. This is a cost expression;
the logical input still contains the prefix. Its size, exact encoding,
provider behavior and observed cache hits determine whether savings occur.
The output and live latency must be measured separately.

### Repair convergence

A smaller finding count does not establish improvement. One removed finding
may conceal a more severe new error; successive reviewers may word the same
defect differently. Bounded repair limits cost. A stopping rule should retain
unresolved findings and report why it stopped. A material quality claim needs
the final artifact and an independent acceptance check.

## Choices that still require experiments

Reading size, direct-writing crossover, grouping depth, model assignment,
review coverage and concurrency are hypotheses about a workload. Their values
must be distinguishable from hard provider limits and exact source contracts.
No universal word count or neighboring-page count determines semantic context.

A live comparison should hold the corpus, brief and acceptance criteria fixed.
Record source-reading work, planning work, writing work, checking work,
repairs, peak concurrency, actual tokens, time to first acceptable section and
time to the accepted final artifact. Review source qualifications, omissions,
cross-document disagreements, repetitions and usability without revealing
which route produced each candidate. Repeat across document/reference,
question, audio-script and method workflows. Audio delivery additionally needs
listening and navigation checks; a script-level pass does not establish them.

The machine-readable fixture result and test results should be regenerated on
the exact revision being reviewed. A benchmark from a different commit cannot
establish the behavior of the published change.
