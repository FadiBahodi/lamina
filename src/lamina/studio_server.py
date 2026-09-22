"""Loopback-only Studio API and static output host.

The adapter is selected at server startup, never by an HTTP request. Uploaded
text is reference material, not an executable instruction or filesystem path.
"""

from __future__ import annotations

import base64
import copy
import binascii
import json
import mimetypes
import re
import shlex
import tempfile
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .export import export_bundle
from .ingest import read_source
from .method_runtime import record_observation, run_method
from .methods import validate_method
from .pipeline import build
from .procedures import BUILTINS, validate_procedure
from .providers import CommandProvider
from .store import Workspace, canonical
from .validation import validate_bundle

MAX_BODY = 8_000_000
MAX_FILES = 12
MAX_FILE_CHARS = 500_000
MAX_PDF_BYTES = 5_000_000
MAX_METHOD_TASK_CHARS = 500_000
SAFE_NAME = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9._ -]{0,119}\.(?:md|txt|pdf|pptx)\Z", re.I
)
RUN_ID = re.compile(r"[0-9a-f]{32}\Z")


def make_provider(
    adapter: str | None, *, version: str | None = None, timeout: float = 120
):
    if not adapter:
        return None
    if adapter.startswith("@"):
        from .providers import configured_provider

        return configured_provider(adapter[1:])
    command = shlex.split(adapter)
    if not command:
        raise ValueError("adapter command cannot be empty")
    return CommandProvider(command, timeout=timeout, version=version)


