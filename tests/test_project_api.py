"""Connected local HTTP journeys for goal-to-artifact production."""

from __future__ import annotations

import json
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

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


def _stop(server, thread):
    server.shutdown()
    thread.join(timeout=2)
    server.server_close()


def _call(server, path, body=None, headers=None):
    url = f"http://127.0.0.1:{server.server_port}{path}"
    payload = json.dumps(body).encode() if body is not None else None
    request = Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        with urlopen(request, timeout=10) as response:
            return response.status, response.read()
    except HTTPError as error:
        return error.code, error.read()


def _finished(server, rid):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        status = json.loads(_call(server, f"/api/runs/{rid}")[1])
        if status["status"] in {"ready", "review", "failed", "interrupted"}:
            return status
        time.sleep(0.05)
    raise AssertionError(f"Production run did not finish: {status.get('status')}, {status.get('events', [])[-3:]}")


def _upload_four(server):
    files = [
        {
            "name": "01-expiry.md",
            "role": "teaching",
            "text": "# Expiry\n\nA lease expires after thirty seconds. Lease expiry does not prove that the former worker stopped.",
        },
        {
            "name": "02-fencing.md",
            "role": "teaching",
            "text": "# Fencing\n\nA fencing token lets storage reject writes from workers holding an older token.",
        },
        {
            "name": "03-retry.md",
            "role": "teaching",
            "text": "# Retry\n\nA retry acquires a new token before it writes. The retry must not assume that the former worker has stopped.",
        },
        {
            "name": "04-logging.md",
            "role": "teaching",
            "text": "# Logging\n\nOperations should log the token on each write attempt so a stale rejection can be traced.",
        },
    ]
    code, raw = _call(server, "/api/sources", {"files": files})
    assert code == 201, raw
    return [row["id"] for row in json.loads(raw)["sources"]]


def _start(server, source_ids, fmt="guide"):
    body = {
        "brief": "Write an incident guide for lease-based workers.",
        "source_ids": source_ids,
        "options": {
            "format": fmt,
            "reader_workers": 8,
            "writer_workers": 8,
            "review_workers": 8,
        },
    }
    code, raw = _call(server, "/api/projects", body)
    assert code == 202, raw
    return _finished(server, json.loads(raw)["id"])


