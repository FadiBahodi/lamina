"""Run source policy and explicit observation selection with an original fixture.

This deterministic adapter demonstrates boundaries and cache behavior, not
model-generated quality. Run from a Lamina checkout with `python
examples/source-policy/demo.py` after installing the package.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from lamina.ingest import ingest_paths
from lamina.method_runtime import record_observation
from lamina.production import plan_production, run_production
from lamina.store import Workspace

HERE = Path(__file__).resolve().parent
FILES = [
    "current-procedure.md",
    "operations-supplement.md",
    "historical-note.md",
    "question-form.md",
]
POLICIES = ["authority", "supplement", "historical", "form_exemplar"]


class BoundaryFixture:
    identity = "original-source-policy-fixture-v1"

    def __init__(self):
        self.route_inputs = []

    def call(self, stage, request):
        if request["protocol"] != "lamina-stage-1" or request["stage"] != stage:
            raise ValueError("Unexpected fixture request")
        data = request["input"]
        if stage == "production_read":
            return {
                "ideas": [
                    {
                        "title": unit["heading"],
                        "explanation": "".join(s["text"] for s in unit["spans"]),
                        "unit_ids": [unit["id"]],
                        "evidence_refs": [
                            {
                                "span_id": unit["spans"][0]["id"],
                                "end_span_id": unit["spans"][-1]["id"],
                            }
                        ],
                    }
                    for unit in data["core"]
                ]
            }
        if stage == "production_route":
            self.route_inputs.append(data)
            ideas = data["ideas"]
            has_note = bool(data["experience"])
            return {
                "title": "Worker retry guide",
                "summary": "Separate expiry from termination",
                "sections": [
                    {
                        "id": "safe-retry",
                        "title": "Safe retry",
                        "purpose": "Explain current behavior and the historical conflict",
                        "idea_ids": [idea["id"] for idea in ideas],
                        "context_section_ids": [],
                        "representation": {
                            "kind": (
                                "question-and-answer"
                                if data["form_exemplars"]
                                else "guide"
                            ),
                            "rationale": "Use the exemplar's form, not its facts",
                            "requirements": [
                                "Explain current fencing behavior",
                                "Mark the old expiry claim as historical",
                            ]
                            + (
                                ["Emphasize expiry versus termination"]
                                if has_note
                                else []
                            ),
                        },
                    }
                ],
                "omitted": [],
                "shared_context": [],
            }
        if stage in {"production_write", "production_repair"}:
            evidence = [
                item for idea in data["assigned_ideas"] for item in idea["evidence"]
            ]
            body = "\n\n".join(item["quote"] for item in evidence)
            if any(
                "Emphasize" in item
                for item in data["section"]["representation"]["requirements"]
            ):
                body += "\n\nOperator-selected clarification: expiry and termination are different events."
            return {
                "body": body,
                "used_idea_ids": data["section"]["idea_ids"],
                "evidence": evidence,
            }
        if stage == "production_review":
            return {"findings": []}
        raise ValueError("Unexpected fixture stage")


def main():
    with tempfile.TemporaryDirectory(prefix="lamina-source-policy-") as directory:
        workspace = Workspace(Path(directory))
        ingest_paths([HERE / name for name in FILES], workspace)
        by_filename = {
            source["filename"]: source["id"] for source in workspace.sources()
        }
        source_ids = [by_filename[name] for name in FILES]
        policy = {sid: role for sid, role in zip(source_ids, POLICIES)}
        options = {
            "format": "guide",
            "source_policy": policy,
            "method_family": "document-production",
        }
        adapter = BoundaryFixture()
        first_plan = plan_production(
            workspace,
            adapter,
            "Explain safe worker retries",
            source_ids,
            {"workflow": "planned", **(options)},
        )
        first = run_production(workspace, adapter, first_plan)
        note = record_observation(
            workspace,
            family="document-production",
            method_id="source-policy-example",
            method_version="1",
            task_digest=first_plan["plan_digest"],
            outcome="useful with clarification",
            applicability="lease-based workers",
            note="Make the expiry/termination distinction visible.",
        )
        selected_options = {**options, "observation_ids": [note["observation_id"]]}
        second_plan = plan_production(
            workspace,
            adapter,
            "Explain safe worker retries",
            source_ids,
            {"workflow": "planned", **(selected_options)},
        )
        second = run_production(workspace, adapter, second_plan)
        result = {
            "label": "Original deterministic fixture; demonstrates mechanics, not model quality.",
            "source_roles": {name: role for name, role in zip(FILES, POLICIES)},
            "first": {
                "status": first["status"],
                "reader_windows": first_plan["metrics"]["reader_windows"],
                "selected_observations": first_plan["metrics"]["selected_observations"],
                "markdown": first["markdown"],
            },
            "second": {
                "status": second["status"],
                "reader_cache_hits": sum(
                    r["cache"] == "hit"
                    for r in second_plan["metrics"]["requests"]
                    if r["stage"] == "production_read"
                ),
                "selected_observations": second_plan["metrics"][
                    "selected_observations"
                ],
                "observation_reached_planner": adapter.route_inputs[-1]["experience"][
                    0
                ]["observation"]["observation_id"]
                == note["observation_id"],
                "markdown": second["markdown"],
            },
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