def run_procedure(
    workspace: Workspace, provider, procedure: dict, output: Path
) -> dict:
    """Generate selected artifacts through the same validated path as the CLI."""
    selected = validate_procedure(procedure)
    if provider is None:
        raise ValueError(
            "A local adapter must be configured before running a procedure"
        )
    bundle = build(workspace, provider, workers=selected["workers"], procedure=selected)
    validate_bundle(bundle)
    if "oral-case" in selected["outputs"] and not any(
        lesson.get("scenario") for lesson in bundle["lessons"]
    ):
        raise ValueError("oral-case procedure produced no reviewed scenario")
    output.mkdir(parents=True, exist_ok=True)
    (output / "procedure.json").write_text(
        json.dumps(selected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    links = {"site": "", "bundle": "bundle.json", "procedure": "procedure.json"}
    if "study-guide" in selected["outputs"]:
        from .print_export import export_markdown

        export_markdown(bundle, output / "study-guide.md")
        bundle["downloads"] = {"markdown": "study-guide.md"}
        links["study_guide"] = "study-guide.md"
    export_bundle(bundle, output)
    if "samp" in selected["outputs"]:
        from .samp import export_samp, generate_samp

        artifact = generate_samp(bundle, provider, workspace, procedure=selected)
        export_samp(artifact, output)
        links["samp"] = "samp.md"
    if "audio-script" in selected["outputs"]:
        scripts = [
            {
                "lesson_id": lesson["id"],
                "title": lesson["title"],
                "script": lesson["audio_script"],
            }
            for lesson in bundle["lessons"]
        ]
        (output / "audio-script.json").write_text(
            json.dumps(scripts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        links["audio_script"] = "audio-script.json"
    # Oral-case practice is already a required, reviewed field in every lesson.
    if "oral-case" in selected["outputs"]:
        links["oral_case"] = ""
    return {"title": bundle["title"], "lessons": len(bundle["lessons"]), "links": links}


def validate_method_task(task: object) -> dict:
    """Bound browser-supplied reference data without interpreting it as a path."""
    if (
        not isinstance(task, dict)
        or len(task) > 64
        or any(not isinstance(key, str) or not key or len(key) > 100 for key in task)
    ):
        raise ValueError(
            "method task must be an object with at most 64 short field names"
        )
    if len(canonical(task)) > MAX_METHOD_TASK_CHARS:
        raise OverflowError("method task exceeds the 500,000-character limit")
    return task


def public_method_receipt(receipt: dict) -> dict:
    """Keep node outcomes inspectable without exposing adapter stderr/paths."""
    cleaned = json.loads(json.dumps(receipt, ensure_ascii=False))
    for node in cleaned["nodes"].values():
        if "error" in node:
            node["error"] = "Node failed; see the local Studio console"
    return cleaned


class StudioServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        workspace: Path,
        *,
        port: int = 8048,
        adapter: str | None = None,
        adapter_version: str | None = None,
        audio_adapter: str | None = None,
        audio_adapter_version: str | None = None,
        timeout: float = 120,
    ):
        self.workspace = Workspace(workspace)
        self.provider = make_provider(adapter, version=adapter_version, timeout=timeout)
        self.audio_provider = make_provider(
            audio_adapter, version=audio_adapter_version, timeout=timeout
        )
        self.output_root = self.workspace.root / "outputs"
        self.output_root.mkdir(parents=True, exist_ok=True)
        from .studio_site import prepare_studio

        self.asset_root = prepare_studio(
            self.workspace.root / "studio-static"
        ).resolve()
        self.runs: dict[str, dict] = {}
        self.run_lock = threading.Lock()
        from .project_api import restore_projects

        restore_projects(self)
        super().__init__(("127.0.0.1", port), StudioHandler)

    def start_run(self, procedure: dict) -> dict:
        if self.provider is None:
            raise RuntimeError(
                "No adapter configured. Start Studio with --adapter to generate from your sources."
            )
        selected = validate_procedure(procedure)
        with self.run_lock:
            if any(
                run["status"] in {"queued", "running"} for run in self.runs.values()
            ):
                raise RuntimeError("A build is already running in this workspace")
            run_id = uuid.uuid4().hex
            status = {"id": run_id, "status": "queued", "error": None, "outputs": {}}
            self.runs[run_id] = status

        def work():
            with self.run_lock:
                status["status"] = "running"
            try:
                result = run_procedure(
                    self.workspace, self.provider, selected, self.output_root / run_id
                )
                links = {
                    key: f"/outputs/{run_id}/{value}"
                    for key, value in result["links"].items()
                }
                with self.run_lock:
                    status.update(
                        status="ready",
                        outputs=links,
                        title=result["title"],
                        lessons=result["lessons"],
                    )
            except Exception as exc:
                # Exceptions can contain local paths, command arguments, or
                # adapter stderr. Keep them on the local console, not in JSON.
                print(f"Lamina run {run_id} failed: {exc}", flush=True)
                with self.run_lock:
                    status.update(
                        status="failed",
                        error=f"{type(exc).__name__}: build failed; see the local Studio console",
                    )

        threading.Thread(
            target=work, name=f"lamina-run-{run_id[:8]}", daemon=True
        ).start()
        return dict(status)

    def start_method_run(self, method: dict, task: dict) -> dict:
        if self.provider is None:
            raise RuntimeError(
                "No adapter configured. Start Studio with --adapter to run a method."
            )
        selected = validate_method(method)
        selected_task = validate_method_task(task)
        for node in selected["nodes"]:
            missing = set(node["task_keys"] or []) - set(selected_task)
            if missing:
                raise ValueError(f"{node['id']} missing task fields: {sorted(missing)}")
        with self.run_lock:
            if any(
                run["status"] in {"queued", "running"} for run in self.runs.values()
            ):
                raise RuntimeError("A build is already running in this workspace")
            run_id = uuid.uuid4().hex
            status = {
                "id": run_id,
                "kind": "method",
                "status": "queued",
                "error": None,
                "outputs": {},
            }
            self.runs[run_id] = status

        def work():
            with self.run_lock:
                status["status"] = "running"
            try:
                receipt = run_method(
                    self.workspace, self.provider, selected, selected_task
                )
                if receipt["status"] == "failed":
                    for node_id, node in receipt["nodes"].items():
                        if node["status"] == "failed":
                            print(
                                f"Lamina method run {run_id} node {node_id} failed: {node.get('error')}",
                                flush=True,
                            )
                visible_receipt = public_method_receipt(receipt)
                output = self.output_root / run_id
                output.mkdir(parents=True, exist_ok=True)
                (output / "receipt.json").write_text(
                    json.dumps(visible_receipt, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                with self.run_lock:
                    if receipt["status"] == "completed":
                        status.update(
                            status="ready",
                            receipt=visible_receipt,
                            outputs={"receipt": f"/outputs/{run_id}/receipt.json"},
                        )
                    else:
                        # The workspace retains raw node errors locally. HTTP
                        # and downloadable receipts receive the redacted copy.
                        status.update(
                            status="failed",
                            receipt=visible_receipt,
                            outputs={"receipt": f"/outputs/{run_id}/receipt.json"},
                            error="Method run failed; see the local Studio console",
                        )
            except Exception as exc:
                print(f"Lamina method run {run_id} failed: {exc}", flush=True)
                with self.run_lock:
                    status.update(
                        status="failed",
                        error="Method run failed; see the local Studio console",
                    )

        threading.Thread(
            target=work, name=f"lamina-method-{run_id[:8]}", daemon=True
        ).start()
        return dict(status)

    def record_method_observation(self, body: dict) -> dict:
        if set(body) != {"run_id", "node_id", "note", "outcome", "applicability"}:
            raise ValueError(
                "observation needs exactly run_id, node_id, note, outcome, applicability"
            )
        run_id, node_id = body["run_id"], body["node_id"]
        if (
            not isinstance(run_id, str)
            or not RUN_ID.fullmatch(run_id)
            or not isinstance(node_id, str)
        ):
            raise ValueError("observation needs a valid run ID and node ID")
        for key in ("note", "outcome", "applicability"):
            value = body[key]
            if (
                not isinstance(value, str)
                or not value.strip()
                or len(value) > 4000
                or "\x00" in value
            ):
                raise ValueError(f"observation.{key} must be 1–4000 characters")
        with self.run_lock:
            run = self.runs.get(run_id)
            if run is None:
                raise LookupError("run not found")
            if run.get("kind") != "method" or run["status"] != "ready":
                raise RuntimeError("observation requires a completed method run")
            receipt = run["receipt"]
            if node_id not in receipt["nodes"] or receipt["nodes"][node_id][
                "status"
            ] not in {"executed", "cached"}:
                raise ValueError(
                    "node_id must name a completed node in this method run"
                )
            identity = dict(receipt["method"])
            task_digest = receipt["task_digest"]
        observation = record_observation(
            self.workspace,
            family=identity["family"],
            method_id=identity["id"],
            method_version=identity["version"],
            task_digest=task_digest,
            outcome=body["outcome"],
            applicability=body["applicability"],
            note=body["note"],
        )
        return {
            "observation_id": observation["observation_id"],
            "run_id": run_id,
            "node_id": node_id,
            "observation": observation,
        }


class StudioHandler(BaseHTTPRequestHandler):
    server: StudioServer

    def log_message(self, fmt: str, *args):
        # Avoid logging URL/query values or uploaded names in shared consoles.
        pass

    def _json(self, code: int, body: dict):
        encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _origin_ok(self) -> bool:
        port = self.server.server_port
        allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        host = self.headers.get("Host", "")
        if host not in allowed_hosts:
            return False
        origin = self.headers.get("Origin")
        return origin is None or origin in {f"http://{name}" for name in allowed_hosts}

    def _reject_origin(self) -> bool:
        if self._origin_ok():
            return False
        self._json(403, {"error": "Studio accepts only same-origin loopback requests"})
        return True

    def _body(self) -> dict:
        content_type = (
            self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        )
        if content_type != "application/json":
            raise ValueError("Content-Type must be application/json")
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError as exc:
            raise ValueError("Content-Length is required") from exc
        if length < 0 or length > MAX_BODY:
            raise OverflowError("JSON request exceeds the 8 MB limit")
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("request body must be valid JSON") from exc
        if not isinstance(body, dict):
            raise ValueError("request body must be a JSON object")
        return body

    def _path(self) -> str:
        parsed = urlsplit(self.path)
        if parsed.query or parsed.fragment:
            return ""
        return unquote(parsed.path)

    def do_GET(self):
        if self._reject_origin():
            return
        path = self._path()
        if path == "/api/status":
            sources = self.server.workspace.sources()
            units = self.server.workspace.units()
            counts = {s["id"]: 0 for s in sources}
            for unit in units:
                counts[unit["source_id"]] += 1
            with self.server.run_lock:
                active = next(
                    (
                        {k: r.get(k) for k in ("id", "kind", "status")}
                        for r in self.server.runs.values()
                        if r["status"] in {"queued", "running"}
                    ),
                    None,
                )
            self._json(
                200,
                {
                    "mode": "local",
                    "adapter_configured": self.server.provider is not None,
                    "audio_adapter_configured": self.server.audio_provider is not None,
                    "sources": [
                        {
                            "id": s["id"],
                            "title": s["title"],
                            "role": s["role"],
                            "units": counts[s["id"]],
                        }
                        for s in sources
                    ],
                    "jobs": self.server.workspace.stats()["jobs"],
                    "active_run": active,
                },
            )
            return
        if path == "/api/project-observations":
            from .method_runtime import list_experience

            self._json(
                200,
                {
                    "observations": list_experience(
                        self.server.workspace, "document-production", limit=100
                    )
                },
            )
            return
        if path == "/api/projects":
            with self.server.run_lock:
                items = [
                    {
                        k: r.get(k)
                        for k in ("id", "status", "created_at", "outputs", "parent_id")
                    }
                    for r in self.server.runs.values()
                    if r.get("kind") == "production"
                ]
            self._json(
                200,
                {
                    "projects": sorted(
                        items, key=lambda r: r.get("created_at", 0), reverse=True
                    )[:100]
                },
            )
            return
        if path == "/api/procedures":
            self._json(200, {"procedures": BUILTINS})
            return
        if path.startswith("/api/progress/") and RUN_ID.fullmatch(
            path.removeprefix("/api/progress/")
        ):
            run_id = path.removeprefix("/api/progress/")
            with self.server.run_lock:
                run = self.server.runs.get(run_id)
                result = (
                    {k: v for k, v in run.items() if k not in {"plan", "receipt"}}
                    if run
                    else None
                )
            self._json(200 if result else 404, result or {"error": "run not found"})
            return
        if path.startswith("/api/runs/") and RUN_ID.fullmatch(
            path.removeprefix("/api/runs/")
        ):
            run_id = path.removeprefix("/api/runs/")
            with self.server.run_lock:
                run = self.server.runs.get(run_id)
                result = dict(run) if run else None
            self._json(200 if result else 404, result or {"error": "run not found"})
            return
        if path.startswith("/api/"):
            self._json(404, {"error": "unknown API endpoint"})
            return
        self._file(path)

    def do_POST(self):
        if self._reject_origin():
            return
        path = self._path()
        project_action = re.fullmatch(
            r"/api/projects/([0-9a-f]{32})/(revise|resume|observation)", path
        )
        if not project_action and path not in {
            "/api/project-example",
            "/api/projects",
            "/api/sources",
            "/api/runs",
            "/api/methods/validate",
            "/api/method-runs",
            "/api/method-observations",
        }:
            self._json(404, {"error": "unknown API endpoint"})
            return
        try:
            body = self._body()
            if path == "/api/project-example":
                if body:
                    raise ValueError("The original example takes no custom input.")
                from .project_api import run_project_example

                run = run_project_example(self.server)
                self._json(
                    201,
                    {
                        "id": run["id"],
                        "status": run["status"],
                        "url": f"/api/runs/{run['id']}",
                    },
                )
            elif path == "/api/projects" or project_action:
                from .project_api import start_project

                if project_action:
                    with self.server.run_lock:
                        parent = copy.deepcopy(self.server.runs.get(project_action[1]))
                    if not parent or parent.get("kind") != "production":
                        raise LookupError("Project not found.")
                    if parent["status"] in {"running", "queued"}:
                        raise RuntimeError("Wait for this project to finish.")
                    if project_action[2] == "observation":
                        from .project_api import keep_project_observation

                        self._json(
                            201, keep_project_observation(self.server, parent, body)
                        )
                        return
                    if parent.get("example"):
                        raise ValueError(
                            "Run the original example again, or start your own project with a model adapter."
                        )
                    if project_action[2] == "revise":
                        if set(body) != {"section_notes"}:
                            raise ValueError("Describe changes by section ID.")
                        run = start_project(
                            self.server,
                            parent["request"],
                            parent=parent,
                            section_notes=body["section_notes"],
                        )
                    else:
                        if body:
                            raise ValueError("Resume does not accept new settings.")
                        run = start_project(
                            self.server, parent["request"], parent=parent
                        )
                else:
                    run = start_project(self.server, body)
                self._json(
                    202,
                    {
                        "id": run["id"],
                        "status": run["status"],
                        "url": f"/api/runs/{run['id']}",
                    },
                )
            elif path == "/api/sources":
                response = self._sources(body)
                self._json(201, response)
            elif path == "/api/methods/validate":
                if set(body) != {"method"}:
                    raise ValueError("validation request must contain only method")
                self._json(200, {"method": validate_method(body["method"])})
            elif path == "/api/method-runs":
                if set(body) != {"method", "task"}:
                    raise ValueError("method run request needs exactly method and task")
                run = self.server.start_method_run(body["method"], body["task"])
                self._json(
                    202,
                    {
                        "id": run["id"],
                        "status": run["status"],
                        "url": f"/api/runs/{run['id']}",
                    },
                )
            elif path == "/api/method-observations":
                self._json(201, self.server.record_method_observation(body))
            else:
                if set(body) != {"procedure"}:
                    raise ValueError("run request must contain only procedure")
                run = self.server.start_run(body["procedure"])
                self._json(
                    202,
                    {
                        "id": run["id"],
                        "status": run["status"],
                        "url": f"/api/runs/{run['id']}",
                    },
                )
        except OverflowError as exc:
            self._json(413, {"error": str(exc)})
        except RuntimeError as exc:
            self._json(409, {"error": str(exc)})
        except LookupError as exc:
            self._json(404, {"error": str(exc)})
        except ValueError as exc:
            self._json(400, {"error": str(exc)})

    def _sources(self, body: dict) -> dict:
        if (
            set(body) != {"files"}
            or not isinstance(body["files"], list)
            or not 1 <= len(body["files"]) <= MAX_FILES
        ):
            raise ValueError(f"files must be a list of 1–{MAX_FILES} documents")
        files = body["files"]
        names = set()
        for item in files:
            if not isinstance(item, dict) or not {"name", "role"}.issubset(item):
                raise ValueError("each file needs name and role")
            name, role = item["name"], item["role"]
            if (
                not isinstance(name, str)
                or not SAFE_NAME.fullmatch(name)
                or name in {".", ".."}
                or name.startswith(".")
            ):
                raise ValueError(
                    "file name must be a safe .md, .txt, .pdf, or .pptx basename"
                )
            if name.lower() in names:
                raise ValueError("file names must be unique within one upload")
            names.add(name.lower())
            if name.lower().endswith((".pdf", ".pptx")):
                if set(item) != {"name", "base64", "role"} or not isinstance(
                    item["base64"], str
                ):
                    raise ValueError("Binary files need exactly name, base64, and role")
                if len(item["base64"]) > MAX_PDF_BYTES * 4 // 3 + 8:
                    raise OverflowError("File exceeds the 5 MB decoded limit")
                try:
                    decoded = base64.b64decode(item["base64"], validate=True)
                except (ValueError, binascii.Error) as exc:
                    raise ValueError("File base64 is invalid") from exc
                signature = b"%PDF-" if name.lower().endswith(".pdf") else b"PK"
                if len(decoded) > MAX_PDF_BYTES or not decoded.startswith(signature):
                    raise ValueError("File header is invalid or exceeds 5 MB")
                item["_decoded"] = decoded
            else:
                if set(item) != {"name", "text", "role"}:
                    raise ValueError("text files need exactly name, text, and role")
                text = item["text"]
                if (
                    not isinstance(text, str)
                    or not text.strip()
                    or len(text) > MAX_FILE_CHARS
                    or "\x00" in text
                ):
                    raise ValueError(
                        f"file text must contain 1–{MAX_FILE_CHARS} characters"
                    )
            if role not in {"teaching", "assessment"}:
                raise ValueError("file role must be teaching or assessment")
        parsed = []
        with tempfile.TemporaryDirectory(prefix="lamina-upload-") as tmp:
            for item in files:
                path = Path(tmp) / item["name"]
                if "_decoded" in item:
                    path.write_bytes(item["_decoded"])
                else:
                    path.write_text(item["text"], encoding="utf-8")
                try:
                    parsed.append(read_source(path, item["role"]))
                except Exception as exc:
                    # PDF parsers may raise their own exception classes and
                    # include temporary paths in their messages.
                    if isinstance(exc, ValueError) and "PDF support requires" in str(
                        exc
                    ):
                        raise ValueError(
                            'PDF upload requires the optional pdf dependency: pip install "lamina-engine[pdf]"'
                        ) from exc
                    raise ValueError(
                        f"{item['name']} could not be read; check its format and text extraction"
                    ) from exc
        existing = {s["id"]: s for s in self.server.workspace.sources()}
        seen_roles = {}
        for source, _ in parsed:
            prior = existing.get(source["id"])
            if prior and prior["role"] != source["role"]:
                raise ValueError(
                    "identical content already exists with another source role"
                )
            if (
                source["id"] in seen_roles
                and seen_roles[source["id"]] != source["role"]
            ):
                raise ValueError(
                    "identical files in one upload cannot have different source roles"
                )
            seen_roles[source["id"]] = source["role"]
        for source, units in parsed:
            self.server.workspace.put_source(source)
            self.server.workspace.put_units(units)
        return {
            "sources": [
                {
                    "id": s["id"],
                    "title": s["title"],
                    "role": s["role"],
                    "units": len(units),
                }
                for s, units in parsed
            ],
            "count": len(parsed),
        }

    def _file(self, path: str):
        if (
            not path
            or "\\" in path
            or "\x00" in path
            or any(part in {".", ".."} for part in path.split("/"))
        ):
            self._json(404, {"error": "file not found"})
            return
        if path.startswith("/outputs/"):
            parts = path.split("/")
            if len(parts) < 3 or not RUN_ID.fullmatch(parts[2]):
                self._json(404, {"error": "file not found"})
                return
            with self.server.run_lock:
                run = self.server.runs.get(parts[2], {})
                ready = run.get("status") in {"ready", "review"}
                failed_method_receipt = (
                    run.get("kind") == "method"
                    and run.get("status") == "failed"
                    and len(parts) == 4
                    and parts[3] == "receipt.json"
                    and bool(run.get("receipt"))
                )
            if not (ready or failed_method_receipt):
                self._json(404, {"error": "file not found"})
                return
            root = (self.server.output_root / parts[2]).resolve()
            relative = "/".join(parts[3:]) or "index.html"
        else:
            root = self.server.asset_root
            relative = path.lstrip("/")
            if not relative or path.endswith("/"):
                relative += "index.html"
        target = (root / relative).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            self._json(404, {"error": "file not found"})
            return
        payload = target.read_bytes()
        content_type = (
            mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        )
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
