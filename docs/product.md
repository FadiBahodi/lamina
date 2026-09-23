# Building useful artifacts from source collections

Lamina turns source files into reference documents, guides, podcast scripts and assessments. A project starts with files, a description of the intended result and a configured model adapter. It finishes with an artifact, its source-aware plan and a receipt that records model calls, reuse, findings and known gaps.

The main production path serves people who need to make a substantial artifact from more material than one model call should handle. Lamina preserves source structure, assigns material to bounded tasks, gives each task the context it needs and saves validated results for later revision. Models decide meaning and editorial form. Code controls source identity, ownership, capacity, execution and exact accounting.

## A project from input to result

Suppose an engineering team has several manuals and incident reviews about safe job retries. They want a field guide that explains when a retried worker may publish a result.

1. Lamina imports the files as identifiable structures. A Markdown table remains a table; a PDF page retains its page location; text, tables and notes from one PowerPoint slide remain connected.
2. The operator marks each source as authoritative, supplemental, historical or an example of form. Held-out assessment material remains unavailable to generation.
3. Lamina chooses a route. A small assignment can go directly to a writer. A larger collection is read in bounded tasks and organized into sections. A person or another agent can also provide the section assignments.
4. Each writer receives its owned material, the original source passages and declared context. A reviewer checks the completed section against the same assignment and sources. A concrete finding can trigger one repair and recheck.
5. Lamina exports Markdown, HTML and optional PDF, together with the plan and receipt. Repeating an unchanged request reuses its validated result. A local section revision can leave unrelated requests unchanged.

The same engine supports assessments and listening scripts. Assessments separate candidate material from examiner material and run a blind solve plus a separate judging call. A configured speech adapter can turn a completed podcast script into a checked PCM WAV. These are production boundaries: the exported assessment is not a live oral-exam application, and a structurally valid WAV still needs listening review.

## Three production routes

`workflow="auto"` selects the simplest route that fits the declared request and workload limits.

| Route | When to use it | Model work before writing |
| --- | --- | --- |
| Direct | The complete source assignment and review request fit one call. | None. The writer works from the original source units. |
| Planned | The collection needs source reading, cross-file organization or retrieval-target reconciliation. | Readers produce source-addressed ideas; a planner creates sections and assigns every idea or records an omission. |
| Assigned | A person or upstream agent already knows the sections and source ownership. | None inside Lamina. The supplied assignments must account for every selected factual unit. |

Automatic selection does not judge whether the result is good. The adapter's context limit establishes what fits; a separate workload policy states how much semantic work a call may attempt. Those limits remain operator choices until they are evaluated on representative material.

## Ownership, shared evidence and dependencies

Lamina keeps three relationships separate because they change what a worker may claim and when it may start.

**Ownership** says what a section must account for. In the retry guide, a section called “Fencing stale completions” might own the manual passage defining fencing tokens and the incident passage describing an old worker's late write. Those passages cannot also be silently assigned as another section's work.

**Shared evidence** supplies relevant source material without changing ownership. A neighboring section about lease expiry may need the fencing definition to explain why expiry does not prove that the first worker stopped. It can receive that exact passage as context while the fencing section remains its owner. Planned earlier ideas are also context, not completed prose.

**Completed-result dependencies** apply when a task needs another worker's actual output. If an editor must quote or transform the finished fencing section, it cannot run in parallel with that writer. That job belongs in a custom method graph with a dependency on the completed result. Assessment checks use a narrower boundary: a later candidate question can receive explicitly declared earlier candidate prompts, while examiner answers stay private.

This distinction allows independent writing to remain parallel without pretending that a shared plan is the same as finished prerequisite text.

## What the operator can inspect

A production plan retains selected source revisions, reading batches, extracted ideas, grouping records, section ownership, declared context, omissions and the capacity decision. The receipt retains completed sections, citations, claim links, review findings, unperformed checks, request measurements, attempts, reported usage and cache outcomes.

These records establish specific mechanical facts. They can show that a source unit reached a reader, that an extracted idea cited an exact span, that a planner assigned it once and that an output claim links to an original passage. They cannot prove that extraction found every relevant fact, that the passage supports the interpretation or that the finished artifact is useful. Lamina records semantic recall as unmeasured unless a separate evaluation establishes it.

## Interfaces

The local Projects interface, `lamina produce` and the Python production API use the same source-to-artifact engine. The browser app binds to loopback, stores project state locally and uses the adapter configured at startup. Selected source text may be sent to that adapter's model service.

The separate [Method runtime](methods.md) runs declared dependency graphs with task-field selection, completed-result inputs, resource lanes and caching. It is a general JSON-object workflow runtime. It does not automatically add Production's source ownership, evidence resolution, section review or artifact contracts; a method author must define the behavior its nodes require.

Older lesson and procedure APIs remain in the package under their own contracts. They are not the current general production architecture. [System origins](system-origins.md) explains how reference, audio, question and oral-case work informed the current design without claiming that every historical system is implemented here.

## Limits and evaluation

PDF extraction can lose reading order, figures and layout meaning. OCR creates a text layer but does not establish correct associations between labels, values and diagrams. PowerPoint text, tables and notes remain structured, but Lamina does not interpret arbitrary visual content.

Model replies can be valid and incomplete. Citations can be real while the explanation loses a condition. Model reviewers can miss the same defect as the writer. The final outline and every indivisible source structure or required context set must fit their configured request limits. Planned production also waits for the route to be complete before section writing begins.

Evaluate the complete artifact on the actual source family and use. Record parsing errors, important omissions, qualifier preservation, unsupported claims, elapsed time, provider usage, operator corrections and whether the result helps its intended reader. The [quality evaluation](quality-evaluation.md) and [measurement protocol](measurement.md) separate these judgments from software and scheduler tests.

See [Production](production.md) for controls and failure behavior, [Architecture](architecture.md) for the code map and scheduling model, and [Parsing](parsing.md) for source boundaries.
