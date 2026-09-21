import base64
import copy
import io
import json
import threading
import time
from pathlib import Path
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


def method_definition():
    return json.loads((Path(__file__).parents[1] / "examples/methods/field-guide.json").read_text())


class MethodFixtureProvider:
    identity = "studio-method-fixture-v1"

    def __init__(self):
        self.calls = []

    def call(self, stage, payload):
        assert stage == payload["stage"] == "method_node"
        self.calls.append(copy.deepcopy(payload))
        data = payload["input"]
        node = data["node"]["id"]
        if node == "site-read":
            return {"finding": "site: " + data["task"]["site_notes"]}
        if node == "plant-read":
            return {"finding": "plants: " + data["task"]["plant_notes"]}
        return {"guide": " | ".join([data["dependencies"]["site-read"]["finding"],
                                      data["dependencies"]["plant-read"]["finding"],
                                      *[item["observation"]["note"] for item in data["experience"]]])}


def finished_run(server, run_id):
    for _ in range(100):
        status = json.loads(call(server, f"/api/runs/{run_id}")[2])
        if status["status"] in {"ready", "failed"}:
            return status
        time.sleep(0.01)
    raise AssertionError("background method did not finish")


def start_method(server, method, task):
    code, _, raw = call(server, "/api/method-runs", body={"method": method, "task": task})
    assert code == 202, raw
    return finished_run(server, json.loads(raw)["id"])


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
    code, _, raw = call(studio, "/api/method-runs", body={"method": method_definition(), "task": {}})
    assert code == 409 and "adapter" in json.loads(raw)["error"].lower()


def test_method_http_validate_import_run_cache_change_and_observation(studio):
    method = method_definition()
    code, _, raw = call(studio, "/api/methods/validate", body={"method": method})
    assert code == 200
    canonical = json.loads(raw)["method"]
    assert canonical["nodes"][0]["observation_ids"] == []
    assert canonical["nodes"][0]["task_keys"] == ["site_notes"]
    studio.provider = MethodFixtureProvider()
    code, _, raw = call(studio, "/api/sources", body={"files": [
        {"name": "garden.md", "role": "teaching", "text": "# Site\n\nMorning shade, one tap."}]})
    assert code == 201
    task = {"site_notes": "Morning shade, one tap.", "plant_notes": "Mint", "audience": "Volunteers"}
    first = start_method(studio, method, task)
    assert first["kind"] == "method" and first["status"] == "ready"
    assert [first["receipt"]["nodes"][node]["status"] for node in ("site-read", "plant-read", "guide")] == ["executed"] * 3
    assert len(studio.provider.calls) == 3
    output = first["outputs"]["receipt"]
    code, headers, raw = call(studio, output)
    assert code == 200 and "application/json" in headers["Content-Type"]
    assert json.loads(raw)["run_id"] == first["receipt"]["run_id"]
    second = start_method(studio, method, task)
    assert [second["receipt"]["nodes"][node]["status"] for node in ("site-read", "plant-read", "guide")] == ["cached"] * 3
    assert len(studio.provider.calls) == 3
    code, _, _ = call(studio, "/api/sources", body={"files": [
        {"name": "garden-revised.md", "role": "teaching", "text": "# Site\n\nAfternoon shade, one tap."}]})
    assert code == 201
    changed = {**task, "site_notes": "Afternoon shade, one tap."}
    third = start_method(studio, method, changed)
    assert [third["receipt"]["nodes"][node]["status"] for node in ("site-read", "plant-read", "guide")] == ["executed", "cached", "executed"]
    assert len(studio.provider.calls) == 5
    assert "Afternoon shade" in third["receipt"]["results"]["guide"]["guide"]
    observation_body = {"run_id": third["id"], "node_id": "guide", "note": "Mention the western entrance.",
                        "outcome": "needs clarification", "applicability": "afternoon site note"}
    code, _, raw = call(studio, "/api/method-observations", body=observation_body)
    assert code == 201
    recorded = json.loads(raw)
    assert recorded["observation"]["family"] == "field-guides"
    assert recorded["observation"]["task_digest"] == third["receipt"]["task_digest"]
    guided = copy.deepcopy(method)
    guided["version"] = "1.1"
    guided["nodes"][2]["observation_ids"] = [recorded["observation_id"]]
    fourth = start_method(studio, guided, changed)
    assert [fourth["receipt"]["nodes"][node]["status"] for node in ("site-read", "plant-read", "guide")] == ["cached", "cached", "executed"]
    assert "western entrance" in fourth["receipt"]["results"]["guide"]["guide"]
    assert studio.provider.calls[-1]["input"]["experience"][0]["observation"]["observation_id"] == recorded["observation_id"]


