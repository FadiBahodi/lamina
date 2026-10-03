"""Compare single-section, grouped and direct requests on the same source task.

Fixture mode measures local execution and request sizes, never model quality.
Gemini mode requires GEMINI_API_KEY and an explicit --model. Every replicate
uses fresh workspaces. Planned variants share an identical frozen plan; its
measured cost is included in both totals. Failed runs remain in the report.
"""

from __future__ import annotations

import argparse
from collections import Counter
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from lamina.calibration import read_corpus
from lamina.ingest import ingest_paths
from lamina.production import plan_production, run_production
from lamina.production_contract import REVISION
from lamina.production_example import fixture_request_budget
from lamina.quality_evaluation import (
    Canary, ObservedProvider, _body_rows, _source_control, _source_map, score_canaries,
)
from lamina.store import Workspace, canonical

FACTS = [
    ("Rotor Amber", "Rotor Amber stops above 20 m/s unless supervised test mode is active."),
    ("Rotor Blue", "Rotor Blue does not produce electricity while its brake is locked."),
    ("Controller Cedar", "Controller Cedar starts only after both sensors agree for 30 seconds."),
    ("Channel Delta", "Channel Delta measures wind speed in m/s, not rotor speed in rpm."),
    ("Vessel Elm", "Vessel Elm permits 14 kPa only after cooling for 2 minutes."),
    ("Rotor Flint", "The 2018 Rotor Flint limit of 13 m/s does not apply to the 2026 controller."),
]
BRIEF = "Write a concise equipment reference. Preserve every condition, exception, number, unit and date in the sources. These are fictional specifications."


class FixtureProvider:
    identity = "matched-execution-source-echo-1"

    def budget_for(self, stage):
        return fixture_request_budget(stage, max_items=96)

    def call(self, stage, payload):
        data = payload["input"]
        if "section_tasks" in data:
            return {"sections": [
                {"section_id": task["section_id"], "result": self.call(stage, {"input": task["input"]})}
                for task in data["section_tasks"]
            ]}
        if stage == "production_read":
            return {"ideas": [{
                "title": unit["heading"],
                "explanation": "".join(span["text"] for span in unit["spans"]),
                "evidence_refs": [{"span_id": unit["spans"][0]["id"], "end_span_id": unit["spans"][-1]["id"]}],
            } for unit in data["core"]]}
        if stage == "production_route":
            return {"title": "Equipment reference", "summary": "Conditions for each device.",
                    "sections": [{"id": f"section_{i}", "title": idea["title"],
                                  "purpose": "Explain this device's conditions.", "idea_ids": [idea["id"]],
                                  "context_section_ids": [], "candidate_context_ids": [],
                                  "representation": {"kind": "reference", "rationale": "Keep each device's conditions together.", "requirements": []}}
                                 for i, idea in enumerate(data["ideas"])],
                    "shared_context": [], "omitted": []}
        if stage in {"production_write", "production_repair"}:
            units = data["assigned_units"]
            text = lambda unit: unit.get("text", re.sub(r"\[s\d+\]", "", unit.get("addressed_text", "")))
            evidence = [{"unit_id": unit["id"], "quote": text(unit)} for unit in units]
            result = {"body": "\n\n".join(text(unit) for unit in units), "evidence": evidence,
                      "claims": [{"id": f"claim_{i}", "text": text(unit), "body_field": "body", "evidence": [evidence[i]]}
                                 for i, unit in enumerate(units)]}
            section = data["section"]
            if "unit_ids" in section:
                result.update(used_unit_ids=section["unit_ids"], omitted_units=[])
            else:
                result["used_idea_ids"] = section["idea_ids"]
            return result
        if stage == "production_review":
            return {"findings": []}
        raise ValueError(f"Unexpected fixture stage: {stage}")


class CallLimit:
    def __init__(self, provider, limit):
        import threading
        self.provider, self.limit, self.count = provider, limit, 0
        self.lock = threading.Lock()

    def __getattr__(self, name):
        return getattr(self.provider, name)

    def call(self, stage, payload):
        with self.lock:
            if self.count >= self.limit:
                raise RuntimeError("Experiment model-call limit reached")
            self.count += 1
        return self.provider.call(stage, payload)


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def original_corpus(folder):
    folder.mkdir()
    paths, canaries = [], []
    for i, (subject, fact) in enumerate(FACTS):
        path = folder / f"device-{i}.txt"
        path.write_text(fact + "\n")
        paths.append(path)
        canaries.append(Canary(str(i), path.name, subject, (fact,), (), "whole-source", "qualified-statement"))
    return paths, canaries, BRIEF


