"""Measure configured providers with qualified canaries through production.

Run --help for explicit load, task and acceptance controls. --scripted is an
adversarial contract test and cannot establish a model's working capacity.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lamina.context_budget import RequestBudget
from lamina.providers import configured_provider
from lamina.production_contract import REVISION
from lamina.quality_evaluation import run_trial, summarize
from lamina.store import canonical, digest
from lamina.workload_profiles import WorkloadProfile


class ExperimentalLimit:
    """The operator explicitly chooses this one-stage experimental token limit."""

    def __init__(self, provider, stage, limit):
        self.provider, self.stage, self.limit = provider, stage, limit
        self.identity = provider.identity + ":experiment:" + digest([stage, limit])

    def __getattr__(self, name):
        return getattr(self.provider, name)

    def identity_for(self, stage):
        identity = getattr(
            self.provider, "identity_for", lambda _: self.provider.identity
        )(stage)
        return identity + ":experiment:" + digest([self.stage, self.limit])

    def budget_for(self, stage):
        budget = self.provider.budget_for(stage)
        if stage == self.stage:
            budget = replace(
                budget,
                workload=WorkloadProfile(
                    stage, max_input_tokens=self.limit, basis="configured"
                ),
            )
        return budget


class SilentOmissionProvider:
    """Valid replies that deliberately omit a negation in their own statements.

    Quotes still contain the original negation. Citation coverage and schema
    validation pass; checking authored meaning exposes the loss.
    """

    identity = "scripted-silent-omission-1"

    def __init__(self, max_items):
        self.max_items = max_items

    def budget_for(self, stage):
        return RequestBudget(
            2_000_000, workload=WorkloadProfile(stage, max_items=self.max_items)
        )

    def call(self, stage, payload):
        data = payload["input"]
        if stage == "production_read":
            ideas = []
            for unit in data["core"]:
                text = "".join(span["text"] for span in unit["spans"])
                idea = {
                    "title": "Source equipment statement",
                    "explanation": (
                        "Rotor Umber has a red indicator."
                        if "Rotor Umber does not reset" in text
                        else text
                    ),
                    "unit_ids": [unit["id"]],
                }
                if unit.get("spans"):
                    idea["evidence_refs"] = [
                        {
                            "span_id": unit["spans"][0]["id"],
                            "end_span_id": unit["spans"][-1]["id"],
                        }
                    ]
                else:
                    idea["evidence"] = [{"unit_id": unit["id"], "quote": text}]
                ideas.append(idea)
            return {"ideas": ideas}
        if stage == "production_route":
            return {
                "title": "Fictional equipment reference",
                "summary": "Retain equipment conditions.",
                "sections": [
                    {
                        "id": "equipment",
                        "title": "Equipment",
                        "purpose": "Preserve the source specifications.",
                        "idea_ids": [row["id"] for row in data["ideas"]],
                        "context_section_ids": [],
                        "candidate_context_ids": [],
                        "representation": {
                            "kind": "reference",
                            "rationale": "Retain the specifications.",
                            "requirements": [],
                        },
                    }
                ],
                "omitted": [],
                "shared_context": [],
            }
        if stage in {"production_write", "production_repair"}:
            ideas = data["assigned_ideas"]
            return {
                "body": "\n\n".join(row["explanation"] for row in ideas),
                "used_idea_ids": [row["id"] for row in ideas],
                "evidence": [e for row in ideas for e in row["evidence"]],
            }
        if stage == "production_review":
            return {"findings": []}
        raise ValueError("scripted fixture does not implement " + stage)


def integers(text):
    values = [int(value) for value in text.split(",")]
    if (
        not values
        or any(value < 1 for value in values)
        or len(values) != len(set(values))
    ):
        raise argparse.ArgumentTypeError("supply distinct positive integers")
    return values


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    providers = parser.add_mutually_exclusive_group(required=True)
    providers.add_argument(
        "--models",
        type=Path,
        help="configured_provider JSON with explicit per-stage workload policies",
    )
    providers.add_argument(
        "--scripted",
        action="store_true",
        help="exercise silent omission; no live model",
    )
    parser.add_argument(
        "--loads",
        required=True,
        type=integers,
        help="background paragraph counts, e.g. 20,80,200; actual request tokens are recorded",
    )
    parser.add_argument(
        "--input-limits",
        type=integers,
        help="experimental rendered-input token caps for --stage; requires a real adapter tokenizer",
    )
    parser.add_argument(
        "--stage",
        choices=["production_read", "production_route", "production_write"],
        default="production_read",
    )
    parser.add_argument("--reading", choices=["task", "reusable"], required=True)
    parser.add_argument("--replicates", type=int, required=True)
    parser.add_argument(
        "--complete", action="store_true", help="include writing, review and any repair"
    )
    parser.add_argument(
        "--minimum-fraction",
        type=float,
        required=True,
        help="caller-supplied lexical survival criterion, applied to each position and replicate",
    )
    parser.add_argument("--maximum-counterfacts", type=int, required=True)
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="fresh directory for sources, plans, outputs and report.json",
    )
    args = parser.parse_args(argv)
    if (
        args.replicates < 1
        or not 0 <= args.minimum_fraction <= 1
        or args.maximum_counterfacts < 0
    ):
        parser.error("invalid replicate count or acceptance criteria")
    if args.output.exists():
        parser.error("--output must be a fresh directory")
    if args.scripted and args.input_limits:
        parser.error("scripted fixture has no tokenizer; omit --input-limits")
    provider = (
        SilentOmissionProvider(max(args.loads) + 20)
        if args.scripted
        else configured_provider(args.models)
    )
    trials = []
    try:
        if not args.scripted:
            stages = ["production_read", "production_route"] + (
                ["production_write", "production_review", "production_repair"]
                if args.complete
                else []
            )
            for stage in stages:
                budget = provider.budget_for(stage)
                if budget.context_tokens is None or budget.output_tokens < 1:
                    parser.error(
                        f"{stage} requires a declared tokenizer, context limit and output token allowance"
                    )
        for limit in args.input_limits or [None]:
            experiment = (
                ExperimentalLimit(provider, args.stage, limit) if limit else provider
            )
            for load in args.loads:
                for replicate in range(args.replicates):
                    folder = (
                        args.output
                        / f"limit-{limit or 'configured'}-load-{load}-replicate-{replicate + 1}"
                    )
                    result = run_trial(
                        experiment,
                        folder,
                        load=load,
                        reading=args.reading,
                        complete=args.complete,
                    )
                    result["experimental_input_limit"] = limit
                    result["experimental_stage"] = args.stage if limit else None
                    result["replicate"] = replicate + 1
                    trials.append(result)
        stages = ["extraction", "assignment"] + (
            ["finished_output"] if args.complete else []
        )
        report = {
            "protocol_revision": REVISION,
            "evaluation": (
                "scripted-adversarial-contract"
                if args.scripted
                else "configured-provider-observations"
            ),
            "oracle_scope": "Lexical canary preservation with correct-source evidence; broader meaning, usefulness and unknown factual errors require human review.",
            "summary": summarize(
                trials,
                minimum_fraction=args.minimum_fraction,
                maximum_counterfacts=args.maximum_counterfacts,
                required_stages=stages,
            ),
            "trials": trials,
        }
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / "report.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
        print(
            canonical(
                {
                    "report": str(args.output / "report.json"),
                    "evaluation": report["evaluation"],
                    "summary": report["summary"],
                }
            )
        )
    finally:
        getattr(provider, "close", lambda: None)()
    return (
        0
        if all(
            row["passed_all_observed_checks"]
            for row in report["summary"]["observations"]
        )
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
