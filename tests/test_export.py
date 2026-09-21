"""Static export must preserve data without allowing data to end a script tag."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from lamina.export import export_bundle
from lamina.print_export import export_markdown, export_pdf
from test_pipeline import MemoryWorkspace, SpyProvider
from lamina.pipeline import build


class ExportTests(unittest.TestCase):
    def test_file_export_escapes_script_terminators_and_round_trips(self) -> None:
        bundle = build(MemoryWorkspace(), SpyProvider())
        bundle["title"] = "</script><script>alert(1)</script>"
        bundle["plan"]["title"] = bundle["title"]
        bundle["description"] = "Line one\u2028line two"
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            export_bundle(bundle, output)
            js = (output / "data.js").read_text(encoding="utf-8")
            self.assertNotIn("</script>", js)
            self.assertNotIn("\u2028", js)
            self.assertEqual(json.loads((output / "bundle.json").read_text(encoding="utf-8")), bundle)
            self.assertTrue((output / "index.html").is_file())

    def test_markdown_keeps_prompts_before_answer_key_and_source_ledger(self) -> None:
        bundle = build(MemoryWorkspace(), SpyProvider())
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "lesson.md"
            export_markdown(bundle, output)
            content = output.read_text(encoding="utf-8")
            self.assertLess(content.index("#### Practice"), content.index("## Answer key"))
            self.assertLess(content.index("## Answer key"), content.index("Moss retains water."))
            self.assertIn("guide.md", content)
            self.assertIn("line 1", content)
            self.assertNotIn("SECRET ASSESSMENT ANSWER", content)

    def test_pdf_has_lesson_practice_answer_key_and_source_ledger(self) -> None:
        try:
            from pypdf import PdfReader
            import reportlab  # noqa: F401
        except ImportError:
            self.skipTest("optional PDF dependencies are unavailable")
        bundle = build(MemoryWorkspace(), SpyProvider())
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "lesson.pdf"
            export_pdf(bundle, output)
            reader = PdfReader(output)
            self.assertGreaterEqual(len(reader.pages), 4)
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            self.assertIn("Practice", text)
            self.assertIn("Answer key", text)
            self.assertIn("guide.md", text)
            self.assertNotIn("SECRET ASSESSMENT ANSWER", text)

    def test_print_exports_reject_assessment_rows(self) -> None:
        bundle = build(MemoryWorkspace(), SpyProvider())
        bundle["units"].append({"id": "a1", "source_id": "s2", "role": "assessment", "text": "secret"})
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "held-out"):
                export_markdown(bundle, Path(temp) / "bad.md")

    def test_unknown_fields_cannot_be_smuggled_into_public_artifacts(self) -> None:
        clean = build(MemoryWorkspace(), SpyProvider())
        insertions = {
            "top-level": lambda d: d.__setitem__("private_notes", "synthetic extra field"),
            "source": lambda d: d["sources"][0].__setitem__("private_notes", "synthetic extra field"),
            "plan": lambda d: d["plan"].__setitem__("private_notes", "synthetic extra field"),
            "lesson": lambda d: d["lessons"][0].__setitem__("private_notes", "synthetic extra field"),
            "section": lambda d: d["lessons"][0]["sections"][0].__setitem__("private_notes", "synthetic extra field"),
            "question": lambda d: d["lessons"][0]["questions"][0].__setitem__("private_notes", "synthetic extra field"),
            "evidence": lambda d: d["lessons"][0]["sections"][0]["evidence"][0].__setitem__("private_notes", "synthetic extra field"),
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for label, insert in insertions.items():
                forged = copy.deepcopy(clean)
                insert(forged)
                for export, suffix in ((export_bundle, "html"), (export_markdown, "md"), (export_pdf, "pdf")):
                    with self.subTest(field=label, format=suffix):
                        with self.assertRaises(ValueError):
                            export(forged, root / f"{label}.{suffix}")


if __name__ == "__main__":
    unittest.main()
