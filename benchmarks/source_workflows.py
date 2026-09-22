"""Compare request work on an original deterministic windmill fixture.

Run with --repo pointing at each checkout. No network or model calls occur.
Reference token counts use cl100k_base, not any provider's billing tokenizer.
"""

import argparse
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
sys.path.insert(0, str(args.repo.resolve() / "src"))
import tiktoken
from lamina.production import build_production, run_production, REVISION
from lamina.store import Workspace, canonical

encoding = tiktoken.get_encoding("cl100k_base")


class Meter:
    identity = "original-wind-fixture-1"

    def __init__(self):
        self.requests = []

    def call(self, stage, payload):
        self.requests.append((stage, payload))
        data = payload["input"]
        if stage == "production_read":
            return {
                "ideas": [
                    {
                        "title": u["heading"],
                        "explanation": u["text"][:180],
                        "unit_ids": [u["id"]],
                        "evidence": [{"unit_id": u["id"], "quote": u["text"][:120]}],
                    }
                    for u in data["core"]
                ]
            }
        if stage == "production_route":
            return {
                "title": "Windmill fixture",
                "summary": "Fixed assignments, not model quality.",
                "sections": [
                    {
                        "id": f"section-{i}",
                        "title": f"Topic {i}",
                        "purpose": "Explain the assigned material.",
                        "idea_ids": [idea["id"] for idea in data["ideas"][i::10]],
                        "context_section_ids": [],
                        "representation": {
                            "kind": "explanation",
                            "rationale": "Fixed fixture.",
                            "requirements": [],
                        },
                    }
                    for i in range(10)
                ],
                "omitted": [],
                "shared_context": [],
            }
        if stage == "production_write":
            evidence = [e for idea in data["assigned_ideas"] for e in idea["evidence"]]
            return {
                "body": " ".join(e["quote"] for e in evidence)
                + data.get("operator_revision_note", ""),
                "used_idea_ids": data["section"]["idea_ids"],
                "evidence": evidence,
            }
        if stage == "production_review":
            return {"findings": []}
        raise ValueError(stage)


with tempfile.TemporaryDirectory() as folder:
    ws = Workspace(Path(folder))
    ws.put_source(
        {
            "id": "wind",
            "title": "Windmill fixture",
            "filename": "wind.md",
            "sha256": "synthetic",
            "role": "teaching",
        }
    )
    phrase = "Wind turns the blade and shaft while crews check each worn part for signs of rust and wear".split()
    units = [
        {
            "id": f"u{i}",
            "source_id": "wind",
            "role": "teaching",
            "ordinal": i,
            "heading": "Windmill",
            "locator": f"paragraph {i}",
            "text": " ".join(([f"Note{i}."] + phrase * 20)[:250]),
        }
        for i in range(100)
    ]
    ws.put_units(units)
    provider = Meter()
    options = {} if REVISION == "lamina-production-3" else {"workflow": "planned"}
    result = build_production(
        ws, provider, "Explain windmills for beginners", ["wind"], options
    )
    calls = list(provider.requests)
    stages = {}
    for stage in sorted({s for s, _ in calls}):
        requests = [payload for s, payload in calls if s == stage]
        stages[stage] = {
            "calls": len(requests),
            "request_bytes": sum(len(canonical(p).encode()) for p in requests),
            "reference_input_tokens": sum(
                len(encoding.encode(canonical(p))) for p in requests
            ),
        }
    reader_words = sum(
        len(u["text"].split())
        for s, p in calls
        if s == "production_read"
        for key, value in p["input"].items()
        if isinstance(value, list)
        for u in value
        if isinstance(u, dict) and "text" in u and "id" in u
    )
    before = len(provider.requests)
    run_production(ws, provider, result["plan"])
    warm = len(provider.requests) - before
    before = len(provider.requests)
    run_production(
        ws,
        provider,
        result["plan"],
        {"section_notes": {"section-0": " Clarify this section."}},
    )
    revision_calls = len(provider.requests) - before
    report = {
        "kind": "deterministic_fixture_not_model_quality",
        "revision": REVISION,
        "fixture": {
            "units": 100,
            "words": 25000,
            "sections": 10,
            "tokenizer": "cl100k_base",
        },
        "stages": stages,
        "reader_source_words": reader_words,
        "reader_source_amplification": reader_words / 25000,
        "cold_calls": len(calls),
        "warm_write_calls": warm,
        "section_revision_calls": revision_calls,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
