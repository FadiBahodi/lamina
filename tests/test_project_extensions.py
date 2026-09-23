"""Connected browser endpoints for examples, source policy and retained notes."""

from __future__ import annotations

import copy
import json
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from lamina.production_example import FixtureAdapter
from lamina.studio_server import StudioServer


def _static(path, with_pdf=False):
    path.mkdir(parents=True, exist_ok=True)
    (path / "index.html").write_text("studio", encoding="utf-8")
    return path


def _server(root, monkeypatch, provider=None):
    monkeypatch.setattr("lamina.studio_site.prepare_studio", _static)
    server = StudioServer(root, port=0)
    server.provider = provider
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _call(server, path, body=None, *, origin=None):
    headers = {"Content-Type": "application/json"}
    if origin is not None:
        headers["Origin"] = origin
    request = Request(
        f"http://127.0.0.1:{server.server_port}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        headers=headers,
    )
    try:
        with urlopen(request, timeout=15) as response:
            return response.status, response.read()
    except HTTPError as error:
        return error.code, error.read()


def _finished(server, rid):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        data = json.loads(_call(server, f"/api/runs/{rid}")[1])
        if data["status"] in {"ready", "review", "failed"}:
            return data
        time.sleep(0.04)
    raise AssertionError("Project did not finish")


def _stop(server, thread):
    server.shutdown()
    thread.join(timeout=2)
    server.server_close()


def test_no_adapter_original_example_runs_and_downloads(tmp_path, monkeypatch):
    server, thread = _server(tmp_path / "example", monkeypatch)
    try:
        code, raw = _call(server, "/api/project-example", {})
        assert code == 201, raw
        result = _finished(server, json.loads(raw)["id"])
        assert result["example"] is True
        assert result["status"] == "ready"
        assert result["adapter_label"] == "Deterministic original example"
        assert result["plan"]["options"]["source_policy"]
        assert result["receipt"]["initial_findings"]["section_2"]
        for key in ("document", "reader", "report", "plan"):
            code, content = _call(server, result["outputs"][key])
            assert code == 200 and content
        assert _call(server, "/api/project-example", {"adapter": "other"})[0] == 400
        assert (
            _call(server, "/api/project-example", {}, origin="http://evil.example")[0]
            == 403
        )
    finally:
        _stop(server, thread)


class RecordingFixture(FixtureAdapter):
    def __init__(self):
        super().__init__()
        self.envelopes = []

    def call(self, stage, request):
        with self.lock:
            self.envelopes.append((stage, copy.deepcopy(request)))
        return super().call(stage, request)


def test_http_policy_observation_planner_only_and_holdout_boundary(
    tmp_path, monkeypatch
):
    provider = RecordingFixture()
    server, thread = _server(tmp_path / "policy", monkeypatch, provider)
    try:
        facts = [
            (
                "current.md",
                "A lease expires after thirty seconds. Lease expiry does not prove that the former worker stopped.",
            ),
            (
                "fencing.md",
                "A fencing token lets storage reject writes from workers holding an older token.",
            ),
            (
                "retry.md",
                "A retry acquires a new token before it writes. The retry must not assume that the former worker has stopped.",
            ),
            (
                "logging.md",
                "Operations should log the token on each write attempt so a stale rejection can be traced.",
            ),
        ]
        files = [
            {"name": name, "role": "teaching", "text": "# Notes\n\n" + text}
            for name, text in facts
        ]
        files += [
            {
                "name": "form.md",
                "role": "teaching",
                "text": "# Prior question form\n\nFORM ONLY: Ask for the next safe action, then a reason.",
            },
            {
                "name": "holdout.md",
                "role": "assessment",
                "text": "# Secret key\n\nHIDDEN EVALUATION FACT.",
            },
        ]
        code, raw = _call(server, "/api/sources", {"files": files})
        assert code == 201, raw
        ids = [row["id"] for row in json.loads(raw)["sources"]]
        factual_ids, form_id, holdout_id = ids[:4], ids[4], ids[5]
        selected = factual_ids + [form_id]
        policy = {sid: "authority" for sid in factual_ids}
        policy[factual_ids[2]] = "historical"
        policy[form_id] = "form_exemplar"
        bad = {
            "brief": "Make a guide",
            "source_ids": selected + [holdout_id],
            "options": {
                "workflow": "planned",
                "source_policy": {**policy, holdout_id: "form_exemplar"},
            },
        }
        assert _call(server, "/api/projects", bad)[0] == 400
        assert not provider.envelopes
        body = {
            "brief": "Write an incident guide for lease workers",
            "source_ids": selected,
            "options": {
                "workflow": "planned",
                "format": "guide",
                "source_policy": policy,
            },
        }
        code, raw = _call(server, "/api/projects", body)
        assert code == 202, raw
        first = _finished(server, json.loads(raw)["id"])
        assert first["status"] == "ready", first.get("error")
        assert first["plan"]["form_exemplar_ids"] == [form_id]
        assert first["plan"]["factual_source_ids"] == factual_ids
        route_inputs = [
            request["input"]
            for stage, request in provider.envelopes
            if stage == "production_route"
        ]
        assert "FORM ONLY" in str(route_inputs[0]["form_exemplars"])
        reads = [
            request["input"]
            for stage, request in provider.envelopes
            if stage == "production_read"
        ]
        writers = [
            request["input"]
            for stage, request in provider.envelopes
            if stage == "production_write"
        ]
        assert len(reads) == 4
        assert "FORM ONLY" not in str(reads) + str(writers)
        assert "HIDDEN EVALUATION FACT" not in str(provider.envelopes)
        assert "FORM ONLY" not in first["receipt"]["markdown"]

        code, raw = _call(
            server,
            f"/api/projects/{first['id']}/observation",
            {
                "note": "Make the expiry/termination distinction visible.",
                "outcome": "useful after correction",
                "applicability": "lease-worker guide",
            },
        )
        assert code == 201, raw
        observation = json.loads(raw)
        oid = observation["observation_id"]
        code, raw = _call(server, "/api/project-observations")
        assert code == 200
        assert oid in {row["observation_id"] for row in json.loads(raw)["observations"]}
        before = len(provider.envelopes)
        selected_body = copy.deepcopy(body)
        selected_body["options"]["observation_ids"] = [oid]
        code, raw = _call(server, "/api/projects", selected_body)
        assert code == 202, raw
        second = _finished(server, json.loads(raw)["id"])
        assert second["status"] == "ready", second.get("error")
        new = provider.envelopes[before:]
        route = [
            request["input"] for stage, request in new if stage == "production_route"
        ]
        assert len(route) == 1
        assert route[0]["experience"][0]["observation"]["observation_id"] == oid
        assert not [stage for stage, _ in new if stage == "production_read"]
        assert all(
            "experience" not in request["input"]
            for stage, request in new
            if stage in {"production_write", "production_review"}
        )
    finally:
        _stop(server, thread)
