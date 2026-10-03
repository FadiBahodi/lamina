# Evidence dependencies and physical execution

Production protocol 11 separates claim ownership, supporting evidence, physical
requests and output sections. Existing protocol-10 plans must be replanned;
eligible future runs use the new semantic cache identity.

## Evidence and invalidation

Every reader idea has owned `unit_ids` anchored in its core and derived
`support_unit_ids` for cited context outside the core. Citations can address only
material actually visible to that read. A context-only idea is rejected. Writer
and reviewer requests include exact supporting units for assigned and declared
prior ideas; their request hashes therefore change when supporting text changes.
Unrelated requests can remain reusable. Source edits that change packing or
planning boundaries may still invalidate more work.

Optional comparison runs after reading and before planning. Local similarity
(provider embeddings when the adapter offers `embed`, otherwise TF-IDF) nominates
pairs above a threshold, plus same-unit and same-structure lanes. A provider
hook can add retrieval lanes and multi-source groups. Frequent postings are skipped to bound retrieval
work; their count is reported. Models compare the actual source passages and
can request missing evidence. Relations preserve participant IDs, evidence,
classification and searches. Planning sees their conditions; affected writers
receive their support. Ownership never transfers because two claims are related.

Nomination recall and comparison accuracy are separate unmeasured quantities.
Lexically dissimilar relations need caller/dense nominations or successful query
expansion. A limited search is not an exhaustive reconciliation algorithm.

## Grouping and scheduling

`sections_per_request` defaults to 1. Larger values group ready writing/review
work under full request and stage workload checks. Each task retains its own
source alias scope, output contract, section identity and fenced cache entry.
Valid rows survive a malformed sibling. Invalid/missing rows retry individually;
provider outages do not fan out into another wave of calls. Repairs remain local.
Cached sections are removed before forming a new physical request. A change to
one section does not force an otherwise unchanged peer to be generated again.

Ready follow-ups continue to precede fresh writing under one shared pool. There
is no all-writer barrier. Reader truncation releases child tasks into that pool;
children keep ordered ownership and adjacent context. Incremental packing releases
eligible reads before later preparation finishes. Native Gemini token counting
has a separate admission lane; every submitted request still receives exact
capacity checking. No provider throughput guarantee follows from a worker count.

## Delivery

The local app streams one raw file at a time to temporary disk. Finished local
section checks publish bounded provisional previews through a separate cursor
endpoint; the progress response stays small. Assessment previews never contain
examiner prose, source quotations or diagnostic titles. Full project checks may
supersede provisional content.

Ready podcast sections are separate synthesis/cache units. PCM segments remain
playable files even if another segment fails. Matching formats are concatenated
in order on disk; incompatible formats fail visibly. The joined WAV can exceed
the per-adapter response limit. Shared speech-resource names and capacities scope
local-process concurrency. Audio rendering still starts after the script reaches
ready; synthesis during unfinished script production and audio streaming remain
future work. Prosody, pronunciation and listening fidelity need direct evaluation.

## Validation and limits

Deterministic regressions cover support propagation, support-only invalidation,
unknown references, three-source comparison expansion, shuffled nomination,
shared-pool reader splits, six-section batching, local retry/repair, segment reuse,
large raw uploads and bounded preview delivery. Their exact responses test
mechanics, not model understanding. The six-section fixture makes 1 write and
1 review request with grouping, versus 6 writes and 6 reviews without it, while
holding all six outputs and evidence records constant.

No live model, large-chart timing, OCR throughput, dense-retrieval recall,
independent assessment quality or listening evaluation is established by these
tests. Layout-aware visual extraction, original-question inventory and completed-
prose podcast callbacks remain separate product work. The blind assessment
boundary, direct/assigned routes and existing method runtime remain available.

### Verified build record

On the implementation branch based on `80c9dce`, Python 3.12 completed 388 tests
and 21 subtests; 11 optional-dependency tests were skipped. The wheel built and
its installed production/revision fixture ran successfully. A headless Chromium
journey used the local app's production form to upload two original source files,
observe three provisional sections while another writer was still active, and
open the finished artifact and revision control with no page errors. Browser
responses and audio bytes in these checks were deterministic fixtures. No live
provider key was configured. The branch is intended for PR review; no hosted
release or production deployment is implied.
