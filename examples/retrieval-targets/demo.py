"""Run an original, deterministic retrieval-target example without a model account."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from lamina.production import plan_production, run_production
from lamina.store import Workspace

NOTES = [
    ("ordinary-handoff.md", "A stale write is rejected by a fencing token."),
    ("handoff-checklist.md", "A stale write is rejected by a fencing token."),
    ("recovery.md", "A stale write is rejected by a fencing token."),
    ("retry.md", "A retry obtains a new token before it writes."),
]


class DeterministicProvider:
    identity = "retrieval-target-example-v1"

    def call(self, stage, request):
        data = request["input"]
        if stage == "production_read":
            return {
                "ideas": [
                    {
                        "title": unit["heading"],
                        "explanation": unit["text"],
                        "unit_ids": [unit["id"]],
                        "evidence": [{"unit_id": unit["id"], "quote": unit["text"]}],
                    }
                    for unit in data["core"]
                ]
            }
        if stage == "production_targets":
            ids = [idea["id"] for idea in data["ideas"]]

            def answer(text, members, units):
                return {
                    "text": text,
                    "supports_idea_ids": members,
                    "evidence": [
                        {"unit_id": f"unit_{n}", "quote": NOTES[n - 1][1]}
                        for n in units
                    ],
                }

            targets = [
                {
                    "id": "ordinary-handoff",
                    "title": "Ordinary worker handoff",
                    "prompt": "What rejects a stale write during an ordinary worker handoff?",
                    "context": "Normal handoff",
                    "member_idea_ids": ids[:2],
                    "membership_relation": "equivalent",
                    "answer_groups": [
                        {
                            "label": "Guard",
                            "items": [answer(NOTES[0][1], ids[:2], [1, 2])],
                        }
                    ],
                },
                {
                    "id": "recovery",
                    "title": "Recovery after a restart",
                    "prompt": "What rejects a stale write after a recovery restart?",
                    "context": "Restart and recovery",
                    "member_idea_ids": [ids[2]],
                    "membership_relation": "unique",
                    "answer_groups": [
                        {
                            "label": "Guard",
                            "items": [answer(NOTES[2][1], [ids[2]], [3])],
                        }
                    ],
                },
                {
                    "id": "retry-token",
                    "title": "Retry prerequisite",
                    "prompt": "What must a retry obtain before writing?",
                    "context": "New worker retry",
                    "member_idea_ids": [ids[3]],
                    "membership_relation": "unique",
                    "answer_groups": [
                        {
                            "label": "Prerequisite",
                            "items": [answer(NOTES[3][1], [ids[3]], [4])],
                        }
                    ],
                },
            ]
            return {
                "targets": targets,
                "relations": [
                    {
                        "from_target_id": "ordinary-handoff",
                        "to_target_id": "recovery",
                        "kind": "different_context",
                        "reason": "Same answer, different presentation.",
                    },
                    {
                        "from_target_id": "ordinary-handoff",
                        "to_target_id": "retry-token",
                        "kind": "variant",
                        "reason": "Related mechanism, different action asked.",
                    },
                ],
            }
        if stage == "production_route":
            target_ids = [
                target["id"] for target in data["retrieval_targets"]["targets"]
            ]
            return {
                "title": "Worker safety retrieval guide",
                "summary": "Handoff, recovery, retry",
                "sections": [
                    {
                        "id": "questions",
                        "title": "Worker safety questions",
                        "purpose": "Keep distinct presentations visible",
                        "target_ids": target_ids,
                        "context_section_ids": [],
                        "representation": {
                            "kind": "question-and-answer",
                            "rationale": "Direct retrieval practice",
                            "requirements": ["Keep recovery distinct"],
                        },
                    }
                ],
                "omitted": [],
                "shared_context": [],
            }
        if stage in {"production_write", "production_repair"}:
            targets = data["assigned_targets"]
            evidence = [
                citation
                for target in targets
                for group in target["answer_groups"]
                for item in group["items"]
                for citation in item["evidence"]
            ]
            return {
                "body": "\n\n".join(target["prompt"] for target in targets),
                "used_idea_ids": data["section"]["idea_ids"],
                "used_target_ids": data["section"]["target_ids"],
                "evidence": evidence,
            }
        if stage == "production_review":
            return {"findings": []}
        raise ValueError(f"Unexpected stage: {stage}")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="lamina-retrieval-example-") as temporary:
        workspace = Workspace(Path(temporary))
        for number, (name, note) in enumerate(NOTES, 1):
            source_id = f"source_{number}"
            workspace.put_source(
                {
                    "id": source_id,
                    "title": name,
                    "filename": name,
                    "sha256": f"fixture-{number}",
                    "role": "teaching",
                }
            )
            workspace.put_units(
                [
                    {
                        "id": f"unit_{number}",
                        "source_id": source_id,
                        "role": "teaching",
                        "ordinal": 0,
                        "heading": name,
                        "locator": "line 1",
                        "text": note,
                    }
                ]
            )
        provider = DeterministicProvider()
        plan = plan_production(
            workspace,
            provider,
            "Make a worker-safety retrieval guide",
            [f"source_{n}" for n in range(1, 5)],
            {"format": "guide", "retrieval_targets": True},
        )
        receipt = run_production(workspace, provider, plan)
        print(
            json.dumps(
                {
                    "kind": "deterministic fixture, not model-quality evidence",
                    "targets": plan["retrieval_targets"],
                    "route": plan["route"],
                    "guide": receipt["markdown"],
                    "status": receipt["status"],
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
