"""Compile the LaTeX engineering paper and refresh the packaged public asset.

Requires Tectonic on PATH. It downloads TeX dependencies on the first build.
"""

from __future__ import annotations
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    executable = shutil.which("tectonic")
    if executable is None:
        raise SystemExit("Install Tectonic, then rerun: python tools/build_paper.py")
    output = ROOT / "output" / "pdf"
    output.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            executable,
            "-X",
            "compile",
            str(ROOT / "docs/paper/lamina.tex"),
            "--outdir",
            str(output),
        ],
        check=True,
    )
    target = output / "lamina-technical-paper.pdf"
    (output / "lamina.pdf").replace(target)
    asset = ROOT / "src/lamina/studio/assets/lamina-technical-paper.pdf"
    asset.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(target, asset)
    print(target)


if __name__ == "__main__":
    main()
