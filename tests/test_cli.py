"""Run the offline demo through the same CLI a clean install exposes."""

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
                                 capture_output=True, text=True, timeout=60)
        self.assertEqual(process.returncode, 0, process.stderr)
        return json.loads(process.stdout)

    def test_demo_runs_the_production_engine_offline(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "demo"
            workspace = root / "workspace"
            demo = self.run_cli("demo", "--output", output, "--workspace", workspace)
            self.assertEqual(demo["status"], "ready")
            self.assertEqual(demo["sections"], 3)
            for name in ("index.html", "document.md", "plan.json", "report.json"):
                self.assertTrue((output / name).is_file(), name)
            report = json.loads((output / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "ready")
            self.assertTrue(report["sections"])
            found = self.run_cli("search", "lease", "--workspace", workspace, "--json")
            self.assertTrue(found)
            self.assertTrue(all(unit["role"] == "teaching" for unit in found))


if __name__ == "__main__":
    unittest.main()
