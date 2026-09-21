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
    cli = argparse.ArgumentParser(
        prog="lamina",
        description="Turn source material into useful work. Keep the method.",
    )
    cli.add_argument("--version", action="version", version=__version__)
    commands = cli.add_subparsers(dest="command", required=True)
    ingest = commands.add_parser(
        "ingest", help="Import user-owned documents with stable provenance"
    )
    ingest.add_argument("paths", nargs="+", type=Path)
    ingest.add_argument("--workspace", type=Path, default=Path(".lamina"))
    ingest.add_argument(
        "--role", choices=["teaching", "assessment"], default="teaching"
    )
    lookup = commands.add_parser(
        "search", help="Retrieve teaching evidence with transparent rank fusion"
    )
    lookup.add_argument("query")
    lookup.add_argument("--workspace", type=Path, default=Path(".lamina"))
    lookup.add_argument("--limit", type=int, default=8)
    lookup.add_argument(
        "--vectors",
        type=Path,
        help="Optional JSON: {query: [...], units: {unit_id: [...]}}",
    )
    lookup.add_argument(
        "--json", action="store_true", help="Print complete evidence records"
    )
    inspect = commands.add_parser(
        "inspect", help="Inspect source and durable-job counts"
    )
    inspect.add_argument("--workspace", type=Path, default=Path(".lamina"))
    build = commands.add_parser(
        "build", help="Generate and review with your configured JSON command adapter"
    )
    build.add_argument("--workspace", type=Path, default=Path(".lamina"))
    build.add_argument(
        "--adapter",
        required=True,
        help="Executable and arguments; invoked without a shell",
    )
    build.add_argument("--output", type=Path, default=Path("site"))
    build.add_argument("--workers", type=int, default=4)
    build.add_argument("--timeout", type=float, default=120)
    build.add_argument(
        "--adapter-version",
        help="Cache identity for your model/config revision (or LAMINA_ADAPTER_VERSION)",
    )
    build.add_argument(
        "--pdf",
        action="store_true",
        help="Include a print-ready study book (requires the pdf extra)",
    )
    produce = commands.add_parser(
        "produce",
        help="Plan and produce a source-linked document, script or assessment",
    )
    produce.add_argument(
        "--brief", help="The finished work you want and its intended audience"
    )
    produce.add_argument(
        "--brief-file",
        type=Path,
        help="Read a longer project brief from a UTF-8 text file",
    )
    produce.add_argument(
        "--plan", type=Path, help="Reuse a saved production plan for revision"
    )
    produce.add_argument(
        "--section-notes",
        type=Path,
        help="JSON object mapping section IDs to revision instructions",
    )
    produce.add_argument("--workspace", type=Path, default=Path(".lamina"))
    produce.add_argument(
        "--source-id",
        action="append",
        help="Select a teaching source; otherwise use all teaching sources",
    )
    produce.add_argument(
        "--adapter",
        required=True,
        help="Executable and arguments; invoked without a shell",
    )
    produce.add_argument("--adapter-version")
    produce.add_argument(
        "--audio-adapter", help="Optional speech command for finished podcast scripts"
    )
    produce.add_argument("--audio-adapter-version")
    produce.add_argument(
        "--source-policy",
        type=Path,
        help="JSON mapping source IDs to authority, supplement, historical or form_exemplar",
    )
    produce.add_argument(
        "--observation-id",
        action="append",
        help="Reuse a selected prior operator observation",
    )
    produce.add_argument(
        "--method-family",
        help="Family for retained observations (default: document-production)",
    )
    produce.add_argument("--timeout", type=float, default=120)
    produce.add_argument(
        "--format", choices=["document", "guide", "podcast-script", "assessment"]
    )
    produce.add_argument("--readers", type=int)
    produce.add_argument("--writers", type=int)
    produce.add_argument("--reviewers", type=int)
    produce.add_argument(
        "--retrieval-targets",
        action="store_true",
        default=None,
        help="Merge equivalent retrieval tasks while preserving answer groups (guide or assessment)",
    )
    produce.add_argument("--core-words", type=int)
    produce.add_argument("--halo-units", type=int)
    produce.add_argument("--output", type=Path, default=Path("output/project"))
    run = commands.add_parser(
        "run", help="Run a validated teaching procedure with a configured adapter"
    )
    run.add_argument(
        "--procedure", required=True, type=Path, help="Data-only procedure JSON v1"
    )
    run.add_argument("--workspace", type=Path, default=Path(".lamina"))
    run.add_argument(
        "--adapter",
        required=True,
        help="Executable and arguments; invoked without a shell",
    )
    run.add_argument(
        "--adapter-version", help="Cache identity for your model/config revision"
    )
    run.add_argument("--timeout", type=float, default=120)
    run.add_argument("--output", type=Path, default=Path("site"))
    method = commands.add_parser(
        "method",
        help="Inspect and execute a reusable method with explicit dependencies",
    )
    actions = method.add_subparsers(dest="method_action", required=True)
    method_validate = actions.add_parser(
        "validate", help="Check a method's graph and resource limits"
    )
    method_validate.add_argument("path", type=Path)
    method_run = actions.add_parser(
        "run", help="Execute through an operator-configured adapter"
    )
    method_run.add_argument("--method", type=Path, required=True)
    method_run.add_argument("--task", type=Path, required=True)
    method_run.add_argument("--workspace", type=Path, default=Path(".lamina"))
    method_run.add_argument("--adapter", required=True)
    method_run.add_argument("--adapter-version")
    method_run.add_argument("--timeout", type=float, default=120)
    method_run.add_argument(
        "--output", type=Path, help="Also save the run receipt as JSON"
    )
    method_observe = actions.add_parser(
        "observe", help="Retain an attributed observation for later method selection"
    )
    method_observe.add_argument(
        "path",
        type=Path,
        help="Observation JSON; this does not automatically change a method",
    )
    method_observe.add_argument("--workspace", type=Path, default=Path(".lamina"))
    method_experience = actions.add_parser(
        "experience", help="Retrieve observations for one method family"
    )
    method_experience.add_argument("--family", required=True)
    method_experience.add_argument("--limit", type=int, default=20)
    method_experience.add_argument("--workspace", type=Path, default=Path(".lamina"))
    studio = commands.add_parser(
        "app",
        aliases=["studio"],
        help="Open the local Lamina app with an optional startup adapter",
    )
    studio.add_argument("--workspace", type=Path, default=Path(".lamina"))
    studio.add_argument("--port", type=int, default=8048)
    studio.add_argument(
        "--adapter", help="Startup-only JSON command adapter; no credentials in browser"
    )
    studio.add_argument(
        "--adapter-version", help="Cache identity for your model/config revision"
    )
    studio.add_argument("--timeout", type=float, default=120)
    studio.add_argument("--audio-adapter", help="Startup-only optional speech adapter")
    studio.add_argument("--audio-adapter-version")
    demo = commands.add_parser(
        "demo", help="Run the original curated fixture, offline, with no credentials"
    )
    demo.add_argument("--output", type=Path, default=Path("demo"))
    demo.add_argument("--workspace", type=Path, default=Path(".lamina-demo"))
    demo.add_argument("--workers", type=int, default=4)
    demo.add_argument(
        "--pdf",
        action="store_true",
        help="Include a print-ready study book (requires the pdf extra)",
    )
    export = commands.add_parser(
        "export", help="Render an existing bundle to another artifact"
    )
    export.add_argument("bundle", type=Path)
    export.add_argument("--format", choices=["html", "pdf", "markdown"], required=True)
    export.add_argument("--output", type=Path, required=True)
    validate = commands.add_parser(
        "validate", help="Recheck a saved bundle's source and coverage invariants"
    )
    validate.add_argument("bundle", type=Path)
    serve = commands.add_parser(
        "serve", help="Serve an exported site on your local machine"
    )
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
            result = search(
                Workspace(args.workspace).units(),
                args.query,
                args.limit,
                query_vector=vectors.get("query"),
                vectors=vectors.get("units"),
            )
            if not args.json:
                for unit in result:
                    print(
                        f"{unit['heading']} · {unit['locator']} · {unit['id']}\n{unit['text']}\n"
                    )
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
                provider = CommandProvider(
                    command, timeout=args.timeout, version=args.adapter_version
                )
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
            result = {
                "output": str(args.output),
                "title": bundle["title"],
                "lessons": len(bundle["lessons"]),
                "workspace": workspace.stats(),
                "next": f"lamina serve {shlex.quote(str(args.output))}",
            }
        elif args.command == "produce":
            from .production import plan_production, run_production
            from .production_delivery import deliver_production
            from .studio_server import make_provider

            workspace = Workspace(args.workspace)
            provider = make_provider(
                args.adapter, version=args.adapter_version, timeout=args.timeout
            )
            options = {
                key: value
                for key, value in {
                    "format": args.format,
                    "reader_workers": args.readers,
                    "writer_workers": args.writers,
                    "review_workers": args.reviewers,
                    "core_words": args.core_words,
                    "halo_units": args.halo_units,
                    "source_policy": (
                        json.loads(args.source_policy.read_text(encoding="utf-8"))
                        if args.source_policy
                        else None
                    ),
                    "observation_ids": args.observation_id,
                    "method_family": args.method_family,
                    "retrieval_targets": args.retrieval_targets,
                }.items()
                if value is not None
            }
            if args.plan:
                if args.brief or args.brief_file or args.source_id:
                    raise ValueError(
                        "A saved plan already specifies its goal and sources. Start a new plan to change them."
                    )
                plan = json.loads(args.plan.read_text(encoding="utf-8"))
            else:
                if bool(args.brief) == bool(args.brief_file):
                    raise ValueError(
                        "Choose --brief or --brief-file when creating a project."
                    )
                brief = (
                    args.brief_file.read_text(encoding="utf-8")
                    if args.brief_file
                    else args.brief
                )
                ids = args.source_id or [
                    s["id"] for s in workspace.sources() if s["role"] == "teaching"
                ]
                plan = plan_production(workspace, provider, brief, ids, options)
            if args.section_notes:
                options["section_notes"] = json.loads(
                    args.section_notes.read_text(encoding="utf-8")
                )
            receipt = run_production(workspace, provider, plan, options)
            audio_provider = make_provider(
                args.audio_adapter,
                version=args.audio_adapter_version,
                timeout=args.timeout,
            )
            links = deliver_production(
                workspace, receipt, plan, args.output, audio_provider=audio_provider
            )
            result = {
                "status": receipt["status"],
                "title": receipt["title"],
                "output": str(args.output.resolve()),
                "files": links,
                "metrics": receipt["metrics"],
            }
        elif args.command == "run":
            from .procedures import validate_procedure
            from .studio_server import make_provider, run_procedure

            procedure = validate_procedure(
                json.loads(args.procedure.read_text(encoding="utf-8"))
            )
            provider = make_provider(
                args.adapter, version=args.adapter_version, timeout=args.timeout
            )
            workspace = Workspace(args.workspace)
            result = run_procedure(workspace, provider, procedure, args.output)
            result = {
                "output": str(args.output),
                "procedure": procedure["id"],
                **result,
                "workspace": workspace.stats(),
            }
        elif args.command == "method":
            from .methods import validate_method
            from .method_runtime import run_method, record_observation, list_experience

            if args.method_action == "validate":
                result = validate_method(
                    json.loads(args.path.read_text(encoding="utf-8"))
                )
            elif args.method_action == "run":
                from .studio_server import make_provider

                definition = json.loads(args.method.read_text(encoding="utf-8"))
                task = json.loads(args.task.read_text(encoding="utf-8"))
                provider = make_provider(
                    args.adapter, version=args.adapter_version, timeout=args.timeout
                )
                result = run_method(
                    Workspace(args.workspace), provider, definition, task
                )
                if args.output:
                    args.output.parent.mkdir(parents=True, exist_ok=True)
                    args.output.write_text(
                        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8",
                    )
                if result.get("status") == "failed":
                    print(json.dumps(result, indent=2, ensure_ascii=False))
                    return 1
            elif args.method_action == "observe":
                observation = json.loads(args.path.read_text(encoding="utf-8"))
                if not isinstance(observation, dict):
                    raise ValueError("observation must be a JSON object")
                required = {
                    "family",
                    "method_id",
                    "method_version",
                    "task_digest",
                    "outcome",
                    "applicability",
                }
                if (
                    not required <= observation.keys()
                    or observation.keys() - required - {"failure", "note"}
                ):
                    raise ValueError(
                        "observation requires family, method_id, method_version, task_digest, outcome, applicability; optional failure and note"
                    )
                result = record_observation(Workspace(args.workspace), **observation)
            else:
                result = list_experience(
                    Workspace(args.workspace), args.family, limit=args.limit
                )
        elif args.command in {"app", "studio"}:
            from .studio_server import StudioServer

            server = StudioServer(
                args.workspace,
                port=args.port,
                adapter=args.adapter,
                adapter_version=args.adapter_version,
                timeout=args.timeout,
                audio_adapter=args.audio_adapter,
                audio_adapter_version=args.audio_adapter_version,
            )
            print(
                f"Lamina at http://127.0.0.1:{server.server_port} · Ctrl-C to stop",
                flush=True,
            )
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

                (export_pdf if args.format == "pdf" else export_markdown)(
                    bundle, args.output
                )
            result = {"output": str(args.output), "format": args.format}
        elif args.command == "validate":
            from .validation import validate_bundle

            bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
            validate_bundle(bundle)
            result = {
                "valid": True,
                "title": bundle["title"],
                "lessons": len(bundle["lessons"]),
            }
        elif args.command == "serve":
            if not (args.directory / "index.html").is_file():
                raise ValueError("Directory must contain an exported index.html")
            handler = functools.partial(
                http.server.SimpleHTTPRequestHandler,
                directory=str(args.directory.resolve()),
            )
            server = http.server.ThreadingHTTPServer((args.host, args.port), handler)
            print(
                f"Lamina at http://{args.host}:{server.server_port} · Ctrl-C to stop",
                flush=True,
            )
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
