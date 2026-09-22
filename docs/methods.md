# Reusable methods in v0.3

A method declares jobs, dependencies, and resource limits. Independent readers run together; an editor waits for their results. Unchanged jobs are reused. The generic JSON-object runtime does not inherit the [lesson pipeline's](architecture.md) ingestion or citation checks; [procedures](procedures.md) configure that pipeline.

## Try it

From the repository root with Python 3.11+ and `python -m pip install -e .`:

```sh
lamina method validate examples/methods/field-guide.json
python examples/methods/demo.py
```

The [method JSON](../examples/methods/field-guide.json) runs `site-read` and `plant-read` before `guide`. The [offline demo](../examples/methods/demo.py) runs three temporary-workspace tasks: changing site notes reruns the site reader and guide but reuses the plant reader. Fixture content does not measure guide quality.

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

The guide node receives both reader results. This adapter only echoes context. A real adapter reads one JSON request from standard input with `protocol: "lamina-stage-1"`, `stage: "method_node"`, `instruction`, `expected_shape`, and `input`, then writes one JSON object to standard output. The bundled `examples/adapter/http_chat.py` accepts this envelope for a compatible model endpoint. The executable, model, and credentials are configured outside the method file. The command provider invokes without a shell and limits requests to 2 MB by default. Change `--adapter-version` or `LAMINA_ADAPTER_VERSION` when model or configuration semantics change.

## Contract and context

A method has `schema_version: "1"`, `family`, `id`, `version`, `description`, `applicability`, `resources`, and `nodes`. `applicability` holds bounded `contexts`, `exclusions`, and `limits` for a person's choice of method; they are not selection predicates. `resources.workers` allows 1 to 128 concurrent jobs. Up to 16 named `lanes` have capacities no greater than workers. Validation accepts 1 to 1024 nodes and rejects cycles, unknown or duplicate dependencies, illegal resources, and unsupported control fields. Reference text may contain links, paths, or model descriptions; it cannot configure the adapter. Method metadata is not an adapter sandbox.

A node has a slug `id`, `role`, `instructions`, `lane`, `depends_on` IDs, JSON `input`, optional `task_keys` and `observation_ids`, and optional `expected_shape` (default `{"result":"str"}`). The shape is a response hint, not enforced output schema. Ready nodes run in file order within global and lane capacities. Each request contains the node's role and instructions, its input, selected task fields, and completed results of declared dependencies only. Omit `task_keys` to send the whole task; use `[]` to send none. Missing keys fail before execution. Selection reduces context and confines cache invalidation after unrelated task edits, though selected sensitive fields still reach the adapter.

The runtime accepts JSON object results. Failure skips descendants while completed siblings remain cached. A run has no internal retry (`retries=0`); a new run can reuse results. SQLite fences stale owners.

## Cache and receipt

Cache identity includes runtime revision, adapter identity, method family/ID, and node ID. The request contains semantic node fields, selected task fields, dependency results, and selected observations. Changes rerun that node; unselected notes, sibling fields, lanes, worker count, applicability prose, and top-level version do not. Version appears in receipts, not every key: change instructions/input or adapter version for behavioral revisions. Descendants rerun when dependency results change, and can stay cached when a rerun returns the same object.

Receipts store run ID, method identity/version/applicability, task digest, adapter identity, completion/failure, node statuses (`executed`, `cached`, `failed`, `skipped`), lanes, dependencies, request bytes, elapsed time, output digest/error, and successful results. `--output` saves JSON; Python's `list_runs(workspace, family)` reads recent runs. There is no CLI run-list command. Receipts may contain sensitive task and result data.

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

The first command saves an operator judgment with a local 32-character ID and timestamp; the second lists recent family observations. `failure` and `note` are optional. Lamina does not verify the claimed digest or judgment. To use a note, add its ID to a node's `observation_ids` (at most 20 unique IDs). Before any worker runs, Lamina checks that selected IDs exist in the method family. It sends those notes as labelled `operator_observation` reference data under `input.experience` and records their IDs in the node receipt. Missing or wrong-family IDs fail before calls. Recording a note alone does not rerun nodes, rank methods, or change instructions. Selection and revision across tasks remain [design goals](design-constraints.md) with a [measurement plan](measurement.md).

`lamina.method_example.method_demo()` runs a deterministic incident-guide fixture. It returns three receipts and captured adapter requests for an initial guide, a changed deployment note, and a revision that consumes one operator caution. For cached nodes, `request_sources` labels the unchanged displayed request `reused_prior_request`. The trace shows actual task fields, dependencies, and experience; it is not evidence of independent semantic reasoning.

## Local browser workbench

Start `lamina app --adapter 'python examples/adapter/http_chat.py'`, then open **Workbench → Custom workflow**. Load the technical brief example or import a method JSON, edit the task, validate, and run. The graph shows dependencies and selected task fields. Results show returned objects and cache decisions; download the receipt for a copy outside the browser.

For a completed run, select a worker and save a note, outcome, and applicability. The browser inserts the observation ID into that worker's method definition for review and a later run. IDs belong to the local workspace, so a method with selected IDs is not self-contained elsewhere.

The browser uses the startup adapter and loopback-origin restrictions; requests cannot select an executable or endpoint.

| Request | Result |
| --- | --- |
| `POST /api/methods/validate` with `{method}` | Canonical validated method |
| `POST /api/method-runs` with `{method, task}` | Run ID and status URL |
| `GET /api/runs/{id}` | Current status and completed receipt |
| `POST /api/method-observations` with `{run_id,node_id,note,outcome,applicability}` | Stored observation ID |

The public site can edit and download methods and inspect recorded examples. Running requires the local app. Custom-method browser status is held in memory; committed jobs and receipts persist in SQLite. Browser responses and downloads redact failed-node diagnostics; full diagnostics stay local. A reviewer node may return a domain verdict such as `revise` even when its runtime call succeeded.

## Limits

The generic runtime checks object shape, scheduling, and cache identity. It does not verify citations, completeness, correctness, teaching quality, or usefulness. A cached object records a prior response under the same adapter identity, and an observation records a person's judgment. Neither establishes method improvement.
