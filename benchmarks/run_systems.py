#!/usr/bin/env python3
"""Measure Lamina's real SQLite job cache with explicitly synthetic wait work.

No model, document ingestion, audio, or network call is performed. The stage
graph has parallel extraction, two serial global stages, then independent
author->review chains, matching the main pipeline's dependency shape.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import platform
import sqlite3
import sys
import tempfile
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lamina.store import Workspace  # noqa: E402


DEFAULT_DELAYS = {"extract": 0.05, "reconcile": 0.12, "plan": 0.12,
                  "author": 0.08, "review": 0.04}


class CounterClock:
    """Track handler occupancy; cached reads do not enter a handler."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.active = 0
        self.peak = 0
        self.calls: Counter[str] = Counter()

    def handler(self, stage: str, delay: float):
        def work(payload: dict) -> dict:
            with self.lock:
                self.calls[stage] += 1
                self.active += 1
                self.peak = max(self.peak, self.active)
            try:
                time.sleep(delay)
                return {"stage": stage, "item": payload["item"]}
            finally:
                with self.lock:
                    self.active -= 1
        return work


def measured_run(workspace: Workspace, workers: int, units: int, lessons: int,
                 delays: dict[str, float]) -> dict:
    meter = CounterClock()
    identity = "synthetic-sleep-v1"

    def one(stage: str, item: int) -> dict:
        return workspace.run_cached(stage, {"item": item},
                                    meter.handler(stage, delays[stage]),
                                    identity=identity, retries=0)

    phases: dict[str, float] = {}
    all_started = time.perf_counter()
    phase_started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        extracted = list(pool.map(lambda n: one("extract", n), range(units)))
    if len(extracted) != units:
        raise AssertionError("extraction results are incomplete")
    phases["extract"] = round(time.perf_counter() - phase_started, 6)

    for stage in ("reconcile", "plan"):
        phase_started = time.perf_counter()
        one(stage, 0)
        phases[stage] = round(time.perf_counter() - phase_started, 6)

    def lesson(index: int) -> tuple[dict, dict]:
        return one("author", index), one("review", index)

    phase_started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        written = list(pool.map(lesson, range(lessons)))
    if len(written) != lessons:
        raise AssertionError("lesson results are incomplete")
    phases["author_and_review"] = round(time.perf_counter() - phase_started, 6)
    expected = {"extract": units, "reconcile": 1, "plan": 1,
                "author": lessons, "review": lessons}
    return {"wall_seconds": round(time.perf_counter() - all_started, 6),
            "phase_wall_seconds": phases, "handler_calls": dict(sorted(meter.calls.items())),
            "total_handler_calls": sum(meter.calls.values()),
            "max_simultaneous_handlers": meter.peak,
            "expected_cold_handler_calls": expected,
            "sqlite_job_stats_after_run": workspace.stats()["jobs"]}


def benchmark(units: int = 24, lessons: int = 6,
              widths: tuple[int, ...] = (1, 4, 8),
              delays: dict[str, float] | None = None) -> dict:
    if units < 1 or lessons < 1 or any(w < 1 for w in widths):
        raise ValueError("units, lessons, and worker widths must be positive")
    delays = dict(DEFAULT_DELAYS if delays is None else delays)
    if set(delays) != set(DEFAULT_DELAYS) or any(x < 0 for x in delays.values()):
        raise ValueError("delays must contain five nonnegative stage durations")
    work = units * delays["extract"] + delays["reconcile"] + delays["plan"] \
        + lessons * (delays["author"] + delays["review"])
    span = delays["extract"] + delays["reconcile"] + delays["plan"] \
        + delays["author"] + delays["review"]
    result = {
        "benchmark": "synthetic_wait_on_real_workspace_cache",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "environment": {"system": platform.system(), "release": platform.release(),
                        "machine": platform.machine(), "python": platform.python_version(),
                        "sqlite": sqlite3.sqlite_version, "logical_cpus": os.cpu_count()},
        "workload": {"synthetic": True, "units": units, "lessons": lessons,
                     "delays_seconds": delays, "workers": list(widths),
                     "dependency_graph": "parallel extract -> reconcile -> plan -> parallel (author -> review)",
                     "description": "Each handler only sleeps and returns a tiny JSON object; no model or media work."},
        "bounds": {"synthetic_handler_work_seconds": round(work, 6),
                   "synthetic_longest_dependency_seconds": round(span, 6),
                   "scope": "Sleep-only idealizations; excludes SQLite, thread scheduling, payload serialization, model inference, and I/O."},
        "runs": [],
    }
    for workers in widths:
        with tempfile.TemporaryDirectory(prefix="lamina-benchmark-") as temp:
            workspace = Workspace(Path(temp))
            cold = measured_run(workspace, workers, units, lessons, delays)
            warm = measured_run(workspace, workers, units, lessons, delays)
        expected_total = units + 2 + 2 * lessons
        if cold["total_handler_calls"] != expected_total or warm["total_handler_calls"] != 0:
            raise AssertionError("cold/warm cache behavior disagrees with the workload")
        ideal = math.ceil(units / workers) * delays["extract"] \
            + delays["reconcile"] + delays["plan"] \
            + math.ceil(lessons / workers) * (delays["author"] + delays["review"])
        result["runs"].append({"workers": workers,
                               "generic_work_span_lower_bound_seconds": round(max(work / workers, span), 6),
                               "barrier_aware_sleep_only_ideal_seconds": round(ideal, 6),
                               "cold": cold, "warm": warm})
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--widths", type=int, nargs="+", default=[1,4,8,16,32])
    parser.add_argument("--units", type=int, default=24)
    parser.add_argument("--lessons", type=int, default=6)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "benchmarks" / "results" / "local-systems.json")
    args = parser.parse_args()
    result = benchmark(args.units, args.lessons, tuple(args.widths))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output),
                      "wall_seconds": {str(r["workers"]): r["cold"]["wall_seconds"] for r in result["runs"]},
                      "warm_handler_calls": {str(r["workers"]): r["warm"]["total_handler_calls"]
                                             for r in result["runs"]}}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
