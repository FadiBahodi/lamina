"""Matched finite-capacity executor measurements with synthetic service times.

Run: PYTHONPATH=src python benchmarks/execution_scaling.py --output results.json
The delays and failures below are assumptions. This measures local scheduling;
it does not measure a model, token pricing, provider quotas or artifact quality.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from lamina.execution import DependencyGraph, bounded_collect, section_pipeline


@dataclass(frozen=True)
class Case:
    id: str
    delays: dict[str, float]
    flagged: bool
    failure: str | None


def cases(count, seed, failure_rate, scale):
    rng = random.Random(seed)
    output = []
    medians = {"write": 20, "review": 8, "repair": 18, "recheck": 8}
    for index in range(count):
        delays = {
            stage: rng.lognormvariate(math.log(median), 0.7) * scale
            for stage, median in medians.items()
        }
        flagged = rng.random() < 0.4
        eligible = list(medians) if flagged else ["write", "review"]
        failure = rng.choice(eligible) if rng.random() < failure_rate else None
        output.append(Case(str(index), delays, flagged, failure))
    return output


class Service:
    def __init__(self, items):
        self.items = {item.id: item for item in items}
        self.calls = []
        self.finished = {}
        self.started = time.monotonic()
        self.lock = threading.Lock()
        self.active = self.peak = 0

    def perform(self, section, stage):
        item = self.items[section["id"]]
        began = time.monotonic()
        with self.lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
        try:
            time.sleep(item.delays[stage])
            if item.failure == stage:
                raise RuntimeError(f"injected {stage} failure for {item.id}")
        finally:
            ended = time.monotonic()
            with self.lock:
                self.active -= 1
                self.calls.append(
                    {
                        "section": item.id,
                        "stage": stage,
                        "start_s": began - self.started,
                        "end_s": ended - self.started,
                        "elapsed_s": ended - began,
                        "assumed_service_s": item.delays[stage],
                        "failed": item.failure == stage,
                    }
                )
                if item.failure == stage:
                    self.finished[item.id] = {
                        "status": "failed",
                        "at_s": ended - self.started,
                    }

    def write(self, section):
        self.perform(section, "write")
        return {"id": section["id"], "repaired": False}

    def review(self, pair):
        section, draft = pair
        stage = "recheck" if draft["repaired"] else "review"
        self.perform(section, stage)
        findings = (
            ["injected finding"]
            if self.items[section["id"]].flagged and stage == "review"
            else []
        )
        if not findings:
            with self.lock:
                self.finished[section["id"]] = {
                    "status": "completed",
                    "at_s": time.monotonic() - self.started,
                }
        return {"findings": findings}

    def repair(self, args):
        section, draft, findings = args
        self.perform(section, "repair")
        return {**draft, "repaired": True}


def barriers(rows, service, workers, writers, reviewers):
    drafts = bounded_collect(service.write, rows, min(workers, writers))
    review_args = [(rows[result.index], result.value) for result in drafts if result.ok]
    reviews = bounded_collect(service.review, review_args, min(workers, reviewers))
    repair_args = [
        (*review_args[result.index], result.value["findings"])
        for result in reviews
        if result.ok and result.value["findings"]
    ]
    repaired = bounded_collect(service.repair, repair_args, min(workers, writers))
    recheck_args = [
        (repair_args[result.index][0], result.value) for result in repaired if result.ok
    ]
    bounded_collect(service.review, recheck_args, min(workers, reviewers))


def run(items, policy, *, workers, writers, reviewers):
    rows = [{"id": item.id} for item in items]
    service = Service(items)
    if policy == "barriers":
        barriers(rows, service, workers, writers, reviewers)
    else:
        try:
            section_pipeline(
                rows,
                service.write,
                service.review,
                service.repair,
                workers=workers,
                writers=writers,
                reviewers=reviewers,
            )
        except RuntimeError as exc:
            if not str(exc).startswith("injected "):
                raise
    wall = time.monotonic() - service.started
    assert len(service.finished) == len(items), "independent work was abandoned"
    stage_metrics = {}
    for stage in ("write", "review", "repair", "recheck"):
        calls = [call for call in service.calls if call["stage"] == stage]
        stage_metrics[stage] = {
            "calls": len(calls),
            "failed": sum(call["failed"] for call in calls),
            "service_ms": round(sum(call["elapsed_s"] for call in calls) * 1000, 3),
            "first_start_ms": round(
                min((call["start_s"] for call in calls), default=0) * 1000, 3
            ),
            "last_finish_ms": round(
                max((call["end_s"] for call in calls), default=0) * 1000, 3
            ),
        }
    completed_at = [
        row["at_s"] for row in service.finished.values() if row["status"] == "completed"
    ]
    return {
        "wall_ms": round(wall * 1000, 3),
        "first_accepted_section_ms": (
            round(min(completed_at) * 1000, 3) if completed_at else None
        ),
        "total_service_ms": round(
            sum(call["elapsed_s"] for call in service.calls) * 1000, 3
        ),
        "assumed_work_ms": round(
            sum(call["assumed_service_s"] for call in service.calls) * 1000, 3
        ),
        "calls": len(service.calls),
        "peak_active": service.peak,
        "outcomes": {
            key: service.finished[key]["status"] for key in sorted(service.finished)
        },
        "stages": stage_metrics,
    }


def graph_scaling():
    """Measure only graph indexing/validation, excluding model and DB work."""
    rows = []
    for count in (128, 256, 512, 1024, 2048):
        nodes = [
            {"id": str(i), "depends_on": [str(i - 1)] if i else []}
            for i in reversed(range(count))
        ]
        before = time.perf_counter()
        pending = {node["id"]: set(node["depends_on"]) for node in nodes}
        reached, examined = set(), 0
        while pending:
            examined += len(pending)
            ready = {
                nid for nid, dependencies in pending.items() if dependencies <= reached
            }
            assert ready
            reached |= ready
            for nid in ready:
                del pending[nid]
        previous_ms = (time.perf_counter() - before) * 1000
        before = time.perf_counter()
        graph = DependencyGraph(nodes)
        indexed_ms = (time.perf_counter() - before) * 1000
        assert len(graph.topological) == count
        rows.append(
            {
                "nodes": count,
                "edges": count - 1,
                "previous_validation_candidate_checks": examined,
                "previous_validation_ms": round(previous_ms, 3),
                "indexed_validation_and_depth_ms": round(indexed_ms, 3),
            }
        )
    return {
        "workload": "synthetic chain declared in reverse order",
        "scope": "previous repeated readiness scan versus adjacency construction, topological validation and remaining-depth calculation; excludes method shape validation and execution",
        "rows": rows,
    }


def benchmark(repeats=3, scale=0.001):
    scenarios = [
        {
            "name": "variable_calls",
            "count": 32,
            "workers": 8,
            "writers": 8,
            "reviewers": 8,
            "failure_rate": 0,
        },
        {
            "name": "one_worker",
            "count": 16,
            "workers": 1,
            "writers": 1,
            "reviewers": 1,
            "failure_rate": 0,
        },
        {
            "name": "review_capacity_one",
            "count": 32,
            "workers": 8,
            "writers": 8,
            "reviewers": 1,
            "failure_rate": 0,
        },
        {
            "name": "finite_pool_tradeoff",
            "count": 4,
            "workers": 2,
            "writers": 2,
            "reviewers": 2,
            "failure_rate": 0,
        },
        {
            "name": "independent_failures",
            "count": 32,
            "workers": 8,
            "writers": 8,
            "reviewers": 8,
            "failure_rate": 0.15,
        },
    ]
    results = []
    for scenario in scenarios:
        comparisons = []
        for repeat in range(repeats):
            seed = 729 + repeat
            items = cases(scenario["count"], seed, scenario["failure_rate"], scale)
            if scenario["name"] == "finite_pool_tradeoff":
                # Exact finite-pool counterexample in the zero-overhead model:
                # write [1,1,1,1], review [1,5,1,5], two workers, no repairs.
                # Barriers finish at 9; follow-up-first chains finish at 10.
                items = [
                    Case(
                        str(i),
                        {"write": 20 * scale, "review": review * 20 * scale},
                        False,
                        None,
                    )
                    for i, review in enumerate((1, 5, 1, 5))
                ]
            config = {key: scenario[key] for key in ("workers", "writers", "reviewers")}
            # Alternate run order to reduce systematic warm-up/order bias.
            policies = (
                ("barriers", "chains") if repeat % 2 == 0 else ("chains", "barriers")
            )
            measured = {policy: run(items, policy, **config) for policy in policies}
            before, after = measured["barriers"], measured["chains"]
            assert before["outcomes"] == after["outcomes"]
            assert before["calls"] == after["calls"]
            assert before["assumed_work_ms"] == after["assumed_work_ms"]
            comparisons.append(
                {
                    "seed": seed,
                    **measured,
                    "wall_ratio": round(before["wall_ms"] / after["wall_ms"], 4),
                }
            )
        ratios = [row["wall_ratio"] for row in comparisons]
        results.append(
            {
                **scenario,
                "comparisons": comparisons,
                "wall_ratio_median": round(statistics.median(ratios), 4),
                "wall_ratio_min": min(ratios),
                "wall_ratio_max": max(ratios),
            }
        )
    return {
        "kind": "synthetic_local_executor_measurement",
        "reproduce": "PYTHONPATH=src python benchmarks/execution_scaling.py --output results.json",
        "assumptions": {
            "service_distribution": "independent lognormal calls, sigma=0.7; finite_pool_tradeoff uses explicit durations",
            "unscaled_stage_medians_seconds": {
                "write": 20,
                "review": 8,
                "repair": 18,
                "recheck": 8,
            },
            "sleep_scale": scale,
            "flag_probability": 0.4,
            "repeats": repeats,
            "failures": "seeded stage failures; successful siblings finish under both policies",
            "capacity": "same finite shared pool and same per-stage ceilings in each comparison",
        },
        "interpretation": "Ratios compare these sampled service times and capacities. A one-worker run has equal useful work; scheduling overhead can make chains slower. The unlimited-worker maximum-of-sums bound does not establish a finite-pool guarantee.",
        "limits": "No live models, token costs, network quotas, provider retry delays or semantic output quality are measured.",
        "graph_scaling": graph_scaling(),
        "scenarios": results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--scale", type=float, default=0.001)
    args = parser.parse_args()
    if args.repeats < 1 or args.scale <= 0:
        parser.error("repeats and scale must be positive")
    result = benchmark(args.repeats, args.scale)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {
                "kind": result["kind"],
                "scenarios": [
                    {
                        key: row[key]
                        for key in (
                            "name",
                            "wall_ratio_median",
                            "wall_ratio_min",
                            "wall_ratio_max",
                        )
                    }
                    for row in result["scenarios"]
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
