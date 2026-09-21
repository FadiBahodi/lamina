"""Durability, identity, role, and transparent ranking behavior."""

from __future__ import annotations

import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from lamina.ingest import ingest_paths, read_source
from lamina.retrieval import search
from lamina.store import Workspace


class CacheTests(unittest.TestCase):
    def test_cache_survives_new_workspace_and_changes_with_identity_or_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = Workspace(root)
            calls = []

            def handler(payload):
                calls.append(payload["value"])
                return {"answer": payload["value"]}

            self.assertEqual(workspace.run_cached("extract", {"value": 1}, handler, identity="adapter-v1"), {"answer": 1})
            reopened = Workspace(root)
            self.assertEqual(reopened.run_cached("extract", {"value": 1}, handler, identity="adapter-v1"), {"answer": 1})
            self.assertEqual(reopened.run_cached("extract", {"value": 1}, handler, identity="adapter-v2"), {"answer": 1})
            self.assertEqual(reopened.run_cached("extract", {"value": 2}, handler, identity="adapter-v2"), {"answer": 2})
            self.assertEqual(calls, [1, 1, 2])
            self.assertEqual(reopened.stats()["attempts"], 3)

    def test_transient_failure_retries_then_persists_success(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = Workspace(Path(temp))
            calls = 0

            def flaky(payload):
                nonlocal calls
                calls += 1
                if calls == 1:
                    raise RuntimeError("temporary failure")
                return {"ok": True}

            self.assertEqual(workspace.run_cached("review", {}, flaky, identity="adapter-v1", retries=1), {"ok": True})
            self.assertEqual(calls, 2)
            self.assertEqual(workspace.stats()["attempts"], 2)

    def test_parallel_callers_share_one_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = Workspace(Path(temp))
            calls = 0

            def handler(payload):
                nonlocal calls
                calls += 1
                return {"result": "shared"}

            with ThreadPoolExecutor(max_workers=4) as pool:
                futures = [pool.submit(workspace.run_cached, "extract", {"id": "same"}, handler,
                                       identity="adapter-v1") for _ in range(4)]
                self.assertEqual([f.result() for f in futures], [{"result": "shared"}] * 4)
            self.assertEqual(calls, 1)

    def test_expired_claim_can_be_recovered(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = Workspace(Path(temp), lease_seconds=1)
            payload = {"unit": "u1"}
            workspace.run_cached("extract", payload, lambda _: {"version": 1}, identity="same")
            with workspace.connection() as db:
                db.execute("UPDATE jobs SET status='running',owner='abandoned',lease_until=?,result=NULL", (time.time() - 5,))
            result = workspace.run_cached("extract", payload, lambda _: {"version": 2}, identity="same", retries=0)
            self.assertEqual(result, {"version": 2})
            self.assertEqual(workspace.stats()["attempts"], 2)

    def test_old_owner_cannot_commit_after_claim_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = Workspace(Path(temp), lease_seconds=1)

            def displaced(payload):
                with workspace.connection() as db:
                    db.execute("UPDATE jobs SET owner='replacement',lease_until=? WHERE status='running'",
                               (time.time() + 10,))
                return {"should_not_publish": True}

            with self.assertRaisesRegex(RuntimeError, "lease was lost"):
                workspace.run_cached("extract", {"unit": "u1"}, displaced, identity="same", retries=0)
            with workspace.connection() as db:
                row = db.execute("SELECT status,result,owner FROM jobs").fetchone()
            self.assertEqual(row["status"], "running")
            self.assertIsNone(row["result"])
            self.assertEqual(row["owner"], "replacement")


class IngestTests(unittest.TestCase):
    def test_duplicate_input_is_idempotent_and_assessment_role_cannot_flip(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            document = root / "guide.md"
            document.write_text("# Rain\n\nWater collects in the valley.\n", encoding="utf-8")
            workspace = Workspace(root / "workspace")
            first = ingest_paths([document], workspace)
            second = ingest_paths([document], workspace)
            self.assertEqual(first["new_sources"], 1)
            self.assertEqual(second["duplicates"], 1)
            self.assertEqual(len(workspace.units()), 1)
            with self.assertRaisesRegex(ValueError, "another source role"):
                ingest_paths([document], workspace, role="assessment")

    def test_text_pdf_keeps_page_locators_without_exporting_absolute_path(self) -> None:
        try:
            import reportlab  # noqa: F401
            import pypdf  # noqa: F401
            from reportlab.pdfgen import canvas
        except ImportError:
            self.skipTest("optional PDF dependencies are unavailable")
        with tempfile.TemporaryDirectory() as temp:
            pdf = Path(temp) / "observations.pdf"
            page = canvas.Canvas(str(pdf))
            page.drawString(72, 720, "Moss holds water after rain.")
            page.showPage()
            page.drawString(72, 720, "Lichen grows on bare rock.")
            page.save()
            source, units = read_source(pdf)
            self.assertEqual([u["locator"] for u in units], ["page 1", "page 2"])
            self.assertIn("Moss holds water", units[0]["text"])
            self.assertIn("Lichen grows", units[1]["text"])
            self.assertNotIn(str(pdf.parent), str(source))

    def test_image_only_pdf_page_is_not_silently_skipped(self) -> None:
        try:
            import reportlab  # noqa: F401
            import pypdf  # noqa: F401
            from reportlab.pdfgen import canvas
        except ImportError:
            self.skipTest("optional PDF dependencies are unavailable")
        with tempfile.TemporaryDirectory() as temp:
            pdf = Path(temp) / "mixed.pdf"
            page = canvas.Canvas(str(pdf))
            page.drawString(72, 720, "First page has text.")
            page.showPage()
            page.rect(72, 680, 100, 100)
            page.save()
            with self.assertRaisesRegex(ValueError, "page 2.*no extractable text"):
                read_source(pdf)


class RetrievalTests(unittest.TestCase):
    def test_rank_is_deterministic_and_held_out_units_are_excluded(self) -> None:
        units = [
            {"id": "b", "heading": "Rain", "text": "Rain collects here.", "role": "teaching"},
            {"id": "a", "heading": "Rain", "text": "Rain collects here.", "role": "teaching"},
            {"id": "secret", "heading": "Rain", "text": "Rain rain rain", "role": "assessment"},
        ]
        forward = search(units, "rain")
        backward = search(list(reversed(units)), "rain")
        self.assertEqual([x["id"] for x in forward], ["a", "b"])
        self.assertEqual([x["id"] for x in forward], [x["id"] for x in backward])
        self.assertEqual(set(forward[0]["lanes"]), {"body", "heading"})

    def test_optional_vector_lane_is_reported_not_implied(self) -> None:
        units = [{"id": "a", "heading": "Field", "text": "moss", "role": "teaching"}]
        self.assertNotIn("vector", search(units, "moss")[0]["lanes"])
        self.assertIn("vector", search(units, "moss", query_vector=[1, 0], vectors={"a": [1, 0]})[0]["lanes"])


if __name__ == "__main__":
    unittest.main()
