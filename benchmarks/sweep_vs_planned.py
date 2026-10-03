"""Compare the sweep and planned routes on the same material with a live adapter.

The two arms make different products: the sweep makes a card deck and the
planned route makes a guide, document or podcast script, so this is a
comparison of two workflow experiences on one source, cold cache per run.
It cannot show that one arm produced the same required result faster; for a
matched-plan comparison of execution policies use ``compare_execution.py``.

Recorded per run: wall time from the production call, time to the first
output a person could use (the sweep's deck written to disk; the planned
route's first section leaving review), completion status, call counts,
reported token usage, output density, and optionally which planted canary
distinctions survive. Run order alternates between runs so neither arm always
goes first, and every workspace and output directory is kept unless
``--discard-workspaces`` is given.

    python benchmarks/sweep_vs_planned.py --adapter @models.json \\
        --files chapter.pdf --runs 3 --output results/sweep-vs-planned.json

Add ``--audio-adapter`` to pass a speech adapter into the planned (podcast)
arm so synthesis overlaps writing, and ``--canaries canaries.txt`` (one
distinction per line). Human-judged coverage still has to be done by a human.
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path


def _ingest(files, workspace_dir):
    from lamina.ingest import ingest_paths
    from lamina.store import Workspace

    workspace = Workspace(workspace_dir)
    ingest_paths([Path(f) for f in files], workspace)
    ids = [s["id"] for s in workspace.sources() if s["role"] == "teaching"]
    units = workspace.units("teaching", ids)
    pages = len({(u["source_id"], u.get("page")) for u in units if u.get("page") is not None})
    return workspace, ids, len(units), pages or None


def _canaries(path):
    if not path:
        return []
    return [line.strip() for line in Path(path).read_text().splitlines() if line.strip()]


def _survivors(canaries, text):
    low = text.casefold()
    return [c for c in canaries if c.casefold() in low]


def _run(route, files, adapter, audio, brief, canaries, options):
    from lamina.production import build_production
    from lamina.production_delivery import deliver_production
    from lamina.production_export import export_production
    from lamina.studio_server import make_provider

    workspace_dir = Path(tempfile.mkdtemp(prefix=f"lamina-bench-{route}-"))
    output_dir = workspace_dir / "out"
    record = {"route": route, "workspace": str(workspace_dir)}
    started = None
    provider = make_provider(adapter)
    audio_provider = make_provider(audio) if audio else None
    try:
        workspace, ids, unit_count, pages = _ingest(files, workspace_dir / "ws")
        record.update(source_units=unit_count, pages=pages)
        basis = pages or unit_count
        record["density_basis"] = "pages" if pages else "source_units"
        started = time.monotonic()
        receipt = build_production(
            workspace,
            provider,
            brief,
            ids,
            options,
            audio_provider=audio_provider,
            audio_output=output_dir if audio_provider is not None else None,
        )
        if route == "sweep":
            # The deck is usable once it is on disk, not when reading ends.
            export_production(receipt, receipt["plan"], output_dir)
            record["first_useful_s"] = round(time.monotonic() - started, 3)
        record["wall_s"] = round(time.monotonic() - started, 3)
        metrics = receipt["metrics"]
        plan = receipt["plan"]
        record.update(
            status=receipt["status"],
            calls=metrics.get("provider_attempts"),
            failed_requests=metrics.get("failed_requests"),
            retry_attempts=metrics.get("retry_attempts"),
            usage=metrics.get("usage"),
            unresolved_reader_windows=metrics.get("unresolved_reader_windows", 0),
        )
        if route != "sweep":
            record["first_useful_s"] = (
                round((plan["metrics"]["wall_ms"] + (metrics.get("first_useful_output_ms") or 0)) / 1000, 3)
                if metrics.get("first_useful_output_ms") is not None
                else None
            )
        if route == "sweep":
            record.update(
                cards=metrics.get("cards"),
                suppressed_duplicates=metrics.get("suppressed_duplicates"),
                audited_windows=metrics.get("audited_windows"),
                audit_findings=metrics.get("audit_findings"),
                density=(round(metrics["cards"] / basis, 2) if basis and metrics.get("cards") else None),
            )
            text = receipt["markdown"]
        else:
            record.update(
                ideas=plan["metrics"].get("extracted_ideas"),
                sections=metrics.get("sections"),
                initial_flagged_sections=metrics.get("initial_flagged_sections"),
                remaining_flagged_sections=metrics.get("remaining_flagged_sections"),
                hierarchy_levels=plan["planning"]["routing"].get("hierarchy_levels"),
                density=(round(plan["metrics"]["extracted_ideas"] / basis, 2) if basis and plan["metrics"].get("extracted_ideas") else None),
            )
            text = receipt["markdown"]
            delivery_started = time.monotonic()
            deliver_production(workspace, receipt, plan, output_dir, audio_provider=audio_provider)
            record["delivery_s"] = round(time.monotonic() - delivery_started, 3)
            if audio_provider is not None:
                record["audio_status"] = receipt.get("audio_delivery", {}).get("status")
                record["speech_prefetch"] = metrics.get("speech_prefetch")
        if canaries:
            found = _survivors(canaries, text)
            record["canaries"] = {"total": len(canaries), "found": len(found), "missing": [c for c in canaries if c not in found]}
    except Exception as exc:
        record.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        metrics = getattr(exc, "metrics", None)
        if isinstance(metrics, dict):
            record.update(calls=metrics.get("provider_attempts"), usage=metrics.get("usage"))
        record["wall_s"] = round(time.monotonic() - started, 3) if started else None
    finally:
        for p in (provider, audio_provider):
            close = getattr(p, "close", None)
            if callable(close):
                close()
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--adapter", required=True, help="@models.json or an adapter command")
    parser.add_argument("--audio-adapter", help="Optional speech adapter for the planned (podcast) arm")
    parser.add_argument("--files", nargs="+", required=True, type=Path)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--brief", default="Exam preparation on this material.")
    parser.add_argument("--planned-format", default="guide", choices=["guide", "document", "podcast-script"])
    parser.add_argument("--canaries", type=Path, help="Text file, one planted distinction per line")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--discard-workspaces", action="store_true", help="Delete each run's workspace and outputs after recording it")
    args = parser.parse_args(argv)
    canaries = _canaries(args.canaries)
    arms = {
        "sweep": {"format": "cards"},
        "planned": {"format": args.planned_format, "workflow": "planned"},
    }
    results = {
        "created": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "files": [str(f) for f in args.files],
        "runs": args.runs,
        "brief": args.brief,
        "arms": arms,
        "records": [],
        "scope": "Two products (card deck; planned guide/document/script) from the same files, cold cache per run, alternating order. Latency and status are measured; first_useful_s is the deck on disk or the first section leaving review; coverage is a lexical proxy unless judged by hand. Not a same-result speed comparison.",
    }
    for run in range(1, args.runs + 1):
        order = list(arms.items())
        if run % 2 == 0:
            order.reverse()
        for route, options in order:
            print(f"run {run} {route} …", flush=True)
            record = _run(route, args.files, args.adapter, args.audio_adapter if route == "planned" else None, args.brief, canaries, options)
            record["run"] = run
            results["records"].append(record)
            print(
                f"  {record.get('status')} in {record.get('wall_s')} s; calls={record.get('calls')} "
                f"density={record.get('density')} first_useful={record.get('first_useful_s')}",
                flush=True,
            )
            if args.discard_workspaces:
                shutil.rmtree(record.pop("workspace"), ignore_errors=True)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(results, indent=2) + "\n")
    print(f"wrote {args.output}")
    for route in arms:
        rows = [r for r in results["records"] if r["route"] == route]
        done = [r for r in rows if r.get("status") in {"ready", "review"}]
        walls = sorted(r["wall_s"] for r in done if r.get("wall_s"))
        median = walls[len(walls) // 2] if walls else None
        print(f"{route}: completed {len(done)}/{len(rows)}; median wall {median} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
