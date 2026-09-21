"""Measure the deterministic method fixture; never report model performance.

From the repository root:
    .venv/bin/python benchmarks/run_method_example.py
"""
from __future__ import annotations

import argparse
import json
import math
import platform
import re
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from lamina.method_example import method_demo


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "docs/experiments/current-runtime.json"
NODES = ("reliability-read", "deployment-read", "incident-guide")
STEPS = ("Initial guide", "Deployment note changed", "Operator caution selected")
EXPECTED = (
    ("executed", "executed", "executed"),
    ("cached", "executed", "executed"),
    ("cached", "cached", "executed"),
)


def _nearest_rank(values: list[float], fraction: float) -> float:
    """Nearest-rank quantile: sorted values[ceil(fraction * n) - 1]."""
    ordered = sorted(values)
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]


def _verify(example: dict) -> None:
    assert example["kind"] == "deterministic_offline_fixture"
    assert len(example["runs"]) == 3
    observation_id = example["observation"]["observation_id"]
    for index, (entry, expected) in enumerate(zip(example["runs"], EXPECTED, strict=True)):
        assert entry["title"] == STEPS[index]
        receipt = entry["receipt"]
        assert receipt["status"] == "completed"
        assert tuple(receipt["nodes"][node]["status"] for node in NODES) == expected
        assert set(entry["requests"]) == set(NODES)
        for node in NODES:
            request = entry["requests"][node]
            assert request["protocol"] == "lamina-stage-1"
            assert request["stage"] == "method_node"
            assert request["input"]["node"]["id"] == node
            assert entry["request_sources"][node] == (
                "executed_in_this_run" if expected[NODES.index(node)] == "executed"
                else "reused_prior_request")
            if node != "incident-guide":
                assert request["input"]["dependencies"] == {}
                assert request["input"]["experience"] == []
        editor = entry["requests"]["incident-guide"]["input"]
        assert set(editor["dependencies"]) == set(NODES[:2])
        assert set(editor["task"]) == {"audience"}
        if index < 2:
            assert editor["experience"] == []
            assert receipt["nodes"]["incident-guide"]["observation_ids"] == []
        else:
            assert len(editor["experience"]) == 1
            selected = editor["experience"][0]
            assert selected["kind"] == "operator_observation"
            assert selected["observation"]["observation_id"] == observation_id
            assert selected["observation"]["family"] == example["method"]["family"]
            assert receipt["nodes"]["incident-guide"]["observation_ids"] == [observation_id]
            assert selected["observation"]["note"] in receipt["results"]["incident-guide"]["guide"]
        assert receipt["wall_ms"] >= 0
    assert example["runs"][0]["requests"]["reliability-read"] == example["runs"][1]["requests"]["reliability-read"]
    assert example["runs"][1]["requests"]["deployment-read"] == example["runs"][2]["requests"]["deployment-read"]
    assert example["runs"][1]["receipt"]["results"]["incident-guide"] != example["runs"][2]["receipt"]["results"]["incident-guide"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=10)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if not 2 <= args.repeats <= 100:
        parser.error("--repeats must be 2..100")

    test_command = [sys.executable, "-m", "unittest", "tests.test_method_runtime", "-q"]
    test = subprocess.run(test_command, cwd=ROOT, capture_output=True, text=True, check=False)
    if test.returncode:
        raise RuntimeError(f"method tests failed:\n{test.stdout}{test.stderr}")
    match = re.search(r"Ran (\d+) tests", test.stdout + test.stderr)
    if not match:
        raise RuntimeError("method test runner did not report a test count")

    samples = {step: [] for step in STEPS}
    first_example = None
    for _ in range(args.repeats):
        example = method_demo()  # each call creates its own fresh temporary workspace
        _verify(example)
        if first_example is None:
            first_example = example
        for entry in example["runs"]:
            samples[entry["title"]].append(entry["receipt"]["wall_ms"])

    assert first_example is not None
    result = {
        "schema_version": "1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "experiment": "deterministic_offline_method_fixture",
        "reproduce": ".venv/bin/python benchmarks/run_method_example.py",
        "python_version": platform.python_version(),
        "repetitions": args.repeats,
        "workspace_policy": "fresh temporary local workspace for each three-run sequence",
        "fixture_adapter": "incident-guide-fixture-v1; no model or network call",
        "tests": {"command": "python -m unittest tests.test_method_runtime -q",
                  "exit_code": test.returncode, "count": int(match.group(1))},
        "verification": {
            "checked_repetitions": args.repeats,
            "all_expected_node_status_patterns": True,
            "all_requests_captured_or_identically_reused": True,
            "all_dependency_contexts_scoped": True,
            "all_selected_observations_same_family_and_only_on_final_editor": True,
            "all_final_guides_changed_by_selected_observation": True,
        },
        "timing": {
            "unit": "milliseconds", "source": "run_method receipt wall_ms from time.monotonic",
            "quantile": "nearest-rank p95 = sorted sample at ceil(0.95 * n) - 1; for n=10 this is the maximum",
            "steps": {step: {"samples_ms": values,
                             "median_ms": round(statistics.median(values), 3),
                             "p95_ms": round(_nearest_rank(values, 0.95), 3)}
                      for step, values in samples.items()},
        },
        "outcomes": {
            "nodes": list(NODES),
            "expected_status_by_step": {step: list(statuses) for step, statuses in zip(STEPS, EXPECTED, strict=True)},
            "verified_sequence_count": args.repeats,
            "sample_guides": {entry["title"]: entry["receipt"]["results"]["incident-guide"]["guide"]
                              for entry in first_example["runs"]},
        },
        "limits": [
            "Deterministic fixture tests orchestration and cache behavior, not semantic quality.",
            "Wall times measure local fixture calls and SQLite overhead, not LLM latency or production speed.",
            "No token, provider cost, source comprehension, learner outcome, or delivery measure is collected.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "repetitions": args.repeats,
                      "tests": result["tests"],
                      "median_ms": {step: data["median_ms"] for step, data in result["timing"]["steps"].items()}},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
