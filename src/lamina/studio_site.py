"""Build the same original example collection for hosted and local Studio."""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path


def prepare_studio(output: Path, with_pdf: bool = False) -> Path:
    """Copy Studio assets and create labelled, source-bound example outputs.

    All semantic output here is the bundled curated fixture. This helper never
    calls a remote model and never reads an operator's working collection.
    """
    from .production_example import production_demo
    from .production_export import export_production
    from .method_example import method_demo
    from .export import export_bundle
    from .ingest import ingest_paths
    from .pipeline import build
    from .print_export import export_markdown, export_pdf
    from .procedures import BUILTINS
    from .providers import DemoProvider
    from .samp import export_samp, generate_samp
    from .store import Workspace

    output = Path(output).resolve()
    assets = Path(__file__).with_name("studio")
    output.mkdir(parents=True, exist_ok=True)
    shutil.copytree(assets, output, dirs_exist_ok=True)
    (output / "procedures.json").write_text(json.dumps(BUILTINS, indent=2) + "\n", encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="lamina-studio-example-") as temp:
        workspace = Workspace(Path(temp))
        ingest_paths([Path(__file__).with_name("demo") / "sources"], workspace)
        provider = DemoProvider()
        bundle = build(workspace, provider)
        reader = output / "workbench"
        reader.mkdir(exist_ok=True)
        export_markdown(bundle, reader / "study-guide.md")
        bundle["downloads"] = {"markdown": "study-guide.md"}
        if with_pdf:
            export_pdf(bundle, reader / "study-guide.pdf")
            bundle["downloads"]["pdf"] = "study-guide.pdf"
        export_bundle(bundle, reader)
        export_samp(generate_samp(bundle, provider, workspace), output / "examples" / "samp")
    (output / "method-example.json").write_text(json.dumps(method_demo(), indent=2) + "\n", encoding="utf-8")
    production = production_demo()
    (output / "production-example.json").write_text(json.dumps(production, indent=2) + "\n", encoding="utf-8")
    export_production(production["runs"][0]["receipt"], production["plan"], output / "examples" / "production")
    from .static_assets import fingerprint_page_assets
    fingerprint_page_assets(output)
    return output


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--pdf", action="store_true")
    args = parser.parse_args()
    print(prepare_studio(args.output, with_pdf=args.pdf))
