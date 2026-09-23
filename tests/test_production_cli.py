"""The installed CLI uses the configured command adapter and saved revision plan."""

import json
import itertools
import os
import shlex
import subprocess
import sys
from pathlib import Path

from lamina.production_example import SOURCES


def test_production_command_and_saved_plan_revision(tmp_path):
    seeds = itertools.count(1)

    def cli(*args):
        call = subprocess.run(
            [sys.executable, "-m", "lamina", *map(str, args)],
            text=True,
            capture_output=True,
            timeout=30,
            env={**os.environ, "PYTHONHASHSEED": str(next(seeds))},
        )
        assert call.returncode == 0, call.stderr
        return json.loads(call.stdout)

    source_dir = tmp_path / "sources"
    source_dir.mkdir()
    for i, source in enumerate(SOURCES, 1):
        for j, paragraph in enumerate(source["text"].split("\n\n")):
            if not paragraph.startswith("#") and paragraph.strip():
                (source_dir / f"{i}-{j}.txt").write_text(paragraph)
    workspace = tmp_path / "workspace"
    cli("ingest", source_dir, "--workspace", workspace)
    adapter = tmp_path / "adapter.py"
    started = tmp_path / "adapter-started"
    adapter.write_text(
        "import sys,json\nfrom pathlib import Path\n"
        "from lamina.production_example import FixtureAdapter\n"
        f"Path({str(started)!r}).touch()\n"
        'r=json.load(sys.stdin)\njson.dump(FixtureAdapter().call(r["stage"],r),sys.stdout)\n'
    )
    command = shlex.join([sys.executable, str(adapter)])
    # A subprocess cannot communicate an internal Python budget declaration
    # through its replies. The caller must configure the workload explicitly.
    rejected = subprocess.run(
        [
            sys.executable,
            "-m",
            "lamina",
            "produce",
            "--workspace",
            str(workspace),
            "--brief",
            "Explain lease safety.",
            "--workflow",
            "planned",
            "--adapter",
            command,
            "--output",
            str(tmp_path / "unprofiled"),
        ],
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert rejected.returncode != 0
    assert "workload" in rejected.stderr.lower()
    assert not started.exists(), "unprofiled planning invoked the adapter"

    model_config = tmp_path / "models.json"
    model_config.write_text(
        json.dumps(
            {
                "default": {
                    "command": [sys.executable, str(adapter)],
                    "version": "scripted-cli-fixture-v1",
                    "workload": {"*": {"max_items": 16, "basis": "configured"}},
                }
            }
        )
    )
    configured_adapter = "@" + str(model_config)
    first = tmp_path / "first"
    result = cli(
        "produce",
        "--workspace",
        workspace,
        "--brief",
        "Explain lease safety.",
        "--workflow",
        "planned",
        "--readers",
        16,
        "--adapter",
        configured_adapter,
        "--output",
        first,
    )
    assert result["status"] == "ready"
    original = json.loads((first / "report.json").read_text())
    revision = tmp_path / "revision.json"
    revision.write_text(json.dumps({"section_3": "Include the incident ticket ID."}))
    second = tmp_path / "second"
    cli(
        "produce",
        "--workspace",
        workspace,
        "--plan",
        first / "plan.json",
        "--section-notes",
        revision,
        "--adapter",
        configured_adapter,
        "--output",
        second,
    )
    changed = json.loads((second / "report.json").read_text())
    assert original["sections"][:2] == changed["sections"][:2]
    assert "incident ticket ID" in changed["sections"][2]["body"]
    assert changed["metrics"]["cache_misses"] == 2
    assert (second / "index.html").is_file()
