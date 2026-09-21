"""Behavioral checks for reusable methods, scheduling, and local experience."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from lamina.method_runtime import list_experience, list_runs, record_observation, run_method
from lamina.method_example import method_demo
from lamina.methods import validate_method
from lamina.store import Workspace


EXAMPLE = Path(__file__).resolve().parents[1] / "examples/methods/field-guide.json"


def garden() -> dict:
    return json.loads(EXAMPLE.read_text())


class CountingProvider:
    identity = "fixture-v1"

    def __init__(self, *, delay: float = 0, fail: str | None = None):
        self.delay = delay
        self.fail = fail
        self.calls = []
        self.active = 0
        self.peak = 0
        self.lock = threading.Lock()

    def call(self, stage: str, payload: dict) -> dict:
        assert stage == payload["stage"] == "method_node"
        assert payload["protocol"] == "lamina-stage-1"
        data = payload["input"]
        nid = data["node"]["id"]
        with self.lock:
            self.calls.append(copy.deepcopy(payload))
            self.active += 1
            self.peak = max(self.peak, self.active)
        try:
            time.sleep(self.delay)
            if nid == self.fail:
                raise RuntimeError("fixture failure")
            return {"text": nid + " " + json.dumps(data["task"], sort_keys=True),
                    "upstream": sorted(data["dependencies"])}
        finally:
            with self.lock:
                self.active -= 1


class ExperienceProvider(CountingProvider):
    def call(self, stage: str, payload: dict) -> dict:
        data = payload["input"]
        with self.lock:
            self.calls.append(copy.deepcopy(payload))
        if data["node"]["id"] == "guide":
            return {"guide": " | ".join([str(data["dependencies"]),
                    *[item["observation"]["note"] for item in data["experience"]]])}
        return {"finding": next(iter(data["task"].values()))}


class MethodTests(unittest.TestCase):
    def test_validation_rejects_unknown_cycle_duplicate_and_resource_errors(self):
        base = garden()
        self.assertEqual(len(validate_method(base)["nodes"]), 3)
        bad = copy.deepcopy(base)
        bad["nodes"][1]["id"] = "site-read"
        with self.assertRaisesRegex(ValueError, "duplicate node"):
            validate_method(bad)
        bad = copy.deepcopy(base)
        bad["nodes"][0]["depends_on"] = ["missing"]
        with self.assertRaisesRegex(ValueError, "unknown dependency"):
            validate_method(bad)
        bad = copy.deepcopy(base)
        bad["nodes"][0]["depends_on"] = ["guide"]
        with self.assertRaisesRegex(ValueError, "cycle"):
            validate_method(bad)
        bad = copy.deepcopy(base)
        bad["resources"]["lanes"]["reading"] = 4
        with self.assertRaisesRegex(ValueError, "capacity"):
            validate_method(bad)
        bad = copy.deepcopy(base)
        bad["nodes"][0]["command"] = "python"
        with self.assertRaisesRegex(ValueError, "each node needs"):
            validate_method(bad)
        reference = copy.deepcopy(base)
        reference["nodes"][0]["input"]["model_explanation"] = "See https://example.org/model and ./notes.md"
        self.assertIn("model_explanation", validate_method(reference)["nodes"][0]["input"])
        bad = copy.deepcopy(base)
        bad["nodes"][0]["observation_ids"] = ["a" * 32, "a" * 32]
        with self.assertRaisesRegex(ValueError, "observation_ids"):
            validate_method(bad)

    def test_parallel_siblings_bounded_and_dependency_context_explicit(self):
        with tempfile.TemporaryDirectory() as temp:
            method = garden()
            provider = CountingProvider(delay=0.08)
            task = {"site_notes": "shade", "plant_notes": "mint", "audience": "helpers",
                    "private_unused": "must not reach workers"}
            receipt = run_method(Workspace(Path(temp)), provider, method, task)
            self.assertEqual(receipt["status"], "completed")
            self.assertEqual(provider.peak, 2)
            self.assertEqual(len(provider.calls), 3)
            by_id = {x["input"]["node"]["id"]: x for x in provider.calls}
            self.assertEqual(by_id["site-read"]["input"]["task"], {"site_notes": "shade"})
            self.assertEqual(by_id["plant-read"]["input"]["task"], {"plant_notes": "mint"})
            self.assertEqual(by_id["site-read"]["input"]["dependencies"], {})
            self.assertEqual(set(by_id["guide"]["input"]["dependencies"]), {"site-read", "plant-read"})
            self.assertEqual(by_id["site-read"]["expected_shape"], {"finding": "str"})
            self.assertNotIn("private_unused", str(provider.calls))
            self.assertGreater(receipt["nodes"]["guide"]["context_bytes"], 0)

    def test_restart_and_branch_change_reuse_only_unaffected_results(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            method = garden()
            task = {"site_notes": "shade", "plant_notes": "mint", "audience": "helpers"}
            first_provider = CountingProvider()
            first = run_method(Workspace(root), first_provider, method, task)
            self.assertEqual(len(first_provider.calls), 3)
            second_provider = CountingProvider()
            second = run_method(Workspace(root), second_provider, method, task)
            self.assertEqual(len(second_provider.calls), 0)
            self.assertTrue(all(row["status"] == "cached" for row in second["nodes"].values()))
            changed = {**task, "site_notes": "sun"}
            third = run_method(Workspace(root), second_provider, method, changed)
            self.assertEqual([x["input"]["node"]["id"] for x in second_provider.calls], ["site-read", "guide"])
            self.assertEqual(third["nodes"]["plant-read"]["status"], "cached")
            revision = copy.deepcopy(method)
            revision["version"] = "1.1"
            revision["nodes"][0]["instructions"] += " Mention access."
            fourth_provider = CountingProvider()
            fourth = run_method(Workspace(root), fourth_provider, revision, changed)
            # The fixture returns the same site result after an instruction
            # edit, so downstream inputs remain identical and stay cached.
            self.assertEqual([x["input"]["node"]["id"] for x in fourth_provider.calls], ["site-read"])
            self.assertEqual(fourth["nodes"]["plant-read"]["status"], "cached")
            self.assertEqual(fourth["nodes"]["guide"]["status"], "cached")
            self.assertEqual(len(list_runs(Workspace(root), "field-guides")), 4)

    def test_failure_keeps_sibling_and_cached_work_for_retry(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Workspace(Path(temp))
            task = {"site_notes": "shade", "plant_notes": "mint", "audience": "helpers"}
            broken = CountingProvider(fail="plant-read")
            first = run_method(workspace, broken, garden(), task)
            self.assertEqual(first["status"], "failed")
            self.assertEqual(first["nodes"]["site-read"]["status"], "executed")
            self.assertEqual(first["nodes"]["guide"]["status"], "skipped")
            fixed = CountingProvider()
            second = run_method(workspace, fixed, garden(), task)
            self.assertEqual(second["status"], "completed")
            self.assertEqual(second["nodes"]["site-read"]["status"], "cached")
            self.assertEqual([x["input"]["node"]["id"] for x in fixed.calls], ["plant-read", "guide"])

    def test_cli_command_adapter_uses_standard_stage_envelope(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            adapter = root / "adapter.py"
            adapter.write_text(
                "import json,sys\n"
                "p=json.load(sys.stdin)\n"
                "assert p['protocol']=='lamina-stage-1'\n"
                "assert p['stage']=='method_node'\n"
                "assert p['instruction'] and p['expected_shape']\n"
                "d=p['input']; n=d['node']['id']\n"
                "assert set(d['dependencies'])==({'site-read','plant-read'} if n=='guide' else set())\n"
                "print(json.dumps({'result':n}))\n", encoding="utf-8")
            task = root / "task.json"
            task.write_text(json.dumps({"site_notes": "shade", "plant_notes": "mint",
                                        "audience": "helpers"}), encoding="utf-8")
            command = [sys.executable, "-m", "lamina", "method", "run",
                       "--method", str(EXAMPLE), "--task", str(task),
                       "--workspace", str(root / "workspace"),
                       "--adapter", f"{sys.executable} {adapter}"]
            run = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(run.returncode, 0, run.stderr)
            receipt = json.loads(run.stdout)
            self.assertEqual(receipt["status"], "completed")
            self.assertEqual(receipt["results"]["guide"], {"result": "guide"})

    def test_experience_is_human_supplied_and_family_scoped(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Workspace(Path(temp))
            self.assertEqual(list_experience(workspace, "field-guides"), [])
            observation = record_observation(
                workspace, family="field-guides", method_id="community-garden-visit",
                method_version="1.0", task_digest="abc", outcome="useful with edits",
                applicability="worked for two short note sets", failure="missed a path closure")
            self.assertEqual(observation["failure"], "missed a path closure")
            self.assertEqual(len(list_experience(Workspace(Path(temp)), "field-guides")), 1)
            self.assertEqual(list_experience(workspace, "other-family"), [])

    def test_selected_observation_changes_only_consumer_and_missing_or_wrong_family_fails_early(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Workspace(Path(temp))
            method = garden()
            task = {"site_notes": "shade", "plant_notes": "mint", "audience": "helpers"}
            provider = ExperienceProvider()
            first = run_method(workspace, provider, method, task)
            self.assertEqual(len(provider.calls), 3)
            selected = record_observation(
                workspace, family="field-guides", method_id=method["id"],
                method_version="1.0", task_digest=first["task_digest"],
                outcome="needs correction", applicability="shade garden",
                note="Check the north gate before entry.")
            guided = copy.deepcopy(method)
            guided["version"] = "1.1"
            guided["nodes"][2]["observation_ids"] = [selected["observation_id"]]
            provider.calls.clear()
            second = run_method(workspace, provider, guided, task)
            self.assertEqual([call["input"]["node"]["id"] for call in provider.calls], ["guide"])
            self.assertIn("Check the north gate", second["results"]["guide"]["guide"])
            self.assertEqual(second["nodes"]["guide"]["observation_ids"], [selected["observation_id"]])
            self.assertEqual(second["nodes"]["site-read"]["status"], "cached")
            self.assertEqual(second["nodes"]["plant-read"]["status"], "cached")
            self.assertEqual(provider.calls[0]["input"]["experience"][0]["kind"], "operator_observation")
            record_observation(workspace, family="field-guides", method_id=method["id"],
                               method_version="1.1", task_digest=first["task_digest"],
                               outcome="unselected", applicability="other garden", note="Unselected note")
            provider.calls.clear()
            third = run_method(workspace, provider, guided, task)
            self.assertEqual(provider.calls, [])
            self.assertEqual(third["nodes"]["guide"]["status"], "cached")
            with workspace.connection() as db:
                db.execute("UPDATE method_observations SET note=? WHERE observation_id=?",
                           ("Check both gates.", selected["observation_id"]))
            fourth = run_method(workspace, provider, guided, task)
            self.assertEqual([call["input"]["node"]["id"] for call in provider.calls], ["guide"])
            self.assertIn("Check both gates.", fourth["results"]["guide"]["guide"])
            wrong = record_observation(workspace, family="other-family", method_id="other",
                                       method_version="1", task_digest="other", outcome="x",
                                       applicability="other", note="Wrong family")
            bad = copy.deepcopy(guided)
            bad["nodes"][2]["observation_ids"] = [wrong["observation_id"]]
            provider.calls.clear()
            with self.assertRaisesRegex(ValueError, "another family"):
                run_method(workspace, provider, bad, task)
            self.assertEqual(provider.calls, [])
            bad["nodes"][2]["observation_ids"] = ["f" * 32]
            with self.assertRaisesRegex(ValueError, "unknown method observations"):
                run_method(workspace, provider, bad, task)
            self.assertEqual(provider.calls, [])

    def test_packaged_example_shows_explicit_observation_consumer(self):
        example = method_demo()
        self.assertEqual(example["kind"], "deterministic_offline_fixture")
        first, second, third = [entry["receipt"] for entry in example["runs"]]
        self.assertEqual([first["nodes"][key]["status"] for key in ("reliability-read", "deployment-read", "incident-guide")],
                         ["executed", "executed", "executed"])
        self.assertEqual([second["nodes"][key]["status"] for key in ("reliability-read", "deployment-read", "incident-guide")],
                         ["cached", "executed", "executed"])
        self.assertEqual([third["nodes"][key]["status"] for key in ("reliability-read", "deployment-read", "incident-guide")],
                         ["cached", "cached", "executed"])
        self.assertIn("Lease expiry does not prove", third["results"]["incident-guide"]["guide"])


if __name__ == "__main__":
    unittest.main()
