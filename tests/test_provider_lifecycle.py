"""Resource owners close adapters after work, including error paths."""

import threading

import pytest

from lamina.cli import main, parser
from lamina.studio_server import StudioServer


class ClosingProvider:
    def __init__(self):
        self.closed = threading.Event()
        self.calls = 0

    def close(self):
        self.calls += 1
        self.closed.set()


def static_assets(path):
    path.mkdir(parents=True, exist_ok=True)
    (path / "index.html").write_text("fixture")
    return path


def test_server_waits_for_owned_jobs_and_closes_only_owned_adapters(
    tmp_path, monkeypatch
):
    owned, borrowed = ClosingProvider(), ClosingProvider()
    monkeypatch.setattr("lamina.studio_site.prepare_studio", static_assets)
    monkeypatch.setattr(
        "lamina.studio_server.make_provider",
        lambda adapter, **_: owned if adapter else None,
    )
    server = StudioServer(tmp_path, port=0, adapter="fixture")
    server.provider = borrowed
    entered, release = threading.Event(), threading.Event()

    def work():
        entered.set()
        assert release.wait(timeout=5)

    server.start_job(work, "owned-test-job")
    assert entered.wait(timeout=2)
    closing = threading.Thread(target=server.server_close)
    closing.start()
    try:
        with server._job_condition:
            assert server._job_condition.wait_for(lambda: server._closing, timeout=2)
        assert closing.is_alive()
        assert not owned.closed.is_set()
        with pytest.raises(RuntimeError, match="shutting down"):
            server.start_job(lambda: None, "rejected")
    finally:
        release.set()
        closing.join(timeout=3)
    assert not closing.is_alive()
    assert owned.calls == 1
    assert borrowed.calls == 0
    server.server_close()
    assert owned.calls == 1


def test_failed_server_startup_releases_created_adapter(tmp_path, monkeypatch):
    provider = ClosingProvider()
    monkeypatch.setattr(
        "lamina.studio_server.make_provider",
        lambda adapter, **_: provider if adapter else None,
    )

    def broken_assets(path):
        raise RuntimeError("fixture setup failure")

    monkeypatch.setattr("lamina.studio_site.prepare_studio", broken_assets)
    with pytest.raises(RuntimeError, match="fixture setup failure"):
        StudioServer(tmp_path, port=0, adapter="fixture")
    assert provider.calls == 1


def test_cli_closes_created_adapter_after_validation_failure(tmp_path, monkeypatch):
    provider = ClosingProvider()
    monkeypatch.setattr(
        "lamina.studio_server.make_provider", lambda *args, **kwargs: provider
    )
    result = main(["produce", "--workspace", str(tmp_path), "--adapter", "fixture"])
    assert result == 1
    assert provider.calls == 1


def test_cli_leaves_automatic_context_selection_to_engine():
    arguments = parser().parse_args(
        ["produce", "--adapter", "fixture", "--brief", "Explain"]
    )
    assert arguments.core_words is None
    assert arguments.max_input_bytes is None
    assert arguments.reading is None
    assert arguments.max_attempts is None
