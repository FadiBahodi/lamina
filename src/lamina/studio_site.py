"""Build the public website or copy assets for the local application."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path


_GENERATED_EXAMPLES = (
    "workbench",
    "examples/samp",
    "examples/production",
    "examples/production-revised",
    "method-example.json",
    "production-example.json",
)
_RETIRED_STUDIO_ASSETS = (
    "inspector.js", "inspector.css", "method-trace.js",
    "assets/experience-leases.svg", "assets/lease-timeline.svg", "assets/pipeline.svg",
    "assets/lamina-technical-paper.pdf",
)


def _remove_generated_examples(output: Path) -> None:
    """Remove only the old builder's known fixture destinations on rebuild."""
    for relative in _GENERATED_EXAMPLES:
        path = output / relative
        if not path.parent.resolve().is_relative_to(output):
            continue
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)


def _remove_old_studio_assets(output: Path, *, retired_only: bool = False) -> None:
    """Retire known local-app assets without clearing an arbitrary output folder."""
    assets = Path(__file__).with_name("studio")
    sources = [assets / name for name in _RETIRED_STUDIO_ASSETS]
    if not retired_only:
        sources.extend(source for source in assets.rglob("*") if source.is_file())
    for source in sources:
        target = output / source.relative_to(assets)
        if not target.parent.resolve().is_relative_to(output):
            continue
        if target.is_file() or target.is_symlink():
            target.unlink()
        # Earlier builds created content-addressed copies alongside each asset.
        if source.suffix in {".css", ".js", ".svg"}:
            pattern = re.compile(
                rf"{re.escape(source.stem)}\.[0-9a-f]{{12}}{re.escape(source.suffix)}"
            )
            if target.parent.is_dir():
                for previous in target.parent.iterdir():
                    if pattern.fullmatch(previous.name) and (
                        previous.is_file() or previous.is_symlink()
                    ):
                        previous.unlink()
    procedures = output / "procedures.json"
    if not retired_only and (procedures.is_file() or procedures.is_symlink()):
        procedures.unlink()


def prepare_studio(output: Path, with_pdf: bool = False) -> Path:
    """Copy the local app and procedure definitions without generating content.

    ``with_pdf`` remains accepted for callers using the previous signature.
    Startup never invokes a model, a fixture provider or an example build.
    """
    from .procedures import BUILTINS
    from .static_assets import fingerprint_page_assets

    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    _remove_generated_examples(output)
    _remove_old_studio_assets(output, retired_only=True)
    shutil.copytree(
        Path(__file__).with_name("studio"), output, dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("production-example.json", "method-example.json"),
    )
    (output / "procedures.json").write_text(
        json.dumps(BUILTINS, indent=2) + "\n", encoding="utf-8"
    )
    fingerprint_page_assets(output)
    return output


def prepare_website(output: Path) -> Path:
    """Build the static public overview, independently of the local application."""
    from .static_assets import fingerprint_page_assets

    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    _remove_generated_examples(output)
    _remove_old_studio_assets(output)
    shutil.copytree(Path(__file__).with_name("site"), output, dirs_exist_ok=True)
    fingerprint_page_assets(output)
    return output


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--pdf", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    print(prepare_website(args.output))
