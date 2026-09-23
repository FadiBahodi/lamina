# Reusable methods

A method describes the jobs for a task: what each worker receives, which completed results it needs, and how many jobs can run at once. Independent readers can work together; an editor starts when their results are ready. Repeated inputs reuse cached results. Use [procedures](procedures.md) to configure the structured lesson pipeline.

## Try it

From the repository root with Python 3.11+ and `python -m pip install -e .`:

```sh
lamina method validate examples/methods/field-guide.json
python examples/methods/demo.py
```

The [method JSON](../examples/methods/field-guide.json) runs `site-read` and `plant-read` before `guide`. The [offline demo](../examples/methods/demo.py) runs three tasks in a temporary workspace. When site notes change, Lamina reruns the site reader and guide and reuses the plant reader.

For a CLI run, create `garden-task.json` with `{"site_notes":"morning shade, one tap","plant_notes":"tomatoes and mint","audience":"Saturday volunteers"}`. Save this echo adapter as `my_method_adapter.py`:

```python
import json
import sys

request = json.load(sys.stdin)
if request.get("protocol") != "lamina-stage-1" or request.get("stage") != "method_node":
    raise ValueError("unexpected stage")
data = request["input"]
json.dump({"node": data["node"]["id"], "task": data["task"],
           "upstream": sorted(data["dependencies"])}, sys.stdout)
sys.stdout.write("\n")
```

```sh
lamina method run --method examples/methods/field-guide.json \
  --task ./garden-task.json --workspace .lamina \
  --adapter 'python ./my_method_adapter.py' --adapter-version echo-v1 \
  --output ./garden-receipt.json
```

The guide node receives both reader results. The example adapter echoes the request context. A model adapter reads one JSON request from standard input with `protocol: "lamina-stage-1"`, `stage: "method_node"`, `instruction`, `expected_shape`, and `input`, then writes one JSON object to standard output. The bundled `examples/adapter/http_chat.py` accepts this envelope for a compatible model endpoint. Configure the executable, model, and credentials outside the method file. The command provider invokes the adapter directly and limits requests to 2 MB by default. Change `--adapter-version` or `LAMINA_ADAPTER_VERSION` when model or configuration semantics change.

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

`lamina.method_example.method_demo()` runs a deterministic incident-guide fixture. It returns three receipts and captured adapter requests for an initial guide, a changed deployment note, and a revision that consumes one operator caution. For cached nodes, `request_sources` labels the displayed earlier request `reused_prior_request`. Use the trace to inspect task fields, dependencies, and experience sent to each worker.

## Local browser workbench

Start `lamina app --adapter 'python examples/adapter/http_chat.py'`, then open **Projects → Advanced tools → Custom workflow**. Load the technical brief example or import a method JSON, edit the task, validate, and run. The graph shows dependencies and selected task fields. Results show returned objects and cache decisions; download the receipt for a copy outside the browser.

For a completed run, select a worker and save a note, outcome, and applicability. The browser inserts the observation ID into that worker's method definition for review and a later run. To use the method in another workspace, select observations available there or remove the old IDs.

The browser uses the adapter configured at startup and accepts local, same-origin requests.

| Request | Result |
| --- | --- |
| `POST /api/methods/validate` with `{method}` | Canonical validated method |
| `POST /api/method-runs` with `{method, task}` | Run ID and status URL |
| `GET /api/runs/{id}` | Current status and completed receipt |
| `POST /api/method-observations` with `{run_id,node_id,note,outcome,applicability}` | Stored observation ID |

The public site lets visitors edit and download methods and inspect recorded examples. The local app runs them. Custom workflow progress lives in browser memory; committed jobs and receipts persist in SQLite. Browser responses and downloads redact failed-node diagnostics; full diagnostics stay local. A reviewer node can return a domain verdict such as `revise` after its runtime call succeeds.

## Limits

The generic runtime checks object shape, scheduling, and cache identity. `expected_shape` guides the adapter but does not enforce its reply structure. It does not verify citations, completeness, correctness, teaching quality, or usefulness. An observation records a person's judgment, without verifying the claimed digest or outcome. The fixture demonstrates execution and cache behavior, not guide quality or measured method improvement.
