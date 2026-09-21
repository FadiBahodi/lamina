"""Small offline method run for explaining the runtime, not model quality.

The fixture adapter is deterministic. It shows context selection, dependency
ordering, branch-local cache reuse, and a specifically selected observation
changing a later output. It does not claim to interpret arbitrary documents.
"""
from __future__ import annotations

import copy
import tempfile
from pathlib import Path

from .method_runtime import record_observation, run_method
from .store import Workspace


class _FixtureAdapter:
    identity = "incident-guide-fixture-v1"

    def __init__(self) -> None:
        self.latest_requests: dict[str, dict] = {}

    def call(self, stage: str, request: dict) -> dict:
        if stage != "method_node" or request.get("protocol") != "lamina-stage-1":
            raise ValueError("expected a Lamina method request")
        data = request["input"]
        node = data["node"]["id"]
        self.latest_requests[node] = copy.deepcopy(request)
        if node == "reliability-read":
            return {"finding": data["task"]["reliability_notes"]}
        if node == "deployment-read":
            return {"finding": data["task"]["deployment_notes"]}
        if node == "incident-guide":
            cautions = [item["observation"]["note"] or item["observation"]["failure"]
                        for item in data["experience"]]
            return {"guide": " | ".join([
                data["dependencies"]["reliability-read"]["finding"],
                data["dependencies"]["deployment-read"]["finding"],
                *[text for text in cautions if text],
            ]), "audience": data["task"]["audience"]}
        raise ValueError(f"unknown fixture node {node}")


def _method() -> dict:
    return {
        "schema_version": "1", "family": "incident-guides",
        "id": "retry-incident-guide", "version": "1.0",
        "description": "Read reliability and deployment notes separately, then join them into an incident guide.",
        "applicability": {
            "contexts": ["A team has separate system and deployment notes for an incident."],
            "exclusions": ["A fixture does not verify the truth of supplied notes."],
            "limits": ["An operator must review the guide before operational use."],
        },
        "resources": {"workers": 2, "lanes": {"reading": 2, "editorial": 1}},
        "nodes": [
            {"id": "reliability-read", "role": "Reliability reader",
             "instructions": "Extract retry and lease behavior from the reliability notes.",
             "lane": "reading", "depends_on": [], "task_keys": ["reliability_notes"],
             "expected_shape": {"finding": "str"}, "input": {"focus": "retry and lease behavior"}},
            {"id": "deployment-read", "role": "Deployment reader",
             "instructions": "Extract the deployment constraint without assuming retry safety.",
             "lane": "reading", "depends_on": [], "task_keys": ["deployment_notes"],
             "expected_shape": {"finding": "str"}, "input": {"focus": "deployment constraint"}},
            {"id": "incident-guide", "role": "Incident guide editor",
             "instructions": "Combine the two findings. Treat selected operator observations as scoped cautions.",
             "lane": "editorial", "depends_on": ["reliability-read", "deployment-read"],
             "task_keys": ["audience"], "expected_shape": {"guide": "str", "audience": "str"},
             "input": {"form": "short incident guide"}},
        ],
    }


def method_demo() -> dict:
    """Return three real receipts and actual worker requests for inspection.

    A cached node retains the identical request captured when the fixture
    adapter last executed it; no imagined request is reconstructed for display.
    """
    initial = {"reliability_notes": "A lease expires after 60 seconds; a second worker may retry.",
               "deployment_notes": "Deployments restart the worker process after draining requests.",
               "audience": "on-call engineer"}
    revised = {**initial,
               "deployment_notes": "Deployments restart workers; a queued job may be reclaimed after restart."}
    method = _method()
    with tempfile.TemporaryDirectory(prefix="lamina-method-example-") as directory:
        workspace = Workspace(Path(directory))
        adapter = _FixtureAdapter()
        first = run_method(workspace, adapter, method, initial)
        first_requests = copy.deepcopy(adapter.latest_requests)
        second = run_method(workspace, adapter, method, revised)
        second_requests = copy.deepcopy(adapter.latest_requests)
        observation = record_observation(
            workspace, family=method["family"], method_id=method["id"],
            method_version=method["version"], task_digest=second["task_digest"],
            outcome="needs a caution", applicability="lease expiry and retry during deployment",
            failure="The guide could imply the first worker had stopped.",
            note="Lease expiry does not prove the original worker stopped; fence stale commits.")
        guided = copy.deepcopy(method)
        guided["version"] = "1.1"
        guided["nodes"][2]["observation_ids"] = [observation["observation_id"]]
        third = run_method(workspace, adapter, guided, revised)
        third_requests = copy.deepcopy(adapter.latest_requests)

    def request_sources(receipt: dict) -> dict[str, str]:
        return {nid: ("executed_in_this_run" if row["status"] == "executed" else
                      "reused_prior_request" if row["status"] == "cached" else "unavailable")
                for nid, row in receipt["nodes"].items()}
    return {
        "kind": "deterministic_offline_fixture",
        "explanation": "These are actual local method executions with a fixture adapter, not model-generated guidance or measured learning quality.",
        "method": guided,
        "task": {"initial": initial, "revised": revised},
        "observation": observation,
        "runs": [
            {"title": "Initial guide", "reason": "Two independent readers feed one guide editor.",
             "receipt": first, "requests": first_requests, "request_sources": request_sources(first)},
            {"title": "Deployment note changed", "reason": "The deployment reader and dependent editor rerun; the reliability reader is reused.",
             "receipt": second, "requests": second_requests, "request_sources": request_sources(second)},
            {"title": "Operator caution selected", "reason": "Only the guide editor receives the named observation and reruns.",
             "receipt": third, "requests": third_requests, "request_sources": request_sources(third)},
        ],
    }
