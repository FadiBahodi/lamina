"""A full stage pass with a spy adapter checks the assessment holdout boundary."""

from __future__ import annotations

import json
import unittest

from lamina.pipeline import build
from lamina.validation import ValidationError


class MemoryWorkspace:
    def __init__(self) -> None:
        self.requests: list[dict] = []
        self._sources = [
            {"id": "s1", "title": "Field guide", "filename": "guide.md", "sha256": "a" * 64, "role": "teaching"},
            {"id": "s2", "title": "Answer key", "filename": "key.md", "sha256": "b" * 64, "role": "assessment"},
        ]
        self._units = [
            {"id": "u1", "source_id": "s1", "heading": "Moss", "text": "Moss holds water after rain.", "locator": "line 1", "ordinal": 1, "role": "teaching"},
            {"id": "a1", "source_id": "s2", "heading": "Answers", "text": "SECRET ASSESSMENT ANSWER", "locator": "line 1", "ordinal": 1, "role": "assessment"},
        ]

    def units(self, role=None):
        return [u for u in self._units if role is None or u["role"] == role]

    def sources(self):
        return self._sources

    def run_cached(self, stage, payload, handler, *, identity, retries=1):
        self.requests.append(payload)
        return handler(payload)

    def stats(self):
        return {"sources": 2, "units": 2}


class SpyProvider:
    identity = "spy-v1"

    def __init__(self, revise=False) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.revise = revise

    def call(self, stage, request):
        self.calls.append((stage, request))
        content = request["input"]
        evidence = [{"unit_id": "u1", "quote": "Moss holds water"}]
        if stage == "extract":
            return {"concepts": [{"title": "Moss", "explanation": "It retains rainwater.", "evidence": evidence}]}
        if stage == "reconcile":
            raw = content["raw_concepts"][0]
            return {"concepts": [{"title": raw["title"], "explanation": raw["explanation"],
                                   "member_ids": [raw["id"]], "evidence": raw["evidence"]}]}
        if stage == "plan":
            return {"title": "Field observations", "lessons": [{"id": "l1", "title": "Rain and moss", "concept_ids": [content["concepts"][0]["id"]], "prerequisite_ids": []}], "deferred": []}
        if stage == "author":
            planned = content["lesson"]
            return {"id": planned["id"], "title": planned["title"], "concept_ids": planned["concept_ids"],
                    "summary": "Moss retains rainwater.",
                    "sections": [{"heading": "Retention", "body": "Moss holds water.", "evidence": evidence}],
                    "questions": [{"id": f"q-{kind}", "kind": kind, "prompt": "What happens?", "answer": "Moss retains water.",
                                   "rationale": "It holds water after rain.", "concept_ids": planned["concept_ids"], "evidence": evidence}
                                  for kind in ("recall", "contrast", "apply")],
                    "audio_script": [{"kind": "speech", "text": "Think about rain."}, {"kind": "pause", "text": "Recall the observation."}]}
        if stage == "review":
            return {"status": "revise", "issues": [{"detail": "Clarify the comparison."}]} if self.revise else {"status": "pass", "issues": []}
        raise AssertionError(stage)


class PipelineTests(unittest.TestCase):
    def test_held_out_assessment_never_enters_adapter_or_bundle(self) -> None:
        workspace = MemoryWorkspace()
        provider = SpyProvider()
        bundle = build(workspace, provider, workers=2)
        self.assertEqual([stage for stage, _ in provider.calls], ["extract", "reconcile", "plan", "author", "review"])
        self.assertNotIn("SECRET ASSESSMENT ANSWER", json.dumps(provider.calls))
        self.assertNotIn("SECRET ASSESSMENT ANSWER", json.dumps(bundle))
        self.assertNotIn('"role": "assessment"', json.dumps(bundle))
        self.assertEqual(bundle["counters"]["assigned_concepts"], 1)

    def test_review_revision_blocks_bundle(self) -> None:
        with self.assertRaisesRegex(ValidationError, "Clarify the comparison"):
            build(MemoryWorkspace(), SpyProvider(revise=True), workers=2)

    def test_material_can_choose_one_practice_form(self) -> None:
        class RecallOnly(SpyProvider):
            def call(self, stage, request):
                result = super().call(stage, request)
                if stage == "author":
                    result["questions"] = result["questions"][:1]
                return result
        bundle = build(MemoryWorkspace(), RecallOnly(), workers=2)
        self.assertEqual([q["kind"] for q in bundle["lessons"][0]["questions"]], ["recall"])

    def test_parallel_writers_receive_route_and_exact_prerequisite_evidence(self) -> None:
        import tempfile
        from pathlib import Path
        from lamina.ingest import ingest_paths
        from lamina.providers import DemoProvider
        from lamina.store import Workspace
        class Capture(DemoProvider):
            def __init__(self):
                super().__init__()
                self.authors = []
            def call(self, stage, request):
                if stage == "author":
                    self.authors.append(request["input"])
                return super().call(stage, request)
        with tempfile.TemporaryDirectory() as folder:
            workspace = Workspace(Path(folder))
            import lamina
            ingest_paths([Path(lamina.__file__).parent / "demo" / "sources"], workspace)
            provider = Capture()
            bundle = build(workspace, provider, workers=3)
            by_id = {row["lesson"]["id"]: row for row in provider.authors}
            plan = bundle["plan"]["lessons"]
            for lesson in plan:
                request = by_id[lesson["id"]]
                self.assertEqual([row["id"] for row in request["shared_route"]], [row["id"] for row in plan])
                self.assertEqual([row["id"] for row in request["earlier_lessons"]], lesson["prerequisite_ids"])
                for previous in request["earlier_lessons"]:
                    units = {row["id"]: row["text"] for row in previous["units"]}
                    for concept in previous["concepts"]:
                        for evidence in concept["evidence"]:
                            self.assertIn(evidence["quote"], units[evidence["unit_id"]])


if __name__ == "__main__":
    unittest.main()
