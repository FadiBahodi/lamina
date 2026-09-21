"""Original, deterministic engineering fixture exercising the production engine.

This is a trace of scheduling, evidence, repair, and cache behavior. It does not
measure generative quality or make a model/truth claim.
"""

from __future__ import annotations

import tempfile
import threading
from pathlib import Path

from .production import plan_production, run_production
from .store import Workspace

SOURCES = [
    {
        "name": "reliability-notes.md",
        "role": "teaching",
        "text": "# Reliability notes\n\nA lease expires after thirty seconds. Lease expiry does not prove that the former worker stopped.\n\n"
        "A fencing token lets storage reject writes from workers holding an older token.",
    },
    {
        "name": "deployment-notes.md",
        "role": "teaching",
        "text": "# Deployment notes\n\nA retry acquires a new token before it writes. The retry must not assume that the former worker has stopped.\n\n"
        "Operations should log the token on each write attempt so a stale rejection can be traced.",
    },
]
BRIEF = {
    "goal": "Write a short incident guide for a team deploying lease-based background workers.",
    "audience": "On-call engineers",
    "constraints": "Preserve the distinction between lease expiry and worker termination.",
}
OPTIONS = {
    "format": "guide",
    "reader_workers": 8,
    "writer_workers": 8,
    "review_workers": 8,
    "core_words": 100,
    "halo_units": 1,
}


class FixtureAdapter:
    identity = "original-production-fixture-v1"

    def __init__(self):
        self.lock = threading.Lock()
        self.calls: list[dict] = []

    def call(self, stage, request):
        if request.get("stage") != stage or request.get("protocol") != "lamina-stage-1":
            raise ValueError("Fixture received an incompatible request")
        data = request["input"]
        with self.lock:
            self.calls.append(
                {
                    "stage": stage,
                    "item": data.get("window_id")
                    or data.get("section", {}).get("id")
                    or "global",
                }
            )
        if stage == "production_read":
            return {
                "ideas": [
                    {
                        "title": u["heading"],
                        "explanation": u["text"],
                        "unit_ids": [u["id"]],
                        "evidence": [{"unit_id": u["id"], "quote": u["text"]}],
                    }
                    for u in data["core"]
                ]
            }
        if stage == "production_route":
            ideas = data["ideas"]
            return {
                "title": "Lease-worker incident guide",
                "summary": "Expiry, fencing, and traceability",
                "sections": [
                    {
                        "id": f"section_{i}",
                        "title": title,
                        "purpose": purpose,
                        "idea_ids": [idea["id"] for idea in ideas[lo:hi]],
                        "context_section_ids": [f"section_{i-1}"] if i > 1 else [],
                        "representation": {
                            "kind": (
                                "comparison"
                                if i == 1
                                else "procedure" if i == 2 else "reference"
                            ),
                            "rationale": "Match the section's operational job",
                            "requirements": [purpose],
                        },
                    }
                    for i, (title, purpose, lo, hi) in enumerate(
                        (
                            (
                                "What expiry means",
                                "Distinguish lease expiry from worker termination",
                                0,
                                1,
                            ),
                            ("Safe retry", "Explain fencing and fresh tokens", 1, 3),
                            ("Trace rejection", "Explain write-attempt logging", 3, 4),
                        ),
                        1,
                    )
                ],
                "omitted": [],
                "shared_context": [
                    {
                        "statement": "A new lease does not prove that the previous worker has stopped; fencing rejects stale writes.",
                        "evidence": [ideas[0]["evidence"][0], ideas[1]["evidence"][0]],
                    }
                ],
            }
        if stage in {"production_write", "production_repair"}:
            sec = data["section"]
            evidence = [e for idea in data["assigned_ideas"] for e in idea["evidence"]]
            body = " ".join(e["quote"] for e in evidence)
            if sec["id"] == "section_2" and stage == "production_write":
                body = body.replace(
                    "must not assume that the former worker has stopped",
                    "can assume that the former worker has stopped",
                )
            if stage == "production_repair":
                body += (
                    " Lease expiry alone never proves that the former worker stopped."
                )
            if data.get("operator_revision_note"):
                body += " Operator note: " + data["operator_revision_note"]
            return {
                "body": body,
                "used_idea_ids": sec["idea_ids"],
                "evidence": evidence,
            }
        if stage == "production_review":
            if (
                data["section"]["id"] == "section_2"
                and "can assume that the former worker has stopped"
                in data["draft"]["body"]
            ):
                return {
                    "findings": [
                        {
                            "issue": "Expiry does not prove a worker stopped.",
                            "repair_instruction": "Restore the expiry/termination distinction.",
                            "evidence": [data["assigned_ideas"][0]["evidence"][0]],
                        }
                    ]
                }
            return {"findings": []}
        raise ValueError("Unexpected fixture stage")


def production_demo() -> dict:
    """Run the real engine twice: original build, then one section note revision."""
    with tempfile.TemporaryDirectory(prefix="lamina-production-example-") as tmp:
        workspace = Workspace(Path(tmp))
        for i, row in enumerate(SOURCES, 1):
            sid = f"fixture_source_{i}"
            workspace.put_source(
                {
                    "id": sid,
                    "title": row["name"].removesuffix(".md"),
                    "filename": row["name"],
                    "sha256": f"fixture-{i}",
                    "role": "teaching",
                }
            )
            for j, paragraph in enumerate(row["text"].split("\n\n")):
                if paragraph.startswith("#") or not paragraph.strip():
                    continue
                workspace.put_units(
                    [
                        {
                            "id": f"fixture_unit_{i}_{j}",
                            "source_id": sid,
                            "heading": row["name"],
                            "text": paragraph,
                            "locator": f"paragraph {j}",
                            "ordinal": j,
                            "role": "teaching",
                        }
                    ]
                )
        provider = FixtureAdapter()
        events: list[dict] = []
        plan = plan_production(
            workspace,
            provider,
            BRIEF,
            ["fixture_source_1", "fixture_source_2"],
            OPTIONS,
            events.append,
        )
        first = run_production(workspace, provider, plan, progress=events.append)
        revised = run_production(
            workspace,
            provider,
            plan,
            {
                "section_notes": {
                    "section_3": "Add the incident ticket ID beside each rejected write."
                }
            },
            progress=events.append,
        )
        return {
            "label": "Deterministic fixture exercising the actual production engine; no generative quality claim.",
            "brief": BRIEF,
            "options": OPTIONS,
            "sources": SOURCES,
            "plan": plan,
            "runs": [
                {"title": "Initial build", "receipt": first},
                {"title": "Targeted section revision", "receipt": revised},
            ],
            "events": events,
            "provider_calls": provider.calls,
        }
