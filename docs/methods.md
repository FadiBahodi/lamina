# Reusable methods

A method describes the jobs for a task: what each worker receives, which completed results it needs, and how many jobs can run at once. Independent readers can work together; an editor starts when their results are ready. Repeated inputs reuse cached results. Use a method when a job needs another job's completed result, or when the work does not fit the [production](production.md) routes.

## Run a method

Configure a [model adapter](adapters.md), then validate a method file:

```sh
lamina method validate examples/methods/field-guide.json
```

The [field-guide definition](../examples/methods/field-guide.json) contains two independent readers, `site-read` and `plant-read`, followed by `guide`, which receives both completed results. Adapt its instructions and task fields to your work. Save matching inputs as `garden-task.json`:

```json
{"site_notes":"morning shade, one tap","plant_notes":"tomatoes and mint","audience":"Saturday volunteers"}
```

Run it with the configured model:

```sh
lamina method run --method examples/methods/field-guide.json \
  --task ./garden-task.json --workspace .lamina \
  --adapter @models.json --output ./garden-receipt.json
```

An adapter receives `protocol: "lamina-stage-1"`, `stage: "method_node"`, instructions, an expected shape and the node's inputs, then returns a JSON object. Keep model configuration and credentials outside the method file. Change the adapter version when its model or behavior changes.

## Contract and context

A method has `schema_version: "1"`, `family`, `id`, `version`, `description`, `applicability`, `resources`, and `nodes`. `applicability` records bounded `contexts`, `exclusions`, and `limits` to help a person choose a method. `resources.workers` allows 1 to 128 concurrent jobs. Up to 16 named `lanes` have capacities no greater than workers. Validation accepts 1 to 1024 nodes and rejects cycles, unknown or duplicate dependencies, illegal resources, and unsupported control fields. Configure the adapter separately; reference text and method metadata cannot select its executable or endpoint.

A node has a slug `id`, `role`, `instructions`, `lane`, `depends_on` IDs, JSON `input`, optional `task_keys` and `observation_ids`, and optional `expected_shape` (default `{"result":"str"}`). Ready nodes with longer remaining dependency chains run first within global and lane capacities; file order breaks ties. Dependency depth is a priority estimate, and does not predict model duration. The scheduler indexes dependents once and updates their remaining prerequisites when a node finishes. Each request contains the node's role and instructions, its input, selected task fields, and completed results of declared dependencies. Omit `task_keys` to send the whole task; use `[]` to send none. Missing keys fail before execution. Selecting task fields keeps requests smaller and allows unrelated task edits to reuse cached results. Selected sensitive fields reach the adapter.

The runtime accepts JSON object results. A failed node skips its descendants; completed siblings remain cached. Each run makes one attempt per node (`retries=0`), and a new run can reuse completed results. SQLite prevents a superseded worker from committing over its replacement.

## Cache and receipt

Cache identity includes runtime revision, adapter identity, method family/ID, and node ID. The request contains semantic node fields, selected task fields, dependency results, and selected observations. Changing those inputs reruns the node. Unselected notes, sibling fields, lanes, worker count, applicability prose, and top-level version leave its cache entry reusable. Version appears in receipts; change instructions/input or adapter version for behavioral revisions. Descendants rerun when dependency results change and can stay cached when a rerun returns the same object.

Receipts store run ID, method identity/version/applicability, task digest, adapter identity, completion/failure, node statuses (`executed`, `cached`, `failed`, `skipped`), lanes, dependencies, request bytes, elapsed time, output digest/error, and successful results. `--output` saves JSON; Python's `list_runs(workspace, family)` reads recent runs. Keep receipts private when task fields or results contain sensitive data.

## Observations

After inspecting a run, create `observation.json` using the receipt's actual `task_digest`:

```json
{
  "family": "field-guides",
  "method_id": "community-garden-visit",
  "method_version": "1.0",
  "task_digest": "paste-actual-digest-here",
  "outcome": "useful with edits",
  "applicability": "worked for two short note sets",
  "failure": "missed a path closure",
  "note": "Check access before calling the guide complete"
}
```

```sh
lamina method observe ./observation.json --workspace .lamina
lamina method experience --family field-guides --workspace .lamina
```

The first command saves an operator judgment with a local 32-character ID and timestamp; the second lists recent family observations. `failure` and `note` are optional. To use a note, add its ID to a node's `observation_ids` (at most 20 unique IDs). Before any worker runs, Lamina checks that selected IDs exist in the method family. It sends those notes as labelled `operator_observation` reference data under `input.experience` and records their IDs in the node receipt. Missing or wrong-family IDs fail before calls. Selecting a note changes the worker's next request; saving one leaves existing requests and cache entries alone. Cross-task selection and revision have a [measurement plan](measurement.md).

## Local browser workbench

Start `lamina app --adapter @models.json` and open **Projects → Advanced tools** in the local app. Import a method JSON, edit the task, validate, and run. The graph shows dependencies and selected task fields. Results show returned objects and cache decisions; download the receipt for a copy outside the browser.

For a completed run, select a worker and save a note, outcome, and applicability. The browser inserts the observation ID into that worker's method definition for review and a later run. To use the method in another workspace, select observations available there or remove the old IDs.

The browser uses the adapter configured at startup and accepts local, same-origin requests.

| Request | Result |
| --- | --- |
| `POST /api/methods/validate` with `{method}` | Canonical validated method |
| `POST /api/method-runs` with `{method, task}` | Run ID and status URL |
| `GET /api/runs/{id}` | Current status and completed receipt |
| `POST /api/method-observations` with `{run_id,node_id,note,outcome,applicability}` | Stored observation ID |

The website provides installation instructions and documentation; method runs happen in the local app or CLI. Method editor progress lives in browser memory; committed jobs and receipts persist in SQLite. Browser responses and downloads redact failed-node diagnostics; full diagnostics stay local. A reviewer node can return a domain verdict such as `revise` after its runtime call succeeds.

## Designing a method

Choose the jobs around the requested result. A reference needs complete answer groups and useful navigation. A podcast needs a teaching sequence and checks on the spoken audio. An exam needs control over what the candidate sees. Record the intended result, source roles and the reason for the division of work with the method.

Give each job its source passages, useful neighboring material, relevant shared decisions and any completed results it needs. Keep source wording beside interpretations so a reviewer can recover a missing condition. Use separate jobs when the work can proceed independently, and dependencies when one job needs another's actual output. Configure resource limits for model calls, media generation and delivery.

Review findings should identify the affected answer, grouping, figure, question or file and its version. Record why material was included, deferred or omitted. Track coverage against the source objects required by the task, and check unreadable images or tables before treating their content as covered. Measure request size, repeated context and the finished result together.

Save useful outcomes and corrections with the delivered version. A delivery record should identify the destination, file hash, access check and unresolved issues. Nodes that publish externally need their own recovery and idempotency rules. When a method changes, retain the reason and compare the result on tasks that were not used to design the change. Cache behavior follows the request inputs described above.

The runtime supplies dependency execution, worker limits, caching and run records. Method authors provide the source, editorial and delivery checks. [Workflow design](workflow-design.md) describes the extension that would let a model choose and revise the method during execution, then use the experience on a later project.

## Limits

The runtime requires a JSON object result; `expected_shape` guides the adapter but is not enforced. Source accuracy, completeness and delivery checks belong to the method. Observations store judgments without verifying their claimed task digest or outcome. The caller selects them for later jobs. Running graphs stay fixed, and model-generated questions or proposed changes are treated as ordinary result data. High-stakes content also needs qualified domain review.
