# Reusable methods in v0.3

Lamina can now run a small, reusable **method**: a data-only description of work steps, their dependencies, and the resources they share. Two independent readers can work at once; an editor waits for both and receives their results. A second run reuses unchanged steps. The run returns a receipt, and an operator can record an observation. These are working capabilities, not a claim that Lamina chooses the best method or improves itself automatically.

This generic runtime is separate from the built-in [source-to-lesson pipeline](architecture.md) and the [teaching procedure](procedures.md) that configures that fixed pipeline. It does not automatically ingest documents, enforce the lesson pipeline's citation rules, synthesize audio, or publish an artifact. Its adapter interprets each node and returns a JSON object.

## Try it

From the repository root with Python 3.11+ and `python -m pip install -e .`:

```sh
lamina method validate examples/methods/field-guide.json
python examples/methods/demo.py
```

The [method JSON](../examples/methods/field-guide.json) has independent `site-read` and `plant-read` nodes followed by `guide`. The [offline demo](../examples/methods/demo.py) runs three tasks in a temporary local workspace. Its second task changes only site notes: the site reader and guide rerun while the plant reader is cached. The fixture outputs are deliberately simple. This demonstrates scheduling and reuse, not model-generated field-guide quality.

The CLI can run the same method through an operator-configured adapter. Create `garden-task.json` with `{"site_notes":"morning shade, one tap","plant_notes":"tomatoes and mint","audience":"Saturday volunteers"}`. Save this minimal echo adapter as `my_method_adapter.py`:

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

The guide node receives the two reader result objects; this echo adapter does not write useful prose. A real adapter reads one JSON request from standard input with `protocol: "lamina-stage-1"`, `stage: "method_node"`, an `instruction`, `expected_shape`, and `input`; it writes one JSON **object** to standard output. The bundled `examples/adapter/http_chat.py` accepts that standard envelope and can be configured for a compatible model endpoint, though the generic runtime checks only that its reply is an object. The executable, model and credentials are configured outside the method file. The command provider invokes without a shell and limits requests to 2 MB by default. Change `--adapter-version` or `LAMINA_ADAPTER_VERSION` when model/configuration semantics change.

## Method contract and context

The file has `schema_version: "1"`, a `family`, `id`, `version`, `description`, `applicability`, `resources`, and `nodes`. `applicability` contains bounded `contexts`, `exclusions`, and `limits`: these are documented guidance, **not executable selection predicates**. An operator decides which method fits. `resources.workers` caps simultaneous work at 1–128; up to 16 named `lanes` each have a capacity no greater than workers. The validator accepts 1–1024 nodes, rejects cycles, unknown or duplicate dependencies and illegal resources, and rejects unsupported control fields. Reference text may contain links, paths, or model descriptions; these are data, not executable configuration. This is a bounded data contract, not a sandbox for the operator's adapter.

Each node has a slug `id`, `role`, `instructions`, a `lane`, `depends_on` IDs, an arbitrary JSON `input` object, optional `task_keys`, optional `observation_ids`, and optional `expected_shape` (default `{"result":"str"}`). The shape is a bounded response hint sent to the adapter, **not output-schema enforcement**. Ready nodes are scheduled in file order within the global and lane capacities. The request's instruction contains the role and directions; its `input` contains the method family/ID, node ID and input, selected task fields, and **only completed results of declared dependencies**. Omit `task_keys` to send the entire task; use an empty list to send none. Missing selected keys fail before the run. Selection reduces irrelevant context and prevents unrelated task edits from invalidating a node; it is not a privacy guarantee if sensitive fields are selected.

The generic runtime checks only that a node returns a JSON object. It does not check citations, answer completeness, domain correctness, teaching quality, or downstream usefulness. If a node fails, its descendants are skipped and completed siblings survive for a later run. The method path has no automatic retry *within* one run (`retries=0`); rerunning can resume from cached work. The SQLite job store supplies claims and stale-owner protection.

## Cache and receipt

