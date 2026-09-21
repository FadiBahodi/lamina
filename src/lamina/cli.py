"""Small, inspectable CLI. Network/model execution is always an explicit choice."""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import shlex
import sys
from pathlib import Path

from . import __version__
from .export import export_bundle
from .ingest import ingest_paths
from .retrieval import search
from .store import Workspace


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(prog="lamina", description="From source material to deliberate learning.")
    cli.add_argument("--version", action="version", version=__version__)
    commands = cli.add_subparsers(dest="command", required=True)
    ingest = commands.add_parser("ingest", help="Import user-owned documents with stable provenance")
    ingest.add_argument("paths", nargs="+", type=Path)
    ingest.add_argument("--workspace", type=Path, default=Path(".lamina"))
    ingest.add_argument("--role", choices=["teaching", "assessment"], default="teaching")
    lookup = commands.add_parser("search", help="Retrieve teaching evidence with transparent rank fusion")
    lookup.add_argument("query")
    lookup.add_argument("--workspace", type=Path, default=Path(".lamina"))
    lookup.add_argument("--limit", type=int, default=8)
    lookup.add_argument("--vectors", type=Path, help="Optional JSON: {query: [...], units: {unit_id: [...]}}")
    lookup.add_argument("--json", action="store_true", help="Print complete evidence records")
    inspect = commands.add_parser("inspect", help="Inspect source and durable-job counts")
    inspect.add_argument("--workspace", type=Path, default=Path(".lamina"))
    build = commands.add_parser("build", help="Generate and review with your configured JSON command adapter")
    build.add_argument("--workspace", type=Path, default=Path(".lamina"))
    build.add_argument("--adapter", required=True, help="Executable and arguments; invoked without a shell")
    build.add_argument("--output", type=Path, default=Path("site"))
    build.add_argument("--workers", type=int, default=4)
    build.add_argument("--timeout", type=float, default=120)
    build.add_argument("--adapter-version", help="Cache identity for your model/config revision (or LAMINA_ADAPTER_VERSION)")
    build.add_argument("--pdf", action="store_true", help="Include a print-ready study book (requires the pdf extra)")
    run = commands.add_parser("run", help="Run a validated teaching procedure with a configured adapter")
    run.add_argument("--procedure", required=True, type=Path, help="Data-only procedure JSON v1")
    run.add_argument("--workspace", type=Path, default=Path(".lamina"))
    run.add_argument("--adapter", required=True, help="Executable and arguments; invoked without a shell")
    run.add_argument("--adapter-version", help="Cache identity for your model/config revision")
    run.add_argument("--timeout", type=float, default=120)
    run.add_argument("--output", type=Path, default=Path("site"))
    studio = commands.add_parser("studio", help="Open the local Studio with an optional startup adapter")
    studio.add_argument("--workspace", type=Path, default=Path(".lamina"))
    studio.add_argument("--port", type=int, default=8048)
    studio.add_argument("--adapter", help="Startup-only JSON command adapter; no credentials in browser")
    studio.add_argument("--adapter-version", help="Cache identity for your model/config revision")
    studio.add_argument("--timeout", type=float, default=120)
    demo = commands.add_parser("demo", help="Run the original curated fixture, offline, with no credentials")
    demo.add_argument("--output", type=Path, default=Path("demo"))
    demo.add_argument("--workspace", type=Path, default=Path(".lamina-demo"))
    demo.add_argument("--workers", type=int, default=4)
    demo.add_argument("--pdf", action="store_true", help="Include a print-ready study book (requires the pdf extra)")
    export = commands.add_parser("export", help="Render an existing bundle to another artifact")
    export.add_argument("bundle", type=Path)
    export.add_argument("--format", choices=["html", "pdf", "markdown"], required=True)
    export.add_argument("--output", type=Path, required=True)
    validate = commands.add_parser("validate", help="Recheck a saved bundle's source and coverage invariants")
    validate.add_argument("bundle", type=Path)
    serve = commands.add_parser("serve", help="Serve an exported site on your local machine")
    serve.add_argument("directory", type=Path)
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--host", default="127.0.0.1", help="Default: loopback only")
    return cli


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "ingest":
            result = ingest_paths(args.paths, Workspace(args.workspace), role=args.role)
        elif args.command == "search":
            vectors = json.loads(args.vectors.read_text()) if args.vectors else {}
            result = search(Workspace(args.workspace).units(), args.query, args.limit,
                            query_vector=vectors.get("query"), vectors=vectors.get("units"))
            if not args.json:
                for unit in result:
                    print(f"{unit['heading']} · {unit['locator']} · {unit['id']}\n{unit['text']}\n")
                if not result:
                    print("No matching teaching evidence.")
                return 0
        elif args.command == "inspect":
            result = Workspace(args.workspace).stats()
        elif args.command in {"build", "demo"}:
            from .pipeline import build
            from .providers import CommandProvider, DemoProvider
            workspace = Workspace(args.workspace)
            if args.command == "demo":
                fixture = Path(__file__).with_name("demo")
                ingest_paths([fixture], workspace)
                provider = DemoProvider()
            else:
                command = shlex.split(args.adapter)
                if not command:
                    raise ValueError("Adapter command cannot be empty")
                provider = CommandProvider(command, timeout=args.timeout, version=args.adapter_version)
            bundle = build(workspace, provider, workers=args.workers)
            from .print_export import export_markdown, export_pdf
            from .validation import validate_bundle
            validate_bundle(bundle)
            args.output.mkdir(parents=True, exist_ok=True)
            export_markdown(bundle, args.output / "study-guide.md")
            bundle["downloads"] = {"markdown": "study-guide.md"}
            if args.pdf:
                export_pdf(bundle, args.output / "study-guide.pdf")
                bundle["downloads"]["pdf"] = "study-guide.pdf"
            export_bundle(bundle, args.output)
            result = {"output": str(args.output), "title": bundle["title"],
                      "lessons": len(bundle["lessons"]), "workspace": workspace.stats(),
                      "next": f"lamina serve {shlex.quote(str(args.output))}"}
        elif args.command == "run":
            from .procedures import validate_procedure
            from .studio_server import make_provider, run_procedure
            procedure = validate_procedure(json.loads(args.procedure.read_text(encoding="utf-8")))
            provider = make_provider(args.adapter, version=args.adapter_version, timeout=args.timeout)
            workspace = Workspace(args.workspace)
            result = run_procedure(workspace, provider, procedure, args.output)
            result = {"output": str(args.output), "procedure": procedure["id"], **result,
                      "workspace": workspace.stats()}
        elif args.command == "studio":
            from .studio_server import StudioServer
            server = StudioServer(args.workspace, port=args.port, adapter=args.adapter,
                                  adapter_version=args.adapter_version, timeout=args.timeout)
            print(f"Lamina Studio at http://127.0.0.1:{server.server_port} · Ctrl-C to stop", flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                server.server_close()
            return 0
        elif args.command == "export":
            from .validation import validate_bundle
            bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
            validate_bundle(bundle)
            if args.format == "html":
                export_bundle(bundle, args.output)
            else:
                from .print_export import export_markdown, export_pdf
                (export_pdf if args.format == "pdf" else export_markdown)(bundle, args.output)
            result = {"output": str(args.output), "format": args.format}
        elif args.command == "validate":
            from .validation import validate_bundle
            bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
            validate_bundle(bundle)
            result = {"valid": True, "title": bundle["title"], "lessons": len(bundle["lessons"])}
        elif args.command == "serve":
            if not (args.directory / "index.html").is_file():
                raise ValueError("Directory must contain an exported index.html")
            handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(args.directory.resolve()))
            server = http.server.ThreadingHTTPServer((args.host, args.port), handler)
            print(f"Lamina at http://{args.host}:{server.server_port} · Ctrl-C to stop", flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                server.server_close()
            return 0
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (OSError, ValueError, RuntimeError, TimeoutError) as exc:
        print(f"lamina: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
