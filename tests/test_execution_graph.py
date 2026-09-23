"""Independent failure recovery, dependency scheduling and finite capacities."""

import threading
import time

import pytest

from lamina.execution import (
    DependencyGraph,
    bounded_collect,
    bounded_map,
    section_pipeline,
)
from lamina.method_runtime import run_method
from lamina.methods import validate_method
from lamina.store import Workspace


def node(nid, deps=(), lane="work"):
    return {
        "id": nid,
        "role": "worker",
        "instructions": "Return a result.",
        "lane": lane,
        "depends_on": list(deps),
        "input": {},
        "task_keys": [],
    }


def method(nodes, workers=4, lanes=None):
    return {
        "schema_version": "1",
        "family": "execution-tests",
        "id": "graph",
        "version": "1",
        "description": "Synthetic execution graph.",
        "applicability": {"contexts": ["Tests"], "exclusions": [], "limits": []},
        "resources": {"workers": workers, "lanes": lanes or {"work": workers}},
        "nodes": nodes,
    }


class Provider:
    identity = "graph-fixture"

    def __init__(self, fail=None, delay=0):
        self.fail, self.delay = fail, delay
        self.calls = []
        self.active = self.peak = 0
        self.lanes, self.lane_peaks = {}, {}
        self.lock = threading.Lock()

    def call(self, stage, payload):
        data = payload["input"]
        nid = data["node"]["id"]
        lane = data["node"]["input"].get("lane", "work")
        with self.lock:
            self.calls.append(data)
            self.active += 1
            self.peak = max(self.peak, self.active)
            self.lanes[lane] = self.lanes.get(lane, 0) + 1
            self.lane_peaks[lane] = max(self.lane_peaks.get(lane, 0), self.lanes[lane])
        try:
            time.sleep(self.delay)
            if nid == self.fail:
                raise ValueError("injected failure")
            return {"node": nid}
        finally:
            with self.lock:
                self.active -= 1
                self.lanes[lane] -= 1


def test_collect_runs_every_item_after_an_early_failure():
    observed = []

    def work(index):
        observed.append(index)
        if index in (0, 7):
            raise ValueError(f"failure {index}")
        return index * 2

    outcomes = bounded_collect(work, range(12), workers=1)
    assert observed == list(range(12))
    assert [x.index for x in outcomes] == list(range(12))
    assert [x.index for x in outcomes if not x.ok] == [0, 7]
    assert outcomes[11].value == 22
    observed.clear()
    with pytest.raises(ValueError, match="failure 0"):
        bounded_map(work, range(12), workers=1)
    assert observed == list(range(12))


def test_submission_is_bounded_and_values_keep_input_order():
    lock = threading.Lock()
    produced, finished = 0, 0

    def items():
        nonlocal produced
        for i in range(30):
            with lock:
                produced += 1
                assert produced - finished <= 3
            yield i

    def work(i):
        nonlocal finished
        time.sleep((3 - i % 3) * 0.001)
        with lock:
            finished += 1
        return i

    assert bounded_map(work, items(), workers=3) == list(range(30))


def test_graph_handles_deep_reverse_order_without_recursive_or_layer_scans():
    # A deep graph must be traversable without Python recursion. Each edge is
    # represented once in each direction; no transitive closures are built.
    nodes = [node(f"n{i}", [f"n{i-1}"] if i else []) for i in range(20000)]
    graph = DependencyGraph(list(reversed(nodes)))
    assert graph.topological == [f"n{i}" for i in range(20000)]
    assert graph.depth["n0"] == 20000
    assert sum(map(len, graph.children.values())) == 19999
    # Exercise the public validator at its declared graph-size limit, too.
    validated = validate_method(method(list(reversed(nodes[:1024]))))
    assert len(validated["nodes"]) == 1024
    nodes[0]["depends_on"] = ["n19999"]
    with pytest.raises(ValueError, match="cycle"):
        DependencyGraph(nodes)


