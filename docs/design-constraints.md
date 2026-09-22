# Design constraints for reusable methods

The Tintinalli/ROUNDS production history shaped these constraints. Public examples use original or permissioned material. Lamina v0.3 introduced method graphs, resource lanes, per-node caching and local observations; the broader editorial requirements below guide further work. See [methods](methods.md), [architecture](architecture.md) and [measurement](measurement.md) for implementation and evaluation details.

A recurring failure was a polished artifact with an important answer missing or badly explained. The source citation and processed-page count could both look correct. The design therefore needs a traceable sequence:

source region → claim or answer → editorial decision → section or omission → review → repair → delivered version

An editor should be able to find the source, understand an omission and open the delivered revision.

## Method design

1. Assign source roles for the task. Teaching material, style examples, conflicting references and held-out questions need different uses. A prior exam question might guide form or supply an answer inventory for one project and remain held out in another. Declare roles before ingestion, including how to handle unreadable tables, images, scans and attachments.

2. Preserve the objects the task requires. Inventory answers, conditions, quantities, visual dependencies, conflicts and retrieval demands. Keep source wording beside the model's interpretation so an editor can find a lost qualifier. Useful units range from a marked answer to a decision threshold, image comparison or causal explanation.

3. Record editorial choices. Inclusion, deferral, exclusion and uncertainty need reasons that an editor can revisit. Consider prerequisites, source support and the cost of omission. Keep search relevance distinct from priority, and distinguish suggested gaps from attributed source facts. Reversing a choice should preserve unaffected work.

4. Match the output to the material and learner. Lists, contrasts, changed-case decisions, annotated images, calculations, references and audio have different requirements. A method should choose a form and check whether it supports retrieval after attention moves elsewhere. Audio also needs pacing, pronunciation, script-to-file checks and playback review.

5. Declare dependencies and resources. Independent regions can be read in parallel; related material across partitions may need a bridge review. A shared route requires the relevant evidence before writing starts. Model review, human review, media generation and delivery have their own dependencies. The runtime supplies a validated graph, JSON jobs, dependency results, resource limits and caching. Domain checks and delivery rules belong in the method built on it.

6. Budget context. Send each worker its source passage, useful neighbors and shared planning material. Record request bytes and tokens, the largest request, repeated context and excluded material. Global planning must fit the source scale. Compact records need source pointers so reviewers can reopen passages before changing a merge or omission.

7. Make findings actionable. A review should identify the affected assertion, answer, grouping, figure, prompt or delivered file and its version. Repair the relevant descendants in the work graph. A wording fix may be local; a missing central concept may require a new plan. High-stakes content needs qualified domain review.

8. Design recovery and delivery. Jobs need durable status, retry limits, idempotent publication, stale-owner protection and visible failures. A delivery record should include destination, artifact hash, timestamp, access check and failed checks. Track generation, upload, device access and learner use as distinct events.

9. Version method changes. A revision needs an observation, proposed change, new version and cache identity, comparison on held-out tasks, and an acceptance decision. Keep the old version and counterexamples. User observations can prompt a revision; the editor decides how to apply them.

10. Show information where users can act. Source and coverage views should identify accepted files and regions, their output locations, deferred work, pending review and finished files. Users should be able to repair a gap without reading logs. Coverage figures need a denominator and exclusions.

## A connected experiment

The runtime executes JSON jobs with resource limits, dependencies, caching and recovery. A node can receive selected observations from the same method family. The user chooses those IDs and reruns the method. Source reading, answer inventory, selection, authoring, review and export can use that machinery.

A permissioned corpus containing prose, a table, a figure and related questions would test the design. Freeze a source-region inventory. Have reviewers label important answers, omissions, conflicts and unsupported claims, then build a route and two output forms. Introduce a missing-item finding after review, repair it and record which jobs and artifacts changed.

Ask an unfamiliar user to locate and correct the omission, then find the delivered revision. Measure context use, rework, quality and cost.

## Cost model

For jobs `i`, let `t_i` be observed service time, `W = Σ t_i` total work and `D` the sum along the longest dependency path. With `p` identical available workers, the lower bound is `T ≥ max(W/p, D)`.

With resource lanes `r`, the bound becomes `T ≥ max(D, max_r W_r/c_r)`, where `W_r` is service time demanded from lane `r` and `c_r` its capacity. Lanes might represent model calls, CPU parsing, GPU audio or human review. Rate limits, setup, scheduling, retries and external latency add time. Jobs requiring several resources at once need further scheduling analysis.

Context amplification is `A = (Σ input tokens across semantic jobs)/(tokens in distinct accepted source text)`. Report input by stage, the largest request and source regions never sent in usable form. Repeated instructions and summaries contribute to this ratio.

Repair cost is `R(o) = Σ service cost of jobs invalidated by observation o`, plus reviewer time and replacement of delivered artifacts. Local defects should incur local repair costs while preserving dependencies that require wider revision.

Queueing estimates need arrival rates, service distributions, concurrency limits and throttling measurements. Near saturation, small service-time changes can sharply increase waiting. Report median and tail time to an accepted, accessible artifact alongside quality and cost. The [systems benchmark](benchmarks.md) measures SQLite jobs and scheduled waits.

## Limits

Several requirements here are design goals. The graph runtime supplies execution; methods must add source policy, output checks and delivery acceptance. Selected observations enter a node's context through a user decision. They do not trigger autonomous revision or learning.

Source parsing, answer preservation, interpretation and learning outcomes each need their own evaluation. A source digest cannot account for unread visual content. Model review needs qualified review for high-stakes uses.

The cost formulas describe lower bounds and accounting. Context amplification includes useful repetition, and synthetic scheduling measurements exclude model, reviewer and delivery performance. Additional workers help only where dependencies and available resources allow concurrent work.
