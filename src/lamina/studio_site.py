"""Copy the local app's static files, or build the public website."""

from __future__ import annotations

import shutil
from pathlib import Path

from .static_assets import fingerprint_page_assets


def prepare_studio(output: Path) -> Path:
    """Copy the local app's page and scripts into ``output``, replacing any earlier copy.

    Startup never invokes a model, a fixture adapter or an example build.
    """
    output = Path(output).resolve()
    if output.exists():
        shutil.rmtree(output)
    shutil.copytree(Path(__file__).with_name("studio"), output)
    fingerprint_page_assets(output)
    return output


def prepare_website(output: Path) -> Path:
    """Copy the static public website into ``output`` and fingerprint its assets."""
    source = Path(__file__).with_name("site")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, output, dirs_exist_ok=True)
    fingerprint_page_assets(output)
    return output


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(prepare_website(args.output))
