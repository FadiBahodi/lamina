"""Local project execution, progress and recoverable browser history."""

from __future__ import annotations
import copy
import json
import re
import threading
import time
import uuid

_RUN = re.compile(r"[0-9a-f]{32}\Z")


def _save(server, status):
    output = server.output_root / status["id"]
    output.mkdir(parents=True, exist_ok=True)
    target = output / "project-state.json"
    temp = output / "project-state.tmp"
    compact = dict(status)
    for key in ("plan", "receipt"):
        if status.get(key) is not None:
            artifact = output / f"execution-{key}.json"
            if not artifact.exists():
                pending = artifact.with_suffix(".tmp")
                pending.write_text(
                    json.dumps(status[key], ensure_ascii=False), encoding="utf-8"
                )
                pending.replace(artifact)
            compact.pop(key)
            compact[f"{key}_stored"] = True
    temp.write_text(json.dumps(compact, ensure_ascii=False), encoding="utf-8")
    temp.replace(target)


def restore_projects(server):
    for path in server.output_root.glob("*/project-state.json"):
        if not _RUN.fullmatch(path.parent.name):
            continue
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
            if state.get("id") != path.parent.name or state.get("kind") != "production":
                continue
            for key in ("plan", "receipt"):
                if state.pop(f"{key}_stored", False):
                    state[key] = json.loads(
                        (path.parent / f"execution-{key}.json").read_text(
                            encoding="utf-8"
                        )
                    )
            if state.get("status") in {"running", "queued"}:
                state.update(
                    status="interrupted",
                    error="The app stopped during this project. Resume to reuse completed work.",
                )
            server.runs[state["id"]] = state
        except (ValueError, OSError):
            continue


def start_project(server, body, *, parent=None, section_notes=None):
    from .production import REVISION, _options, plan_production, run_production
    from .production_delivery import deliver_production
    from .source_policy import normalize_production_inputs

    if server.provider is None:
        raise RuntimeError(
            "Start the local app with a model adapter to build from your sources."
        )
    if (
        not isinstance(body, dict)
        or set(body) - {"brief", "source_ids", "options"}
        or not {"brief", "source_ids"} <= set(body)
    ):
        raise ValueError(
            "A project needs a goal, source IDs and optional production settings."
        )
    brief = body["brief"]
    source_ids = body["source_ids"]
    options = body.get("options", {})
    if not isinstance(brief, str) or not 1 <= len(brief.strip()) <= 12000:
        raise ValueError("The goal must contain 1–12000 characters.")
    if (
        not isinstance(source_ids, list)
        or not source_ids
        or len(source_ids) > 2048
        or any(not isinstance(x, str) for x in source_ids)
    ):
        raise ValueError("Choose at least one source.")
    owned = {s["id"] for s in server.workspace.sources() if s["role"] == "teaching"}
    if not set(source_ids) <= owned:
        raise ValueError(
            "All selected sources must be teaching sources in this workspace."
        )
    if not isinstance(options, dict):
        raise ValueError("Production settings must be an object.")
    if parent is None and "section_notes" in options:
        raise ValueError("Create a project first, then revise its named sections.")
    _options({k: v for k, v in options.items() if k != "section_notes"})
    # Fail before creating a run for malformed resource settings.
    for key in ("reader_workers", "writer_workers", "review_workers"):
        if key in options and (
            type(options[key]) is not int or not 1 <= options[key] <= 128
        ):
            raise ValueError(f"{key} must be 1–128.")
    normalized = normalize_production_inputs(
        server.workspace,
        source_ids,
        {k: v for k, v in options.items() if k != "section_notes"},
    )
    options = {
        **normalized["options"],
        **(
            {"section_notes": options["section_notes"]}
            if "section_notes" in options
            else {}
        ),
    }
    plan = copy.deepcopy(parent.get("plan")) if parent else None
    if plan and plan.get("revision") != REVISION:
        raise ValueError(
            "This plan uses an older production format. Start a new project with the same sources and goal; its original files remain available."
        )
    if section_notes is not None:
        if not plan:
            raise ValueError("The earlier project has no saved plan to revise.")
        if (
            not isinstance(section_notes, dict)
            or not section_notes
            or len(section_notes) > 128
            or any(
                not isinstance(k, str)
                or not isinstance(v, str)
                or not v.strip()
                or len(v) > 8000
                for k, v in section_notes.items()
            )
        ):
            raise ValueError("Choose sections and describe each requested change.")
        valid_ids = {s["id"] for s in plan["route"]["sections"]}
        if set(section_notes) - valid_ids:
            raise ValueError("Revision names an unknown section.")
        options = {
            **options,
            "section_notes": {**options.get("section_notes", {}), **section_notes},
        }
    request = {"brief": brief.strip(), "source_ids": source_ids, "options": options}
    with server.run_lock:
        if any(r["status"] in {"running", "queued"} for r in server.runs.values()):
            raise RuntimeError(
                "A project is already running. Its independent workers are executing together."
            )
        rid = uuid.uuid4().hex
        status = {
            "id": rid,
            "kind": "production",
            "status": "queued",
            "created_at": time.time(),
            "error": None,
            "outputs": {},
            "events": [],
            "request": request,
        }
        if parent:
            status["parent_id"] = parent["id"]
        server.runs[rid] = status
        _save(server, status)

    last_progress_save = 0.0

    def progress(event):
        nonlocal last_progress_save
        with server.run_lock:
            status["events"].append({"at": time.time(), **event})
            if len(status["events"]) > 10000:
                status["events"] = status["events"][-10000:]
            now = time.monotonic()
            if now - last_progress_save >= 0.25:
                _save(server, status)
                last_progress_save = now

    def work():
        nonlocal plan
        with server.run_lock:
            status["status"] = "running"
            _save(server, status)
        try:
            if plan is None:
                plan = plan_production(
                    server.workspace,
                    server.provider,
                    request["brief"],
                    source_ids,
                    options,
                    progress=progress,
                )
            with server.run_lock:
                status["plan"] = plan
                _save(server, status)
            receipt = run_production(
                server.workspace, server.provider, plan, options, progress=progress
            )
            links = deliver_production(
                server.workspace,
                receipt,
                plan,
                server.output_root / rid,
                audio_provider=server.audio_provider,
                progress=progress,
            )
            completed = (
                "review" if receipt.get("status") in {"review", "revise"} else "ready"
            )
            with server.run_lock:
                status.update(
                    status=completed,
                    receipt=receipt,
                    outputs={k: f"/outputs/{rid}/{v}" for k, v in links.items()},
                )
                _save(server, status)
        except Exception as exc:
            print(
                f"Lamina project {rid} failed: {type(exc).__name__}: {exc}", flush=True
            )
            with server.run_lock:
                status.update(
                    status="failed",
                    error="The project stopped. See the local console for details; completed work is retained.",
                )
                _save(server, status)

    threading.Thread(target=work, name=f"lamina-project-{rid[:8]}", daemon=True).start()
    return dict(status)


