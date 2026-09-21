"""Loopback-only Studio API and static output host.

The adapter is selected at server startup, never by an HTTP request. Uploaded
text is reference material, not an executable instruction or filesystem path.
"""
from __future__ import annotations

import base64
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
from .pipeline import build
from .procedures import BUILTINS, validate_procedure
from .providers import CommandProvider
from .store import Workspace
from .validation import validate_bundle

MAX_BODY = 8_000_000
MAX_FILES = 12
MAX_FILE_CHARS = 500_000
MAX_PDF_BYTES = 5_000_000
SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._ -]{0,119}\.(?:md|txt|pdf)\Z", re.I)
RUN_ID = re.compile(r"[0-9a-f]{32}\Z")


def make_provider(adapter: str | None, *, version: str | None = None, timeout: float = 120):
    if not adapter:
        return None
    command = shlex.split(adapter)
    if not command:
        raise ValueError("adapter command cannot be empty")
    return CommandProvider(command, timeout=timeout, version=version)


def run_procedure(workspace: Workspace, provider, procedure: dict, output: Path) -> dict:
    """Generate selected artifacts through the same validated path as the CLI."""
    selected = validate_procedure(procedure)
    if provider is None:
        raise ValueError("A local adapter must be configured before running a procedure")
    bundle = build(workspace, provider, workers=selected["workers"], procedure=selected)
    validate_bundle(bundle)
    if "oral-case" in selected["outputs"] and not any(lesson.get("scenario") for lesson in bundle["lessons"]):
        raise ValueError("oral-case procedure produced no reviewed scenario")
    output.mkdir(parents=True, exist_ok=True)
    (output / "procedure.json").write_text(json.dumps(selected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
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
        scripts = [{"lesson_id": lesson["id"], "title": lesson["title"], "script": lesson["audio_script"]}
                   for lesson in bundle["lessons"]]
        (output / "audio-script.json").write_text(json.dumps(scripts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        links["audio_script"] = "audio-script.json"
    # Oral-case practice is already a required, reviewed field in every lesson.
    if "oral-case" in selected["outputs"]:
        links["oral_case"] = ""
    return {"title": bundle["title"], "lessons": len(bundle["lessons"]), "links": links}


class StudioServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, workspace: Path, *, port: int = 8048, adapter: str | None = None,
                 adapter_version: str | None = None, timeout: float = 120):
        self.workspace = Workspace(workspace)
        self.provider = make_provider(adapter, version=adapter_version, timeout=timeout)
        self.output_root = self.workspace.root / "outputs"
        self.output_root.mkdir(parents=True, exist_ok=True)
        from .studio_site import prepare_studio
        self.asset_root = prepare_studio(self.workspace.root / "studio-static").resolve()
        self.runs: dict[str, dict] = {}
        self.run_lock = threading.Lock()
        super().__init__(("127.0.0.1", port), StudioHandler)

    def start_run(self, procedure: dict) -> dict:
        if self.provider is None:
            raise RuntimeError("No adapter configured. Start Studio with --adapter to generate from your sources.")
        selected = validate_procedure(procedure)
        with self.run_lock:
            if any(run["status"] in {"queued", "running"} for run in self.runs.values()):
                raise RuntimeError("A build is already running in this workspace")
            run_id = uuid.uuid4().hex
            status = {"id": run_id, "status": "queued", "error": None, "outputs": {}}
            self.runs[run_id] = status

        def work():
            with self.run_lock:
                status["status"] = "running"
            try:
                result = run_procedure(self.workspace, self.provider, selected, self.output_root / run_id)
                links = {key: f"/outputs/{run_id}/{value}" for key, value in result["links"].items()}
                with self.run_lock:
                    status.update(status="ready", outputs=links, title=result["title"], lessons=result["lessons"])
            except Exception as exc:
                # Exceptions can contain local paths, command arguments, or
                # adapter stderr. Keep them on the local console, not in JSON.
                print(f"Lamina run {run_id} failed: {exc}", flush=True)
                with self.run_lock:
                    status.update(status="failed", error=f"{type(exc).__name__}: build failed; see the local Studio console")

        threading.Thread(target=work, name=f"lamina-run-{run_id[:8]}", daemon=True).start()
        return dict(status)


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
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
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
                active = next((dict(r) for r in self.server.runs.values() if r["status"] in {"queued", "running"}), None)
            self._json(200, {"mode": "local", "adapter_configured": self.server.provider is not None,
                             "sources": [{"id": s["id"], "title": s["title"], "role": s["role"], "units": counts[s["id"]]} for s in sources],
                             "jobs": self.server.workspace.stats()["jobs"], "active_run": active})
            return
        if path == "/api/procedures":
            self._json(200, {"procedures": BUILTINS})
            return
        if path.startswith("/api/runs/") and RUN_ID.fullmatch(path.removeprefix("/api/runs/")):
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
        if path not in {"/api/sources", "/api/runs"}:
            self._json(404, {"error": "unknown API endpoint"})
            return
        try:
            body = self._body()
            if path == "/api/sources":
                response = self._sources(body)
                self._json(201, response)
            else:
                if set(body) != {"procedure"}:
                    raise ValueError("run request must contain only procedure")
                run = self.server.start_run(body["procedure"])
                self._json(202, {"id": run["id"], "status": run["status"], "url": f"/api/runs/{run['id']}"})
        except OverflowError as exc:
            self._json(413, {"error": str(exc)})
        except RuntimeError as exc:
            self._json(409, {"error": str(exc)})
        except ValueError as exc:
            self._json(400, {"error": str(exc)})

    def _sources(self, body: dict) -> dict:
        if set(body) != {"files"} or not isinstance(body["files"], list) or not 1 <= len(body["files"]) <= MAX_FILES:
            raise ValueError(f"files must be a list of 1–{MAX_FILES} documents")
        files = body["files"]
        names = set()
        for item in files:
            if not isinstance(item, dict) or not {"name", "role"}.issubset(item):
                raise ValueError("each file needs name and role")
            name, role = item["name"], item["role"]
            if not isinstance(name, str) or not SAFE_NAME.fullmatch(name) or name in {".", ".."} or name.startswith("."):
                raise ValueError("file name must be a safe .md, .txt, or .pdf basename")
            if name.lower() in names:
                raise ValueError("file names must be unique within one upload")
            names.add(name.lower())
            if name.lower().endswith(".pdf"):
                if set(item) != {"name", "base64", "role"} or not isinstance(item["base64"], str):
                    raise ValueError("PDF files need exactly name, base64, and role")
                if len(item["base64"]) > MAX_PDF_BYTES * 4 // 3 + 8:
                    raise OverflowError("PDF exceeds the 5 MB decoded limit")
                try:
                    decoded = base64.b64decode(item["base64"], validate=True)
                except (ValueError, binascii.Error) as exc:
                    raise ValueError("PDF base64 is invalid") from exc
                if len(decoded) > MAX_PDF_BYTES or not decoded.startswith(b"%PDF-"):
                    raise ValueError("PDF must be a valid PDF header and at most 5 MB")
                item["_decoded"] = decoded
            else:
                if set(item) != {"name", "text", "role"}:
                    raise ValueError("text files need exactly name, text, and role")
                text = item["text"]
                if not isinstance(text, str) or not text.strip() or len(text) > MAX_FILE_CHARS or "\x00" in text:
                    raise ValueError(f"file text must contain 1–{MAX_FILE_CHARS} characters")
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
                    if isinstance(exc, ValueError) and "PDF support requires" in str(exc):
                        raise ValueError('PDF upload requires the optional pdf dependency: pip install "lamina-engine[pdf]"') from exc
                    raise ValueError(f"{item['name']} could not be read; check its format and text extraction") from exc
        existing = {s["id"]: s for s in self.server.workspace.sources()}
        seen_roles = {}
        for source, _ in parsed:
            prior = existing.get(source["id"])
            if prior and prior["role"] != source["role"]:
                raise ValueError("identical content already exists with another source role")
            if source["id"] in seen_roles and seen_roles[source["id"]] != source["role"]:
                raise ValueError("identical files in one upload cannot have different source roles")
            seen_roles[source["id"]] = source["role"]
        for source, units in parsed:
            self.server.workspace.put_source(source)
            self.server.workspace.put_units(units)
        return {"sources": [{"id": s["id"], "title": s["title"], "role": s["role"], "units": len(units)}
                            for s, units in parsed], "count": len(parsed)}

    def _file(self, path: str):
        if not path or "\\" in path or "\x00" in path or any(part in {".", ".."} for part in path.split("/")):
            self._json(404, {"error": "file not found"})
            return
        if path.startswith("/outputs/"):
            parts = path.split("/")
            if len(parts) < 3 or not RUN_ID.fullmatch(parts[2]):
                self._json(404, {"error": "file not found"})
                return
            with self.server.run_lock:
                ready = self.server.runs.get(parts[2], {}).get("status") == "ready"
            if not ready:
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
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
