"""Export a validated learning bundle as a dependency-free static workbench."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from .validation import validate_bundle


def export_bundle(bundle: dict, output: Path) -> None:
    """Write a site that works over HTTP and directly from ``file://``.

    The pipeline owns semantic and evidence validation. This layer deliberately
    serializes its accepted bundle without inventing citations or scores.
    """
    validate_bundle(bundle)

    output = Path(output)
    template = Path(__file__).with_name("web")
    if not template.is_dir():
        raise FileNotFoundError(f"Packaged web template is missing: {template}")
    output.mkdir(parents=True, exist_ok=True)
    for asset in template.iterdir():
        destination = output / asset.name
        if asset.is_dir():
            shutil.copytree(asset, destination, dirs_exist_ok=True)
        elif asset.is_file():
            shutil.copy2(asset, destination)

    serialized = json.dumps(bundle, ensure_ascii=False, separators=(",", ":"))
    # data.js is loaded through a script tag to support file://. Escape the
    # characters that can terminate a script tag or alter JS line parsing.
    safe_js = (
        serialized.replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
    (output / "data.js").write_text(
        "window.LAMINA_BUNDLE = " + safe_js + ";\n", encoding="utf-8"
    )
    (output / "bundle.json").write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
