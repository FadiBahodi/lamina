"""Export aggregate calibration measurements without source text or responses.

python benchmarks/publish_measurements.py --model MODEL --output public.json PRIVATE/report.json ...
"""

from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path


def aggregate(path):
    raw = path.read_bytes()
    report = json.loads(raw)
    trials = []
    for trial in report["trials"]:
        stages = {}
        for call in trial.get("calls", []):
            stage = stages.setdefault(call["stage"], {"calls": 0, "usage": {}})
            stage["calls"] += 1
            for key, value in call.get("usage", {}).items():
                if isinstance(value, (int, float)):
                    stage["usage"][key] = stage["usage"].get(key, 0) + value
        row = {
            key: trial[key]
            for key in (
                "replicate",
                "experimental_stage",
                "experimental_limit",
                "experimental_dimension",
                "status",
                "engine_status",
                "wall_ms",
                "usage",
                "idea_count",
                "corpus_sha256",
                "evaluation_sha256",
                "load",
                "load_unit",
                "source_bytes",
                "provider_identity",
                "protocol_revision",
                "corpus_tokens",
                "read_source_token_exposure",
                "ideas_per_1000_source_tokens",
            )
            if key in trial
        }
        row["stages"] = stages
        row["checks"] = {
            name: {
                key: trial[name][key]
                for key in (
                    "oracle",
                    "preserved",
                    "total",
                    "fraction",
                    "counterfacts",
                    "by_position",
                )
                if key in trial[name]
            }
            for name in (
                "source_control",
                "extraction",
                "assignment",
                "initial_draft",
                "finished_output",
            )
            if name in trial
        }
        # Errors can include quotations, filesystem paths and provider payloads.
        # Public interpretation belongs in the accompanying reviewed write-up.
        row["error_type"] = trial.get("error_type")
        trials.append(row)
    return {
        "report_sha256": hashlib.sha256(raw).hexdigest(),
        **{
            key: report[key]
            for key in (
                "created_at",
                "protocol_revision",
                "stage",
                "dimension",
                "limits",
                "replicates_required",
                "promotion_policy",
            )
            if key in report
        },
        "trials": trials,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", type=Path, nargs="+")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", required=True)
    args = parser.parse_args()
    payload = {
        "kind": "live-model-calibration-aggregates",
        "model": args.model,
        "reports": [aggregate(path) for path in args.reports],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n")


if __name__ == "__main__":
    main()