def prepare(folder, paths):
    start = time.perf_counter()
    ws = Workspace(folder / "workspace")
    ingest_paths(paths, ws)
    return ws, [row["id"] for row in ws.sources()], (time.perf_counter() - start) * 1000


def metrics(records):
    return {
        "calls": dict(Counter(row["stage"] for row in records)),
        "request_bytes": sum(len(canonical(row["payload"]).encode()) for row in records),
        "usage": {key: sum(row.get("usage", {}).get(key, 0) for row in records)
                  for key in sorted({k for row in records for k in row.get("usage", {})})},
    }


def transport(provider):
    method = getattr(provider, "transport_metrics", None)
    return dict(method()) if callable(method) else {}


def summarize(rows):
    out = {}
    for arm in ("planned", "grouped", "direct"):
        selected = [row for row in rows if row["arm"] == arm]
        completed = [row for row in selected if row.get("status") in {"ready", "review"}]
        out[arm] = {"attempted": len(selected), "completed": len(completed),
                    "failed": sum(row["status"] == "failed" for row in selected),
                    "needs_review": sum(row["status"] == "review" for row in selected),
                    "passed_declared_checks": sum(row.get("passed_checks", False) for row in selected)}
        for key in ("wall_ms", "execution_ms", "first_useful_output_ms", "request_bytes"):
            values = [row[key] for row in completed if row.get(key) is not None]
            out[arm][key] = {"min": min(values), "median": statistics.median(values), "max": max(values)} if values else None
    return out