def test_project_http_upload_build_artifact_revise_and_restart(tmp_path, monkeypatch):
    root = tmp_path / "studio"
    provider = FixtureAdapter()
    server, thread = _server(root, monkeypatch, provider)
    try:
        ids = _upload_four(server)
        initial = _start(server, ids)
        assert initial["status"] == "ready", initial.get("error")
        assert initial["kind"] == "production"
        assert initial["plan"]["route"]["sections"][1]["id"] == "section_2"
        assert initial["receipt"]["initial_findings"]["section_2"]
        assert initial["receipt"]["findings"] == {}
        assert initial["events"] and all(
            "stage" in e and "status" in e for e in initial["events"]
        )
        assert initial["receipt"]["metrics"]["sections"] == 3
        for key in ("document", "reader", "report", "plan"):
            code, content = _call(server, initial["outputs"][key])
            assert code == 200 and content
        first_markdown = _call(server, initial["outputs"]["document"])[1].decode()
        assert "Lease-worker incident guide" in first_markdown
        assert "can assume that the former worker has stopped" not in first_markdown

        code, raw = _call(
            server,
            f"/api/projects/{initial['id']}/revise",
            {"section_notes": {"section_3": "Add the incident ticket ID."}},
        )
        assert code == 202, raw
        revised = _finished(server, json.loads(raw)["id"])
        assert revised["status"] == "ready"
        assert revised["parent_id"] == initial["id"]
        assert revised["receipt"]["sections"][:2] == initial["receipt"]["sections"][:2]
        assert revised["receipt"]["sections"][2] != initial["receipt"]["sections"][2]
        assert revised["receipt"]["metrics"]["cache_hits"] >= 4
        assert (
            "incident ticket ID"
            in _call(server, revised["outputs"]["document"])[1].decode()
        )
        assert (
            _call(
                server,
                f"/api/projects/{initial['id']}/revise",
                {"section_notes": {"missing": "bad"}},
            )[0]
            == 400
        )
        code, raw = _call(
            server,
            f"/api/projects/{revised['id']}/revise",
            {"section_notes": {"section_1": "Show the handoff timer explicitly."}},
        )
        assert code == 202, raw
        cumulative = _finished(server, json.loads(raw)["id"])
        assert cumulative["status"] == "ready"
        assert cumulative["request"]["options"]["section_notes"] == {
            "section_3": "Add the incident ticket ID.",
            "section_1": "Show the handoff timer explicitly.",
        }
        assert cumulative["receipt"]["sections"][2] == revised["receipt"]["sections"][2]
        assert cumulative["receipt"]["sections"][0] != revised["receipt"]["sections"][0]
        assert cumulative["receipt"]["sections"][1] == revised["receipt"]["sections"][1]
        assert (
            _call(
                server,
                "/api/projects",
                {"brief": "x", "source_ids": ids, "adapter": "bad"},
            )[0]
            == 400
        )
        assert (
            _call(
                server,
                "/api/projects",
                {"brief": "x", "source_ids": ids},
                headers={"Origin": "http://evil.example"},
            )[0]
            == 403
        )
    finally:
        _stop(server, thread)

    reopened, reopened_thread = _server(root, monkeypatch, FixtureAdapter())
    try:
        ids_seen = {
            item["id"]
            for item in json.loads(_call(reopened, "/api/projects")[1])["projects"]
        }
        assert initial["id"] in ids_seen and revised["id"] in ids_seen
        assert (
            _finished(reopened, revised["id"])["receipt"]["markdown"]
            == revised["receipt"]["markdown"]
        )
        code, raw = _call(reopened, f"/api/projects/{initial['id']}/resume", {})
        assert code == 202, raw
        resumed = _finished(reopened, json.loads(raw)["id"])
        assert resumed["status"] == "ready"
        assert resumed["receipt"]["metrics"]["cache_misses"] == 0
    finally:
        _stop(reopened, reopened_thread)


def test_assessment_candidate_download_separate_from_examiner(tmp_path, monkeypatch):
    class AssessmentFixture(FixtureAdapter):
        def call(self, stage, request):
            if stage == "assessment_blind_solve":
                assert set(request["input"]) == {"current_candidate_body", "prior_candidate_bodies"}
                return {"answer": "Check the current fencing token.", "uncertainties": []}
            if stage == "assessment_judge":
                return {"findings": []}
            if (
                stage == "production_review"
                and request["input"]["format"] == "assessment"
            ):
                data = request["input"]
                if (
                    data["section"]["id"] == "section_2"
                    and "can assume that the former worker has stopped"
                    in data["draft"]["marking_body"]
                ):
                    return {
                        "findings": [
                            {
                                "issue": "Expiry does not stop the old worker.",
                                "repair_instruction": "Restore the lease expiry distinction.",
                                "evidence": [data["assigned_ideas"][0]["evidence"][0]],
                            }
                        ]
                    }
                return {"findings": []}
            result = super().call(stage, request)
            if (
                stage in {"production_write", "production_repair"}
                and request["input"]["format"] == "assessment"
            ):
                result["candidate_body"] = "Explain the safety boundary."
                result["marking_body"] = result.pop("body")
            return result

    server, thread = _server(tmp_path / "assessment", monkeypatch, AssessmentFixture())
    try:
        ids = _upload_four(server)
        status = _start(server, ids, "assessment")
        assert status["status"] == "ready", status.get("error")
        candidate = _call(server, status["outputs"]["candidate"])[1].decode()
        examiner = _call(server, status["outputs"]["examiner"])[1].decode()
        default = _call(server, status["outputs"]["document"])[1].decode()
        assert "Explain the safety boundary" in candidate
        assert "A lease expires" not in candidate and "A lease expires" not in default
        assert "A lease expires" in examiner
        assert status["receipt"]["candidate_markdown"] == status["receipt"]["markdown"]
        assert (
            status["receipt"]["examiner_markdown"]
            != status["receipt"]["candidate_markdown"]
        )
    finally:
        _stop(server, thread)
