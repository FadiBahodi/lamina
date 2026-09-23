"""Bounded execution with explicit outcomes and dependency-aware scheduling."""

from __future__ import annotations

from collections import deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TaskResult:
    """One settled item; errors remain visible without discarding sibling work."""

    index: int
    value: Any = None
    error: Exception | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def _capacity(value: int, name: str) -> int:
    if type(value) is not int or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def bounded_collect(function, items, workers):
    """Settle every item, retaining ordered results and exceptions.

    At most ``workers`` futures are submitted at once. A failed item does not
    prevent independent items from executing and saving their cached results.
    KeyboardInterrupt and other BaseExceptions still interrupt the operation.
    """
    _capacity(workers, "workers")
    iterator = iter(enumerate(items))
    results = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending = {}

        def fill():
            while len(pending) < workers:
                try:
                    index, item = next(iterator)
                except StopIteration:
                    break
                pending[pool.submit(function, item)] = index

        fill()
        while pending:
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                index = pending.pop(future)
                try:
                    results[index] = TaskResult(index, value=future.result())
                except Exception as exc:
                    results[index] = TaskResult(index, error=exc)
            fill()
    return [results[i] for i in range(len(results))]


def bounded_map(function, items, workers):
    """Return input order; finish independent work before raising an item error."""
    outcomes = bounded_collect(function, items, workers)
    for outcome in outcomes:
        if outcome.error is not None:
            raise outcome.error
    return [outcome.value for outcome in outcomes]


class DependencyGraph:
    """Build adjacency, validate acyclicity and rank remaining graph depth.

    Construction touches each node and edge a fixed number of times: O(V + E).
    Remaining depth is a structural priority, not a prediction of call duration.
    """

    def __init__(self, nodes):
        self.children = {node["id"]: [] for node in nodes}
        self.indegree = {node["id"]: len(node["depends_on"]) for node in nodes}
        for node in nodes:
            for parent in node["depends_on"]:
                if parent not in self.children:
                    raise ValueError(f"{node['id']} has an unknown dependency")
                self.children[parent].append(node["id"])
        remaining = self.indegree.copy()
        ready = deque(nid for nid, count in remaining.items() if count == 0)
        self.topological = []
        while ready:
            nid = ready.popleft()
            self.topological.append(nid)
            for child in self.children[nid]:
                remaining[child] -= 1
                if remaining[child] == 0:
                    ready.append(child)
        if len(self.topological) != len(remaining):
            raise ValueError("method dependency graph has a cycle")
        self.depth = {}
        for nid in reversed(self.topological):
            self.depth[nid] = 1 + max(
                (self.depth[child] for child in self.children[nid]), default=0
            )


def section_pipeline(sections, write, review, repair, *, writers, reviewers, workers):
    """Schedule write → review → optional repair → recheck per section.

    One shared pool and stage ceilings bound running calls. Eligible follow-up
    work precedes fresh writing; FIFO within each lane prevents newer follow-ups
    from overtaking older ones. Failures leave other sections free to finish and
    cache their work; the first failed section is raised after the pool settles.
    """
    for name, value in (
        ("workers", workers),
        ("writers", writers),
        ("reviewers", reviewers),
    ):
        _capacity(value, name)
    fresh = iter(enumerate(sections))
    ready = {"write": deque(), "review": deque()}
    pending, output, initial, remaining, errors = {}, {}, {}, {}, {}
    occupied = {"write": 0, "review": 0}
    capacity = {"write": writers, "review": reviewers}
    exhausted = False
    sequence = 0

    def enqueue(job):
        nonlocal sequence
        lane = "write" if job[1] == "repair" else "review"
        ready[lane].append((sequence, job))
        sequence += 1

    with ThreadPoolExecutor(max_workers=workers) as pool:
        while pending or any(ready.values()) or not exhausted:
            while len(pending) < workers:
                eligible = [
                    lane
                    for lane in ready
                    if ready[lane] and occupied[lane] < capacity[lane]
                ]
                job = None
                if eligible:
                    lane = min(eligible, key=lambda lane: ready[lane][0][0])
                    _, job = ready[lane].popleft()
                elif not exhausted and occupied["write"] < writers:
                    try:
                        index, section = next(fresh)
                        job = (index, "write", section, None, None)
                    except StopIteration:
                        exhausted = True
                if job is None:
                    break
                index, stage, section, draft, findings = job
                lane = "write" if stage in {"write", "repair"} else "review"
                fn, arg = (
                    (write, section)
                    if stage == "write"
                    else (
                        (repair, (section, draft, findings))
                        if stage == "repair"
                        else (review, (section, draft))
                    )
                )
                pending[pool.submit(fn, arg)] = job
                occupied[lane] += 1
            if not pending:
                if any(ready.values()):
                    raise RuntimeError("section scheduler cannot advance")
                continue
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                index, stage, section, draft, findings = pending.pop(future)
                occupied["write" if stage in {"write", "repair"} else "review"] -= 1
                try:
                    result = future.result()
                except Exception as exc:
                    errors[index] = exc
                    continue
                if stage in {"write", "repair"}:
                    enqueue(
                        (
                            index,
                            "review" if stage == "write" else "recheck",
                            section,
                            result,
                            None,
                        )
                    )
                elif stage == "review" and result["findings"]:
                    initial[section["id"]] = result["findings"]
                    enqueue((index, "repair", section, draft, result["findings"]))
                else:
                    output[index] = draft
                    if result["findings"]:
                        remaining[section["id"]] = result["findings"]
    if errors:
        error = errors[min(errors)]
        error.partial_results = {
            "completed_sections": [output[i] for i in sorted(output)],
            "initial_findings": initial,
            "findings": remaining,
            "failed_sections": [
                {"section_id": sections[i]["id"], "error": str(exc)}
                for i, exc in sorted(errors.items())
            ],
        }
        raise error
    return [output[i] for i in range(len(output))], initial, remaining
