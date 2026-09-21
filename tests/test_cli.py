"""Run the public offline journey through the same CLI a clean install exposes."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class CLITests(unittest.TestCase):
    def run_cli(self, *args: object) -> dict:
        process = subprocess.run([sys.executable, "-m", "lamina", *map(str, args)],
                                 capture_output=True, text=True, timeout=30)
        self.assertEqual(process.returncode, 0, process.stderr)
        return json.loads(process.stdout)

    def test_demo_site_and_print_exports_from_one_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            site = root / "site"
            workspace = root / "workspace"
            demo = self.run_cli("demo", "--output", site, "--workspace", workspace)
            self.assertEqual(demo["lessons"], 3)
            bundle_path = site / "bundle.json"
            self.assertTrue((site / "index.html").is_file())
            bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
            self.assertEqual(bundle["counters"]["assigned_concepts"], 6)
            self.assertEqual(bundle["counters"]["deferred_concepts"], 0)
            self.assertTrue(all(s["role"] == "teaching" for s in bundle["sources"]))
            markdown = root / "study.md"
            self.run_cli("export", bundle_path, "--format", "markdown", "--output", markdown)
            handout = markdown.read_text(encoding="utf-8")
            self.assertIn("## Answer key", handout)
            self.assertIn("Scenario · candidate brief", handout)
            self.assertIn("Scenario · examiner notes", handout)
            self.assertIn("## Listen scripts", handout)
            try:
                import reportlab  # noqa: F401
            except ImportError:
                return
            pdf = root / "study.pdf"
            self.run_cli("export", bundle_path, "--format", "pdf", "--output", pdf)
            self.assertGreater(pdf.stat().st_size, 1000)
            try:
                from pypdf import PdfReader
            except ImportError:
                return
            pages = "\n".join(page.extract_text() or "" for page in PdfReader(pdf).pages)
            self.assertIn("Scenario", pages)
            self.assertIn("Listen scripts", pages)


if __name__ == "__main__":
    unittest.main()
