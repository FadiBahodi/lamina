"""Boundary tests: no invented evidence or silently missing study objectives."""

from __future__ import annotations

import copy
import unittest

from lamina.validation import (
    ValidationError,
    validate_evidence,
    validate_extraction,
    validate_lesson,
    validate_plan,
    validate_reconcile,
    validate_review,
)


TEACHING = {
    "u1": {"id": "u1", "role": "teaching", "text": "Moss holds water after rain."},
    "u2": {"id": "u2", "role": "teaching", "text": "Lichen grows on bare rock."},
    "a1": {"id": "a1", "role": "assessment", "text": "The secret answer is moss."},
}
CONCEPTS = [
    {"id": "c1", "title": "Moss", "evidence": [{"unit_id": "u1", "quote": "Moss holds water"}]},
    {"id": "c2", "title": "Lichen", "evidence": [{"unit_id": "u2", "quote": "Lichen grows"}]},
]


class EvidenceTests(unittest.TestCase):
    def test_rejects_quote_absent_from_source(self) -> None:
        with self.assertRaisesRegex(ValidationError, "absent"):
            validate_evidence([{"unit_id": "u1", "quote": "Moss makes oxygen"}], TEACHING, "evidence")

    def test_rejects_held_out_assessment_quote(self) -> None:
        with self.assertRaisesRegex(ValidationError, "held-out"):
            validate_evidence([{"unit_id": "a1", "quote": "secret answer"}], TEACHING, "evidence")

    def test_rejects_unknown_unit_even_if_quote_exists_elsewhere(self) -> None:
        with self.assertRaisesRegex(ValidationError, "unknown unit"):
            validate_evidence([{"unit_id": "missing", "quote": "Moss holds water"}], TEACHING, "evidence")

    def test_adjacent_source_evidence_cannot_replace_core_evidence(self) -> None:
        proposal = {"concepts": [{"title": "Lichen", "explanation": "It grows on rock.",
                                   "evidence": [{"unit_id": "u2", "quote": "Lichen grows"}]}]}
        with self.assertRaisesRegex(ValidationError, "core unit"):
            validate_extraction(proposal, TEACHING["u1"], TEACHING)


class PlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = {
            "title": "Field observations",
            "lessons": [{"id": "l1", "title": "First observations", "concept_ids": ["c1"], "prerequisite_ids": []}],
            "deferred": [{"concept_id": "c2", "reason": "Better in the next field session"}],
        }

    def test_accepts_explicit_deferral(self) -> None:
        self.assertEqual(len(validate_plan(self.plan, CONCEPTS)["deferred"]), 1)

    def test_missing_concept_is_an_error(self) -> None:
        plan = copy.deepcopy(self.plan)
        plan["deferred"] = []
        with self.assertRaisesRegex(ValidationError, "missing=\\['c2'\\]"):
            validate_plan(plan, CONCEPTS)

    def test_double_assignment_is_an_error(self) -> None:
        plan = copy.deepcopy(self.plan)
        plan["lessons"][0]["concept_ids"].append("c2")
        with self.assertRaisesRegex(ValidationError, "repeated=\\['c2'\\]"):
            validate_plan(plan, CONCEPTS)

    def test_prerequisite_cannot_point_forward(self) -> None:
        plan = copy.deepcopy(self.plan)
        plan["lessons"][0]["prerequisite_ids"] = ["l2"]
        with self.assertRaisesRegex(ValidationError, "earlier lessons"):
            validate_plan(plan, CONCEPTS)


class ReconciliationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.raw = [
            {"id": "r1", "title": "Moss", "evidence": [{"unit_id": "u1", "quote": "Moss holds water"}]},
            {"id": "r2", "title": "Lichen", "evidence": [{"unit_id": "u2", "quote": "Lichen grows"}]},
        ]

    def test_merge_preserves_every_member_and_quote(self) -> None:
        result = {"concepts": [{"title": "Early colonizers", "explanation": "Compare moss and lichen.",
                                "member_ids": ["r1", "r2"],
                                "evidence": self.raw[0]["evidence"] + self.raw[1]["evidence"]}]}
        clean = validate_reconcile(result, self.raw, TEACHING)
        self.assertEqual(len(clean), 1)
        self.assertEqual(clean[0]["member_ids"], ["r1", "r2"])

    def test_dropped_member_evidence_fails(self) -> None:
        result = {"concepts": [{"title": "Early colonizers", "explanation": "Compare moss and lichen.",
                                "member_ids": ["r1", "r2"], "evidence": self.raw[0]["evidence"]}]}
        with self.assertRaisesRegex(ValidationError, "dropped member evidence"):
            validate_reconcile(result, self.raw, TEACHING)

    def test_unassigned_raw_concept_fails(self) -> None:
        result = {"concepts": [{"title": "Moss", "explanation": "Only moss.",
                                "member_ids": ["r1"], "evidence": self.raw[0]["evidence"]}]}
        with self.assertRaisesRegex(ValidationError, "exactly one"):
            validate_reconcile(result, self.raw, TEACHING)

class LessonTests(unittest.TestCase):
    def setUp(self) -> None:
        evidence = [{"unit_id": "u1", "quote": "Moss holds water"}]
        self.planned = {"id": "l1", "title": "First observations", "concept_ids": ["c1"], "prerequisite_ids": []}
        self.lesson = {
            "id": "l1", "title": "First observations", "concept_ids": ["c1"],
            "summary": "Observe what retains water.",
            "sections": [{"heading": "Moss", "body": "It retains water.", "evidence": evidence}],
            "questions": [
                {"id": f"q-{kind}", "kind": kind, "prompt": "What do you notice?", "answer": "Moss retains water.",
                 "rationale": "The source describes retention.", "concept_ids": ["c1"], "evidence": evidence}
                for kind in ("recall", "contrast", "apply")
            ],
            "audio_script": [{"kind": "speech", "text": "Consider the moss."}, {"kind": "pause", "text": "Think before continuing."}],
        }

    def test_valid_lesson_has_all_three_modes(self) -> None:
        self.assertEqual(validate_lesson(self.lesson, self.planned, {"c1": CONCEPTS[0]}, TEACHING)["id"], "l1")

    def test_practice_forms_are_optional(self) -> None:
        lesson = copy.deepcopy(self.lesson)
        lesson["questions"] = [q for q in lesson["questions"] if q["kind"] != "apply"]
        validate_lesson(lesson, self.planned, {"c1": CONCEPTS[0]}, TEACHING)
        lesson["questions"] = []
        validate_lesson(lesson, self.planned, {"c1": CONCEPTS[0]}, TEACHING)

    def test_lesson_must_cover_its_concept_evidence(self) -> None:
        lesson = copy.deepcopy(self.lesson)
        replacement = [{"unit_id": "u1", "quote": "after rain"}]
        lesson["sections"][0]["evidence"] = replacement
        for question in lesson["questions"]:
            question["evidence"] = replacement
        with self.assertRaisesRegex(ValidationError, "outside assigned concepts"):
            validate_lesson(lesson, self.planned, {"c1": CONCEPTS[0]}, TEACHING)

    def test_review_revision_requires_actionable_issue(self) -> None:
        with self.assertRaisesRegex(ValidationError, "explain"):
            validate_review({"status": "revise", "issues": []})


if __name__ == "__main__":
    unittest.main()