Node cache identity includes runtime revision, adapter identity, method family/ID and node ID. Its request includes that node's semantic fields, selected task fields, dependency result objects, and **only its explicitly selected observation content**. Changing these inputs reruns it. Adding an unselected observation, changing only a sibling task field, lane, worker count, applicability prose, or top-level method version does not. The version is recorded in the receipt but is **not** in every node cache key. If a revision changes what a node should do, edit its instructions/input or adapter version; bumping the label alone is insufficient. A descendant reruns if the dependency **result** changes; if a rerun returns the same object, the descendant can remain cached.

Every call stores a local receipt with run ID, method family/ID/version and applicability, task digest, adapter identity, completion/failure, node status (`executed`, `cached`, `failed`, `skipped`), lane, dependencies, serialized request bytes, elapsed time, output digest or error, and successful result objects. `--output` saves it as JSON. The Python API `list_runs(workspace, family)` reads recent receipts; there is no current CLI run-list action. A receipt is an execution trace, not a quality verdict. Task and result content may be retained in the local workspace and receipt; do not publish sensitive receipts casually.

## Record what happened

After inspecting a run, create `observation.json` and paste the receipt's actual `task_digest`:

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

The first command stores an operator-supplied observation with a local 32-character ID and timestamp; the second reads recent observations for that family. `failure` and `note` may be omitted. The runtime does not verify the claimed digest or judgment. To make a later node use an observation, an operator adds its ID to that node's `observation_ids` list (at most 20 unique IDs). Before calling any worker, the runtime checks that every selected ID exists and belongs to the method's family. It then supplies **only those observations** under `input.experience`, labelled `operator_observation`, as reference data rather than as instructions. The node receipt records the selected IDs. Missing or wrong-family IDs fail before worker calls. This is an explicit, scoped downstream consumer; recording a new observation alone does not reopen nodes, rank methods, adapt instructions, or promote a revision. Evidence-led selection and revision across new tasks remain [design goals](design-constraints.md) with a [measurement plan](measurement.md). A cached answer proves only that a prior request with the same adapter identity returned that object; a recorded observation proves only that a judgment was entered.

The packaged `lamina.method_example.method_demo()` runs a separate deterministic incident-guide fixture. It returns three actual run receipts plus the **captured adapter requests** for each node: an initial guide, a changed deployment note, and a later guide that explicitly consumes one operator caution. For a cached node, its displayed request is the identical last request that produced the reused result; `request_sources` labels it `reused_prior_request`. This allows inspection of the worker's real task fields, dependencies, and selected experience without claiming that the fixture performed independent semantic reasoning.


## Local browser workbench

Start `lamina app --adapter 'python examples/adapter/http_chat.py'` after configuring the adapter. Open **Workbench → Custom workflow**. Load the technical brief example or import a method JSON file, edit its task, validate the graph, and run it. The graph exposes direct dependencies and selected task fields; the result panel displays the returned objects and cache decisions. Download a receipt to retain the run independently of the browser.

A completed run can receive an operator observation. Select the affected worker, enter a note, outcome, and applicability, then save. The browser inserts the returned observation ID into that worker's method definition. Review the edit and run again. Selection is explicit; saving a note does not automatically regenerate anything. Observation IDs refer to the local workspace, so a method carrying those IDs is not self-contained when moved to a new workspace.

The browser API uses the same startup-configured adapter and loopback-origin restrictions as the document builder. A request cannot select an executable or endpoint. The endpoints are:

| Request | Result |
| --- | --- |
| `POST /api/methods/validate` with `{method}` | Canonical validated method |
| `POST /api/method-runs` with `{method, task}` | Run ID and status URL |
| `GET /api/runs/{id}` | Current status and, when complete, receipt |
| `POST /api/method-observations` with `{run_id,node_id,note,outcome,applicability}` | Persisted observation ID |

The public website supports editing and downloading a method, plus inspection of recorded examples. Execution requires the downloaded local app. Custom-method browser run status is currently held in memory (the newer source-aware Projects path persists its status); the underlying committed jobs and runtime receipts persist in SQLite. Failed-node diagnostics are redacted in browser responses and downloadable receipts; full diagnostics remain local. A successfully executed reviewer node can still return a domain verdict such as `revise`: runtime completion is not approval to publish.