def run(args):
    if args.provider == "gemini" and (not os.environ.get("GEMINI_API_KEY") or not args.model):
        raise ValueError("Live measurement requires GEMINI_API_KEY and --model. No model requests were made.")
    if args.provider == "fixture" and args.corpus:
        raise ValueError("Use a live provider for a custom corpus; the fixture only tests the bundled six statements.")
    args.output.mkdir(parents=True, exist_ok=False)
    corpus = read_corpus(args.corpus) if args.corpus else original_corpus(args.output / "sources")
    paths, canaries, brief = corpus
    report = {"kind": "live-model" if args.provider == "gemini" else "deterministic-local-execution",
              "created_at": datetime.now(timezone.utc).isoformat(), "protocol": REVISION,
              "python": platform.python_version(), "platform": platform.platform(),
              "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "model": args.model if args.provider == "gemini" else None,
              "workers": args.workers, "provider_concurrency": args.concurrency if args.provider == "gemini" else None,
              "sections_per_request": args.group_size,
              "planning": "One cold plan per replicate shared by planned/grouped; its measured cost is included in both totals.",
              "corpus_sha256": hashlib.sha256(b"".join(p.name.encode() + b"\0" + p.read_bytes() for p in paths)).hexdigest(),
              "implementation_sha256": hashlib.sha256(b"".join(p.relative_to(ROOT).as_posix().encode()+b"\0"+p.read_bytes() for p in sorted((ROOT / "src/lamina").rglob("*.py")))).hexdigest(),
              "limits": ["Exact-phrase checks may reject correct paraphrases and miss undeclared errors.",
                         "Fixture mode copies source text, with no simulated delay or token estimates. Its timings measure local overhead only.",
                         "Request bytes are serialized Lamina envelopes, not provider-billed tokens.",
                         "First output is provisional. Completion includes every section check.",
                         "Small replicate counts do not establish project tail percentiles.",
                         "This corpus does not measure cross-document nomination recall or 10,000-page performance."],
              "trials": []}
    for replicate in range(args.replicates):
        folder = args.output / f"replicate-{replicate+1}"
        folder.mkdir()
        if args.provider == "gemini":
            from examples.adapter.gemini_provider import GeminiProvider
            provider = GeminiProvider(model=args.model, max_concurrency=args.concurrency)
        else:
            provider = FixtureProvider()
        provider = CallLimit(provider, args.max_calls)
        observed = ObservedProvider(provider, folder / "calls.jsonl")
        ws, ids, parse_ms = prepare(folder / "planning", paths)
        control = _source_control(ws, canaries)
        if control["preserved"] != control["total"]:
            raise ValueError("Source checks failed before model requests")
        options = {"workflow": "planned", "workers": args.workers, "reading": "task"}
        start = time.perf_counter()
        transport_start = transport(provider)
        try:
            frozen = plan_production(ws, observed, brief, ids, options)
            save(folder / "plan.json", frozen)
            plan_error = None
        except Exception as exc:
            frozen, plan_error = None, type(exc).__name__ + ": " + str(exc)
        planning_ms = (time.perf_counter() - start) * 1000
        planning_transport = {key: value - transport_start.get(key, 0) for key, value in transport(provider).items()}
        planning_records = list(observed.records)
        order = ["planned", "grouped", "direct"]
        order = order[replicate % 3:] + order[:replicate % 3]
        for arm in order:
            trial_folder = folder / arm
            trial_folder.mkdir()
            row = {"replicate": replicate+1, "arm": arm, "status": "failed"}
            offset = len(observed.records)
            started = time.perf_counter()
            transport_start = transport(provider)
            receipt = None
            try:
                target, target_ids, trial_parse_ms = prepare(trial_folder, paths)
                if arm == "direct":
                    begin = time.perf_counter()
                    plan = plan_production(target, observed, brief, target_ids, {**options, "workflow": "direct"})
                    plan_ms = (time.perf_counter() - begin) * 1000
                else:
                    if frozen is None:
                        raise RuntimeError("Shared planning failed: " + plan_error)
                    plan, plan_ms = copy.deepcopy(frozen), planning_ms
                begin = time.perf_counter()
                receipt = run_production(target, observed, plan, {"sections_per_request": args.group_size if arm == "grouped" else 1})
                row["execution_ms"] = (time.perf_counter() - begin) * 1000
                row["wall_ms"] = (time.perf_counter() - started) * 1000 + (planning_ms if arm != "direct" else 0)
                row["status"] = receipt["status"]
                requests = plan["metrics"].get("requests", []) + receipt["metrics"].get("requests", [])
                row["call_preparation_ms"] = sum(request.get("preparation_ms", 0) for request in requests)
                row["execution_capacity"] = receipt["metrics"].get("execution_capacity")
                checks = score_canaries(canaries, _body_rows(receipt["sections"]), _source_map(plan))
                row.update(checks=checks, passed_checks=checks["preserved"] == checks["total"] and checks["counterfacts"] == 0,
                           sections=len(receipt["sections"]), parse_ms=trial_parse_ms, planning_ms=plan_ms,
                           output_sha256=hashlib.sha256(receipt["markdown"].encode()).hexdigest())
                first = receipt["metrics"].get("first_useful_output_ms")
                row["first_useful_output_ms"] = trial_parse_ms + plan_ms + first if first is not None else None
                save(trial_folder / "receipt.json", receipt)
                (trial_folder / "output.md").write_text(receipt["markdown"])
            except Exception as exc:
                row.update(error_type=type(exc).__name__, error=str(exc))
            row.setdefault("wall_ms", (time.perf_counter() - started) * 1000 + (planning_ms if arm != "direct" else 0))
            row["transport"] = {key: value - transport_start.get(key, 0) + (planning_transport.get(key, 0) if arm != "direct" else 0)
                                for key, value in transport(provider).items()}
            records = ([*planning_records] if arm != "direct" else []) + observed.records[offset:]
            row.update(metrics(records))
            row["call_measurements"] = [{k: record[k] for k in ("stage", "status", "wall_ms", "measurement", "usage")} for record in records]
            report["trials"].append(row)
            save(trial_folder / "trial.json", row)
            report["summary"] = summarize(report["trials"])
            save(args.output / "report.json", report)
            print(json.dumps({k: row.get(k) for k in ("replicate", "arm", "status", "passed_checks", "calls", "wall_ms")}), flush=True)
        close = getattr(provider, "close", None)
        if callable(close):
            close()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=["fixture", "gemini"], default="fixture")
    parser.add_argument("--model")
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--replicates", type=int, default=3)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--group-size", type=int, default=6)
    parser.add_argument("--max-calls", type=int, default=100)
    args = parser.parse_args()
    if not 1 <= args.replicates <= 100 or not 1 <= args.workers <= 128 or not 1 <= args.concurrency <= 128 or not 1 <= args.group_size <= 32 or args.max_calls < 1:
        parser.error("Invalid replicate, concurrency, group size or call limit")
    try:
        result = run(args)
    except ValueError as exc:
        parser.exit(2, str(exc) + "\n")
    return 0 if all(row["status"] == "ready" and row.get("passed_checks") for row in result["trials"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
