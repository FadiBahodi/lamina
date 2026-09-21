"""Run the original example without a model account and export its artifacts."""

from pathlib import Path
import argparse
import json
from lamina.production_example import production_demo
from lamina.production_export import export_production

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=Path, default=Path("output/example"))
args = parser.parse_args()
example = production_demo()
args.output.mkdir(parents=True, exist_ok=True)
(args.output / "example.json").write_text(json.dumps(example, indent=2) + "\n")
for n, run in enumerate(example["runs"], 1):
    files = export_production(run["receipt"], example["plan"], args.output / str(n))
    print(
        json.dumps(
            {"run": run["title"], "output": str(args.output / str(n)), "files": files}
        )
    )
