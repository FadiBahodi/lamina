"""Offline scheduling demonstration; responses are a fixture, not model output.

Run with ``PYTHONPATH=src python examples/methods/demo.py`` from the repo root.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from lamina.method_runtime import run_method
from lamina.store import Workspace


class FixtureAdapter:
    identity = "garden-fixture-v1"

    def call(self, stage: str, payload: dict) -> dict:
        if stage != "method_node" or payload.get("protocol") != "lamina-stage-1":
            raise ValueError(stage)
        data = payload["input"]
        nid = data["node"]["id"]
        if nid == "site-read":
            return {"finding": "Site: " + data["task"]["site_notes"]}
        if nid == "plant-read":
            return {"finding": "Plants: " + data["task"]["plant_notes"]}
        return {"guide": " | ".join(x["finding"] for x in data["dependencies"].values()),
                "audience": data["task"]["audience"]}


if __name__ == "__main__":
    method = json.loads(Path(__file__).with_name("field-guide.json").read_text())
    with tempfile.TemporaryDirectory() as temp:
        workspace = Workspace(Path(temp))
        provider = FixtureAdapter()
        task = {"site_notes": "morning shade, one tap", "plant_notes": "tomatoes and mint",
                "audience": "Saturday volunteers"}
        first = run_method(workspace, provider, method, task)
        changed = {**task, "site_notes": "afternoon shade, one tap"}
        second = run_method(workspace, provider, method, changed)
        third = run_method(workspace, provider, method,
                           {"site_notes": "full sun, rain barrel", "plant_notes": "beans",
                            "audience": "new volunteers"})
        for label, receipt in (("first", first), ("changed site", second), ("new task", third)):
            print(label, {nid: row["status"] for nid, row in receipt["nodes"].items()},
                  receipt["results"]["guide"])