def test_failed_root_skips_large_reverse_order_chain_but_runs_sibling(tmp_path):
    nodes = [node(f"n{i}", [f"n{i-1}"] if i else []) for i in range(1000)]
    nodes.reverse()
    nodes.append(node("sibling"))
    provider = Provider(fail="n0")
    receipt = run_method(Workspace(tmp_path), provider, method(nodes), {})
    assert receipt["status"] == "failed"
    assert receipt["nodes"]["n0"]["status"] == "failed"
    assert all(receipt["nodes"][f"n{i}"]["status"] == "skipped" for i in range(1, 1000))
    assert receipt["nodes"]["sibling"]["status"] == "executed"
    assert {call["node"]["id"] for call in provider.calls} == {"n0", "sibling"}
    assert list(receipt["nodes"]) == [n["id"] for n in nodes]


def test_graph_priority_starts_deeper_branch_and_preserves_declared_context(tmp_path):
    nodes = [
        node("leaf"),
        node("tail", ["middle"]),
        node("middle", ["root"]),
        node("root"),
    ]
    provider = Provider()
    receipt = run_method(Workspace(tmp_path), provider, method(nodes, workers=1), {})
    assert [call["node"]["id"] for call in provider.calls] == [
        "root",
        "middle",
        "leaf",
        "tail",
    ]
    assert {
        call["node"]["id"]: list(call["dependencies"]) for call in provider.calls
    } == {"root": [], "middle": ["root"], "leaf": [], "tail": ["middle"]}
    assert list(receipt["results"]) == [n["id"] for n in nodes]
    assert receipt["scheduling"]["priority"] == "remaining_dependency_depth"


def test_lane_capacity_never_blocks_other_available_lane(tmp_path):
    nodes = [node(f"a{i}", lane="slow") for i in range(5)] + [
        node(f"b{i}", lane="fast") for i in range(5)
    ]
    for item in nodes:
        item["input"] = {"lane": item["lane"]}
    provider = Provider(delay=0.015)
    receipt = run_method(
        Workspace(tmp_path),
        provider,
        method(nodes, workers=3, lanes={"slow": 1, "fast": 2}),
        {},
    )
    assert receipt["status"] == "completed"
    assert provider.peak <= 3
    assert provider.lane_peaks["slow"] == 1
    assert provider.lane_peaks["fast"] == 2
    assert receipt["scheduling"]["max_active"] == 3
    assert all(r["queue_ms"] >= 0 for r in receipt["nodes"].values())


def test_section_failure_leaves_unrelated_chains_free_to_finish():
    reviewed = []
    repaired = []

    def write(section):
        if section["id"] == "bad":
            raise ValueError("injected write failure")
        return {"id": section["id"], "repaired": False}

    def review(pair):
        section, draft = pair
        reviewed.append((section["id"], draft["repaired"]))
        return {"findings": [] if draft["repaired"] else ["repair this"]}

    def repair(args):
        section, draft, _ = args
        repaired.append(section["id"])
        return {**draft, "repaired": True}

    with pytest.raises(ValueError, match="injected write failure"):
        section_pipeline(
            [{"id": "bad"}, {"id": "one"}, {"id": "two"}],
            write,
            review,
            repair,
            workers=1,
            writers=1,
            reviewers=1,
        )
    assert repaired == ["one", "two"]
    assert reviewed == [("one", False), ("one", True), ("two", False), ("two", True)]


def test_section_pool_and_stage_capacities_are_shared():
    lock = threading.Lock()
    active = {"total": 0, "write": 0, "review": 0}
    peak = active.copy()

    def work(lane):
        with lock:
            for key in ("total", lane):
                active[key] += 1
                peak[key] = max(peak[key], active[key])
        time.sleep(0.004)
        with lock:
            for key in ("total", lane):
                active[key] -= 1

    def write(section):
        work("write")
        return {"id": section["id"], "repaired": False}

    def review(pair):
        work("review")
        return {"findings": [] if pair[1]["repaired"] else ["repair"]}

    def repair(args):
        work("write")
        return {**args[1], "repaired": True}

    result, initial, remaining = section_pipeline(
        [{"id": str(i)} for i in range(12)],
        write,
        review,
        repair,
        writers=2,
        reviewers=2,
        workers=3,
    )
    assert len(result) == len(initial) == 12
    assert not remaining
    assert peak["total"] <= 3 and peak["write"] <= 2 and peak["review"] <= 2
    assert [r["id"] for r in result] == list(map(str, range(12)))
