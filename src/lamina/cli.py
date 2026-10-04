"""Small, inspectable CLI. Network/model execution is always an explicit choice."""

from __future__ import annotations

import argparse
from contextlib import ExitStack
import json
import shlex
import sys
from pathlib import Path

from . import __version__
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
    calibration = commands.add_parser(
        "calibrate",
        help="Measure workload settings on your model and save passing profiles",
    )
    calibration.add_argument("--models", required=True, type=Path)
    calibration.add_argument("--output", required=True, type=Path)
    calibration.add_argument(
        "--stage",
        choices=["production_read", "production_write"],
        default="production_read",
    )
    calibration.add_argument(
        "--limits",
        default="12,24,48",
        help="Comma-separated item limits, or token limits with --dimension",
    )
    calibration.add_argument(
        "--dimension", choices=["max_items", "max_input_tokens"], default="max_items"
    )
    calibration.add_argument("--replicates", type=int, default=3)
    calibration.add_argument(
        "--load",
        type=int,
        default=30,
        help="Background paragraphs in the bundled corpus",
    )
    calibration.add_argument(
        "--corpus",
        type=Path,
        help="JSON manifest with source paths, brief and lexical canaries",
    )
    calibration.add_argument("--minimum-fraction", type=float, default=1.0)
    calibration.add_argument("--maximum-counterfacts", type=int, default=0)
    starter = commands.add_parser(
        "starter-profile", help="Write initial per-stage workload settings"
    )
    starter.add_argument("--output", type=Path, required=True)
    ingest = commands.add_parser(
        "ingest", help="Import user-owned documents with stable provenance"
    )
    ingest.add_argument("paths", nargs="+", type=Path)
    ingest.add_argument(
        "--ocr",
        action="store_true",
        help="Run local OCRmyPDF on PDFs; preserve existing text pages",
    )
    ingest.add_argument("--workspace", type=Path, default=Path(".lamina"))
    ingest.add_argument(
        "--role", choices=["teaching", "assessment"], default="teaching"
    )
    lookup = commands.add_parser(
        "search", help="Find source passages using the local text index"
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
        "--format",
        choices=["document", "guide", "podcast-script", "assessment", "cards"],
        help="cards selects the sweep route: read in parallel, deduplicate locally, audit a sample, export Anki-ready cards",
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
    produce.add_argument(
        "--workflow",
        choices=["auto", "direct", "assigned", "planned", "sweep"],
        help="auto uses declared workload limits; planned groups source ideas; sweep reads straight to cards",
    )
    produce.add_argument(
        "--assignments",
        type=Path,
        help="Source assignment JSON from an outer agent; use --workflow assigned",
    )
    produce.add_argument(
        "--workers", type=int, help="Shared maximum simultaneous calls across stages"
    )
    produce.add_argument(
        "--max-input-bytes", type=int, help="Hard request limit; no source truncation"
    )
    produce.add_argument(
        "--reading",
        choices=["task", "reusable"],
        help="Read for this brief (default); reusable shares an inventory across goals and needs coverage evaluation",
    )
    produce.add_argument(
        "--max-attempts",
        type=int,
        help="Maximum attempts per model request, including validation repair (1–5)",
    )
    produce.add_argument(
        "--reader-context-spans",
        type=int,
        help="Boundary halo: show this many sentence spans of each adjacent unit to every reader (0–64; 0 means ask only when needed)",
    )
    produce.add_argument(
        "--reading-failures",
        choices=["abort", "continue"],
        help="continue plans from the successful reads and leaves the receipt in review; abort (default) stops the plan",
    )
    produce.add_argument(
        "--audit-rate",
        type=float,
        help="Sweep route: fraction of reader windows that receive a source-centred audit call (0–1, default 0.25)",
    )
    produce.add_argument(
        "--dedup-threshold",
        type=float,
        help="Sweep route: similarity at or above which a later card is suppressed as a duplicate (default by method)",
    )
    produce.add_argument(
        "--episodes",
        help="Podcast: number of episodes (1–64) or auto (default) to size them from the material",
    )
    produce.add_argument(
        "--episode-minutes",
        type=int,
        help="Podcast: target listening time per episode in minutes (default 20; about 150 spoken words per minute)",
    )
    produce.add_argument(
        "--audio-when",
        choices=["ready", "any"],
        default="any",
        help="any (default) renders a podcast script even while it is in review and names its provisional sections in the audio manifest; ready withholds audio until every check passes",
    )
    produce.add_argument("--output", type=Path, default=Path("output/project"))
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
        "app", help="Open the local Lamina app with an optional startup adapter"
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
        "demo", help="Run the production engine on a bundled fixture, offline"
    )
    demo.add_argument("--output", type=Path, default=Path("demo"))
    demo.add_argument("--workspace", type=Path, default=Path(".lamina-demo"))
    demo.add_argument(
        "--synthetic-latency",
        action="store_true",
        help="Make each fixture call take a fixed time per stage so the run timeline has shape; the receipt labels the timing as synthetic",
    )
    return cli


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    resources = ExitStack()

    def own(provider):
        if provider is not None:
            resources.callback(getattr(provider, "close", lambda: None))
        return provider

    try:
        if args.command == "starter-profile":
            from .calibration import starter_workloads

            with args.output.open("x") as stream:
                json.dump(starter_workloads(), stream, indent=2)
                stream.write("\n")
            result = {"output": str(args.output), "basis": "configured"}
        elif args.command == "calibrate":
            from .calibration import calibrate, read_corpus, write_model_configuration
            from .providers import configured_provider

            provider = own(configured_provider(args.models))
            result = calibrate(
                provider,
                args.output,
                stage=args.stage,
                limits=tuple(int(value) for value in args.limits.split(",")),
                dimension=args.dimension,
                replicates=args.replicates,
                load=args.load,
                corpus=read_corpus(args.corpus) if args.corpus else None,
                minimum_fraction=args.minimum_fraction,
                maximum_counterfacts=args.maximum_counterfacts,
                progress=lambda row: print(
                    json.dumps(row), file=sys.stderr, flush=True
                ),
            )
            result["models"] = write_model_configuration(args.models, result)
        elif args.command == "ingest":
            result = ingest_paths(
                args.paths, Workspace(args.workspace), role=args.role, ocr=args.ocr
            )
        elif args.command == "search":
            vectors = json.loads(args.vectors.read_text()) if args.vectors else {}
            workspace = Workspace(args.workspace)
            result = (
                search(
                    workspace.units("teaching"),
                    args.query,
                    args.limit,
                    query_vector=vectors.get("query"),
                    vectors=vectors.get("units"),
                )
                if vectors
                else workspace.search_units(args.query, args.limit)
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
        elif args.command == "demo":
            from .production_example import DEMO_LATENCY, production_demo
            from .production_export import export_production

            example = production_demo(
                args.workspace, latency=DEMO_LATENCY if args.synthetic_latency else None
            )
            receipt = example["runs"][0]["receipt"]
            links = export_production(receipt, example["plan"], args.output)
            geometry = receipt.get("geometry") or {}
            result = {
                "output": str(args.output),
                "title": receipt.get("title"),
                "status": receipt["status"],
                "sections": len(receipt["sections"]),
                "outputs": links,
                "geometry": {
                    key: geometry.get(key)
                    for key in (
                        "timing", "calls", "workers", "peak_in_flight", "critical_path_depth",
                        "critical_path_ms", "bound_ms", "bound_binding", "wall_ms",
                        "wall_over_bound", "serial_fraction",
                    )
                },
                "workspace": str(args.workspace),
                "next": "lamina app --workspace " + shlex.quote(str(args.workspace)),
            }
        elif args.command == "produce":
            from .production import plan_production, run_production
            from .production_delivery import deliver_production
            from .studio_server import make_provider

            workspace = Workspace(args.workspace)
            provider = own(
                make_provider(
                    args.adapter, version=args.adapter_version, timeout=args.timeout
                )
            )
            options = {
                key: value
                for key, value in {
                    "format": args.format,
                    "workflow": args.workflow,
                    "assignments": (
                        json.loads(args.assignments.read_text())
                        if args.assignments
                        else None
                    ),
                    "workers": args.workers,
                    "max_input_bytes": args.max_input_bytes,
                    "reader_workers": args.readers,
                    "writer_workers": args.writers,
                    "review_workers": args.reviewers,
                    "reading": args.reading,
                    "max_attempts": args.max_attempts,
                    "reader_context_spans": args.reader_context_spans,
                    "reading_failures": args.reading_failures,
                    "audit_rate": args.audit_rate,
                    "dedup_threshold": args.dedup_threshold,
                    "episodes": (
                        None
                        if args.episodes is None
                        else ("auto" if args.episodes == "auto" else int(args.episodes))
                    ),
                    "episode_minutes": args.episode_minutes,
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
            audio_provider = own(
                make_provider(
                    args.audio_adapter,
                    version=args.audio_adapter_version,
                    timeout=args.timeout,
                )
            )
            receipt = run_production(
                workspace,
                provider,
                plan,
                options,
                audio_provider=audio_provider,
                audio_output=args.output,
            )
            links = deliver_production(
                workspace,
                receipt,
                plan,
                args.output,
                audio_provider=audio_provider,
                audio_when=args.audio_when,
            )
            result = {
                "status": receipt["status"],
                "title": receipt["title"],
                "output": str(args.output.resolve()),
                "files": links,
                "metrics": receipt["metrics"],
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
                provider = own(
                    make_provider(
                        args.adapter, version=args.adapter_version, timeout=args.timeout
                    )
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
        elif args.command == "app":
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
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 1 if args.command == "calibrate" and not result["promoted"] else 0
    except (OSError, ValueError, RuntimeError, TimeoutError) as exc:
        print(f"lamina: {exc}", file=sys.stderr)
        return 1
    finally:
        resources.close()


if __name__ == "__main__":
    raise SystemExit(main())
