import base64
import io
import json
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from lamina.procedures import BUILTINS
from lamina.studio_server import StudioServer, run_procedure


@pytest.fixture
def studio(tmp_path, monkeypatch):
    def simple_static(path, with_pdf=False):
        path.mkdir(parents=True, exist_ok=True)
        (path / "index.html").write_text("studio example", encoding="utf-8")
        (path / "workbench").mkdir()
        (path / "workbench/index.html").write_text("example workbench", encoding="utf-8")
        return path
    monkeypatch.setattr("lamina.studio_site.prepare_studio", simple_static)
    server = StudioServer(tmp_path / "workspace", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    thread.join(timeout=2)
    server.server_close()


def call(server, path, *, body=None, headers=None):
    url = f"http://127.0.0.1:{server.server_port}{path}"
    payload = json.dumps(body).encode() if body is not None else None
    request = Request(url, data=payload, headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urlopen(request, timeout=2) as result:
            return result.status, result.headers, result.read()
    except HTTPError as error:
        return error.code, error.headers, error.read()


def test_studio_status_upload_and_no_adapter(studio):
    code, _, raw = call(studio, "/api/status")
    assert code == 200
    assert json.loads(raw)["adapter_configured"] is False
    assert json.loads(call(studio, "/api/procedures")[2])["procedures"] == BUILTINS
    code, _, raw = call(studio, "/api/sources", body={"files": [
        {"name": "a.md", "text": "# A\n\n## One\n\nEvidence lives here.", "role": "teaching"},
        {"name": "holdout.txt", "text": "Question material", "role": "assessment"},
    ]})
    assert code == 201
    assert json.loads(raw)["count"] == 2
    status = json.loads(call(studio, "/api/status")[2])
    assert {s["role"] for s in status["sources"]} == {"teaching", "assessment"}
    assert all("text" not in s for s in status["sources"])
    code, _, raw = call(studio, "/api/runs", body={"procedure": BUILTINS[0]})
    assert code == 409 and "adapter" in json.loads(raw)["error"].lower()


def test_studio_rejects_origin_paths_and_non_json(studio):
    code, _, _ = call(studio, "/api/status", headers={"Host": "evil.example"})
    assert code == 403
    code, _, _ = call(studio, "/api/sources", body={"files": []}, headers={"Origin": "http://evil.example"})
    assert code == 403
    code, _, _ = call(studio, "/api/sources", body={"files": [{"name": "../private.md", "text": "x", "role": "teaching"}]})
    assert code == 400
    code, _, _ = call(studio, "/api/sources", body={"files": [{"name": "bad.pdf", "base64": "not base64!", "role": "teaching"}]})
    assert code == 400
    code, _, _ = call(studio, "/api/sources", body={"files": [
        {"name": "same-a.md", "text": "# Same\n\nIdentical body", "role": "teaching"},
        {"name": "same-b.md", "text": "# Same\n\nIdentical body", "role": "assessment"},
    ]})
    assert code == 400
    assert json.loads(call(studio, "/api/status")[2])["sources"] == []
    code, _, _ = call(studio, "/../workspace/workspace.sqlite3")
    assert code == 404
    code, headers, raw = call(studio, "/")
    assert code == 200 and raw == b"studio example" and "Access-Control-Allow-Origin" not in headers
    assert call(studio, "/workbench/")[2] == b"example workbench"


def test_pdf_upload_reuses_extractable_pdf_ingest(studio):
    pytest.importorskip("pypdf")
    canvas_module = pytest.importorskip("reportlab.pdfgen.canvas")
    stream = io.BytesIO()
    canvas = canvas_module.Canvas(stream)
    canvas.drawString(80, 700, "A lease has an expiry and a single owner.")
    canvas.save()
    code, _, raw = call(studio, "/api/sources", body={"files": [{
        "name": "leases.pdf", "base64": base64.b64encode(stream.getvalue()).decode(), "role": "teaching"
    }]})
    assert code == 201, raw
    assert json.loads(raw)["sources"][0]["units"] >= 1


def test_pdf_missing_extra_reports_install_command(studio, monkeypatch):
    def missing_pdf(path, role):
        raise ValueError('PDF support requires: pip install "lamina-engine[pdf]"')
    monkeypatch.setattr("lamina.studio_server.read_source", missing_pdf)
    code, _, raw = call(studio, "/api/sources", body={"files": [{
        "name": "needs-extra.pdf", "base64": base64.b64encode(b"%PDF-dummy").decode(), "role": "teaching"
    }]})
    assert code == 400
    assert "lamina-engine[pdf]" in json.loads(raw)["error"]


def test_studio_background_run_and_output_gate(studio, monkeypatch):
    def fake_run(workspace, provider, procedure, output):
        time.sleep(0.05)
        output.mkdir(parents=True)
        (output / "index.html").write_text("finished", encoding="utf-8")
        (output / "bundle.json").write_text("{}", encoding="utf-8")
        return {"title": "Finished", "lessons": 1, "links": {"site": "", "bundle": "bundle.json"}}
    monkeypatch.setattr("lamina.studio_server.run_procedure", fake_run)
    studio.provider = object()
    code, _, raw = call(studio, "/api/runs", body={"procedure": BUILTINS[0]})
    assert code == 202
    run_id = json.loads(raw)["id"]
    for _ in range(40):
        response = json.loads(call(studio, f"/api/runs/{run_id}")[2])
        if response["status"] == "ready":
            break
        time.sleep(0.02)
    assert response["status"] == "ready"
    assert response["outputs"]["site"] == f"/outputs/{run_id}/"
    assert call(studio, response["outputs"]["site"])[2] == b"finished"
    assert call(studio, f"/outputs/{run_id}/../workspace.sqlite3")[0] == 404


def test_real_procedure_threads_brief_through_semantic_stages(tmp_path):
    from pathlib import Path
    from lamina.ingest import ingest_paths
    from lamina.providers import DemoProvider
    from lamina.store import Workspace

    workspace = Workspace(tmp_path / "workspace")
    ingest_paths([Path(__file__).parents[1] / "src/lamina/demo/sources"], workspace)

    class ObservedProvider:
        def __init__(self):
            self.delegate = DemoProvider()
            self.identity = self.delegate.identity + ":observed"
            self.calls = []

        def call(self, stage, payload):
            self.calls.append((stage, payload))
            return self.delegate.call(stage, payload)

    provider = ObservedProvider()
    procedure = dict(BUILTINS[0])
    procedure["instructions"] += " Pause before showing each answer."
    output = tmp_path / "output"
    result = run_procedure(workspace, provider, procedure, output)
    assert result["lessons"] == 3
    assert (output / "bundle.json").is_file()
    assert (output / "procedure.json").is_file()
    assert {stage for stage, _ in provider.calls} == {"extract", "reconcile", "plan", "author", "review"}
    assert all(request["input"]["procedure"]["id"] == procedure["id"] for _, request in provider.calls)
    assert all(procedure["instructions"] in request["instruction"]
               for stage, request in provider.calls if stage in {"plan", "author"})