def run_project_example(server):
    """Execute the original fixture without using the operator's live adapter."""
    from .production_example import production_demo
    from .production_export import export_production

    example = production_demo()
    rid = uuid.uuid4().hex
    receipt = example["runs"][0]["receipt"]
    links = export_production(receipt, example["plan"], server.output_root / rid)
    status = {
        "id": rid,
        "kind": "production",
        "status": receipt["status"],
        "example": True,
        "adapter_label": "Deterministic original example",
        "created_at": time.time(),
        "error": None,
        "events": example["events"][
            : 2
            * (
                len(example["plan"]["metrics"]["requests"])
                + len(receipt["metrics"]["requests"])
            )
        ],
        "plan": example["plan"],
        "receipt": receipt,
        "outputs": {k: f"/outputs/{rid}/{v}" for k, v in links.items()},
    }
    with server.run_lock:
        server.runs[rid] = status
        _save(server, status)
    return status


def keep_project_observation(server, run, body):
    from .method_runtime import record_observation

    if run.get("status") not in {"ready", "review"} or not run.get("plan"):
        raise ValueError("Open a finished project before keeping a note.")
    if set(body) != {"note", "applicability", "outcome"}:
        raise ValueError("A note needs its observation, applicability and outcome.")
    for value in body.values():
        if (
            not isinstance(value, str)
            or not value.strip()
            or len(value) > 4000
            or "\x00" in value
        ):
            raise ValueError("Each note field must contain 1–4000 characters.")
    plan = run["plan"]
    return record_observation(
        server.workspace,
        family=plan["options"].get("method_family", "document-production"),
        method_id="source-aware-production",
        method_version=plan["revision"],
        task_digest=plan["plan_digest"],
        **body,
    )
