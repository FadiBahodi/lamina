"""SAMP-specific stage, provenance, scoring, and candidate/examiner separation."""
from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from lamina.ingest import ingest_paths
from lamina.pipeline import build
from lamina.providers import DemoProvider
from lamina.procedures import BUILTINS
from lamina.samp import export_samp, generate_samp, validate_samp
from lamina.store import Workspace
from lamina.validation import ValidationError


class SampTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = Workspace(self.root / "workspace")
        source_dir = Path(__file__).resolve().parents[1] / "src" / "lamina" / "demo"
        ingest_paths([source_dir], self.workspace)
        self.provider = DemoProvider()
        self.bundle = build(self.workspace, self.provider, workers=2)
        self.artifact = generate_samp(self.bundle, self.provider, self.workspace)

    def test_curated_problem_is_staged_and_export_separates_answers(self):
        self.assertEqual(len(self.artifact["problems"]), 1)
        steps = self.artifact["problems"][0]["steps"]
        self.assertEqual(len(steps), 4)
        self.assertIsNone(steps[0]["new_information"])
        self.assertTrue(all(s["new_information"] and s["decision_change"] for s in steps[1:]))
        self.assertEqual(len(steps[0]["answer_points"][0]["evidence"]), 1)
        self.assertIn("another worker may claim", steps[0]["answer_points"][0]["evidence"][0]["quote"])
        json_path, md_path = export_samp(self.artifact, self.root / "output")
        self.assertTrue(json_path.is_file())
        document = md_path.read_text(encoding="utf-8")
        candidate, examiner = document.split("## Examiner sheet", 1)
        self.assertIn("changed report parameters", candidate)
        self.assertNotIn("Check durable completion", candidate)
        self.assertIn("Check durable completion", examiner)
        self.assertLess(candidate.index("Question 1"), candidate.index("Question 4"))

    def test_rejects_invented_or_cross_concept_evidence(self):
        tampered = copy.deepcopy(self.artifact)
        tampered["problems"][0]["steps"][0]["answer_points"][0]["evidence"][0]["quote"] = "INVENTED PRIVATE ANSWER"
        with self.assertRaises(ValidationError):
            validate_samp(tampered, self.bundle)
        tampered = copy.deepcopy(self.artifact)
        other = next(c for c in self.bundle["concepts"] if c["id"] not in tampered["problems"][0]["concept_ids"])
        tampered["problems"][0]["steps"][0]["answer_points"][0]["evidence"] = [other["evidence"][0]]
        with self.assertRaises(ValidationError):
            validate_samp(tampered, self.bundle)

    def test_precise_quote_in_assigned_unit_is_allowed_but_unassigned_unit_is_not(self):
        artifact = copy.deepcopy(self.artifact)
        first = artifact["problems"][0]["steps"][0]["answer_points"][1]
        precise = "A late worker can still finish after its lease expires."
        self.assertNotIn(precise, {e["quote"] for c in artifact["concepts"] for e in c["evidence"]})
        first["evidence"][0]["quote"] = precise
        validate_samp(artifact, self.bundle)
        other = next(c for c in self.bundle["concepts"] if c["id"] not in artifact["problems"][0]["concept_ids"])
        foreign = other["evidence"][0]
        unit = next(u for u in self.bundle["units"] if u["id"] == foreign["unit_id"])
        source = next(s for s in self.bundle["sources"] if s["id"] == unit["source_id"])
        artifact["sources"].append(source)
        artifact["units"].append(unit)
        first["evidence"] = [foreign]
        with self.assertRaises(ValidationError):
            validate_samp(artifact, self.bundle)

    def test_rejects_mark_and_response_limit_inconsistency(self):
        tampered = copy.deepcopy(self.artifact)
        tampered["problems"][0]["steps"][0]["marks"] = 3
        with self.assertRaisesRegex(ValidationError, "marks disagree"):
            validate_samp(tampered, self.bundle)
        tampered = copy.deepcopy(self.artifact)
        tampered["problems"][0]["steps"][0]["answer_limit"] = 1
        with self.assertRaises(ValidationError):
            validate_samp(tampered, self.bundle)

    def test_rejects_extra_private_field_and_stale_source(self):
        tampered = copy.deepcopy(self.artifact)
        tampered["problems"][0]["private_notes"] = "should never export"
        with self.assertRaises(ValidationError):
            export_samp(tampered, self.root / "rejected")
        tampered = copy.deepcopy(self.artifact)
        tampered["units"][0]["text"] += "\nAltered"
        with self.assertRaises(ValidationError):
            validate_samp(tampered, self.bundle)
        tampered = copy.deepcopy(self.artifact)
        tampered["sources"][0]["filename"] = 42
        target = self.root / "invalid-filename"
        with self.assertRaises(ValidationError):
            export_samp(tampered, target)
        self.assertFalse((target / "samp.json").exists())
        tampered = copy.deepcopy(self.artifact)
        tampered["concepts"][0]["member_ids"] = [{"private": "hidden"}]
        with self.assertRaises(ValidationError):
            export_samp(tampered, self.root / "invalid-members")

    def test_markdown_treats_source_and_model_text_as_plain_text(self):
        tampered = copy.deepcopy(self.artifact)
        tampered["problems"][0]["stem"] = "Inspect ![remote](https://example.invalid/pixel) before proceeding."
        _, path = export_samp(tampered, self.root / "plain-text")
        body = path.read_text(encoding="utf-8")
        self.assertNotIn("![remote](https://example.invalid/pixel)", body)
        self.assertIn(r"\!\[remote\]\(https://example.invalid/pixel\)", body)

    def test_cache_identity_and_assessment_holdout(self):
        assessment = self.root / "held-out.md"
        assessment.write_text("# Assessment\n\nSECRET ASSESSMENT ANSWER\n", encoding="utf-8")
        ingest_paths([assessment], self.workspace, role="assessment")
        fresh_bundle = build(self.workspace, self.provider, workers=2)
        first = generate_samp(fresh_bundle, self.provider, self.workspace)
        second = generate_samp(fresh_bundle, self.provider, self.workspace)
        self.assertEqual(first, second)
        self.assertNotIn("SECRET ASSESSMENT ANSWER", str(first))
        self.assertNotIn("SECRET ASSESSMENT ANSWER", str(self.workspace.stats()))

    def test_distinct_semantic_review_can_block_release(self):
        response = {"title": self.artifact["title"], "problems": self.artifact["problems"]}
        class ReviewingAdapter:
            identity = "reviewing-adapter-v1"
            def __init__(self):
                self.stages = []
            def call(self, stage, request):
                self.stages.append(stage)
                if stage == "samp":
                    return response
                if stage == "samp_review":
                    return {"status": "revise", "issues": [{"detail": "The changed input needs a clearer decision."}]}
                raise AssertionError(stage)
        adapter = ReviewingAdapter()
        with self.assertRaisesRegex(ValidationError, "requires revision"):
            generate_samp(self.bundle, adapter, self.workspace)
        self.assertEqual(adapter.stages, ["samp", "samp_review"])

    def test_full_procedure_context_changes_samp_cache(self):
        response = {"title": self.artifact["title"], "problems": self.artifact["problems"]}
        class RecordingAdapter:
            identity = "recording-samp-adapter-v1"
            def __init__(self):
                self.calls = []
            def call(self, stage, request):
                self.calls.append((stage, request))
                return response if stage == "samp" else {"status": "pass", "issues": []}
        adapter = RecordingAdapter()
        procedure = copy.deepcopy(next(p for p in BUILTINS if p["id"] == "samp"))
        generate_samp(self.bundle, adapter, self.workspace, procedure=procedure)
        generate_samp(self.bundle, adapter, self.workspace, procedure=procedure)
        self.assertEqual([stage for stage, _ in adapter.calls], ["samp", "samp_review"])
        self.assertEqual(adapter.calls[0][1]["input"]["procedure"]["audience"], procedure["audience"])
        changed = copy.deepcopy(procedure)
        changed["instructions"] += " Ask for the decision after each reveal."
        generate_samp(self.bundle, adapter, self.workspace, procedure=changed)
        self.assertEqual([stage for stage, _ in adapter.calls], ["samp", "samp_review", "samp", "samp_review"])
        self.assertNotEqual(adapter.calls[0][1]["input"]["procedure"]["revision"],
                            adapter.calls[2][1]["input"]["procedure"]["revision"])
        demo = generate_samp(self.bundle, self.provider, self.workspace, procedure=procedure)
        self.assertEqual(demo["problems"][0]["id"], "incident-1")


if __name__ == "__main__":
    unittest.main()