def test_method_http_rejects_malformed_foreign_origin_and_unfinished_observation(studio):
    method = method_definition()
    assert call(studio, "/api/methods/validate", body={"method": method, "adapter": "arbitrary"})[0] == 400
    malformed = copy.deepcopy(method)
    malformed["nodes"][0]["depends_on"] = ["missing"]
    assert call(studio, "/api/methods/validate", body={"method": malformed})[0] == 400
    studio.provider = MethodFixtureProvider()
    assert call(studio, "/api/method-runs", body={"method": method, "task": {}, "path": "../private"})[0] == 400
    assert call(studio, "/api/method-runs", body={"method": method, "task": []})[0] == 400
    assert call(studio, "/api/method-runs", body={"method": method, "task": {"irrelevant": "x"}})[0] == 400
    assert call(studio, "/api/method-runs", body={"method": method, "task": {}},
                headers={"Origin": "http://evil.example"})[0] == 403
    assert call(studio, "/api/methods/validate", body={"method": method},
                headers={"Host": "evil.example"})[0] == 403
    assert call(studio, "/api/method-observations", body={"run_id": "f" * 32, "node_id": "guide",
                "note": "n", "outcome": "o", "applicability": "a"})[0] == 404
    task = {"site_notes": "shade", "plant_notes": "mint", "audience": "volunteers"}
    finished = start_method(studio, method, task)
    assert call(studio, "/api/method-observations", body={"run_id": finished["id"], "node_id": "unknown",
                "note": "n", "outcome": "o", "applicability": "a"})[0] == 400
    assert call(studio, "/api/method-observations", body={"run_id": finished["id"], "node_id": "guide",
                "note": "n", "outcome": "o", "applicability": "a", "adapter": "ignored"})[0] == 400
    assert call(studio, "/api/method-observations", body={"run_id": finished["id"], "node_id": "guide",
                "note": "n", "outcome": "o", "applicability": "a"},
                headers={"Origin": "http://evil.example"})[0] == 403


def test_method_and_guide_share_one_active_run_limit(studio):
    entered, release = threading.Event(), threading.Event()

    class WaitingProvider(MethodFixtureProvider):
        def call(self, stage, payload):
            entered.set()
            assert release.wait(timeout=2)
            return super().call(stage, payload)

    studio.provider = WaitingProvider()
    method = method_definition()
    task = {"site_notes": "shade", "plant_notes": "mint", "audience": "volunteers"}
    code, _, raw = call(studio, "/api/method-runs", body={"method": method, "task": task})
    assert code == 202
    run_id = json.loads(raw)["id"]
    try:
        assert entered.wait(timeout=1)
        assert call(studio, "/api/method-runs", body={"method": method, "task": task})[0] == 409
        assert call(studio, "/api/runs", body={"procedure": BUILTINS[0]})[0] == 409
    finally:
        release.set()
    assert finished_run(studio, run_id)["status"] == "ready"


def test_failed_method_receipt_is_inspectable_without_adapter_error_leak(studio, capsys):
    class FailingProvider:
        identity = "failing-fixture"

        def call(self, stage, payload):
            raise RuntimeError("secret-token and /Users/private/source.txt in adapter stderr")

    studio.provider = FailingProvider()
    method = method_definition()
    task = {"site_notes": "shade", "plant_notes": "mint", "audience": "volunteers"}
    failed = start_method(studio, method, task)
    assert failed["status"] == "failed"
    assert failed["receipt"]["status"] == "failed"
    assert failed["receipt"]["nodes"]["guide"]["status"] == "skipped"
    visible = json.dumps(failed)
    assert "secret-token" not in visible and "/Users/private" not in visible
    assert all(node["error"] == "Node failed; see the local Studio console"
               for node in failed["receipt"]["nodes"].values() if node["status"] == "failed")
    code, _, raw = call(studio, failed["outputs"]["receipt"])
    assert code == 200
    assert b"secret-token" not in raw and b"/Users/private" not in raw
    assert json.loads(raw)["status"] == "failed"
    assert "secret-token" in capsys.readouterr().out


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
