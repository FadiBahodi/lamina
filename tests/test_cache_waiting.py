"""Cache observation must not compete with active writers for SQLite's lock."""

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import threading

from lamina.store import Workspace


class ObservedWorkspace(Workspace):
    def __init__(self, path):
        self.observations = defaultdict(int)
        self.waiter_writes = []
        self.observed_waiters = threading.Event()
        self.trace_lock = threading.Lock()
        super().__init__(path)

    @contextmanager
    def connection(self):
        def trace(statement):
            name = threading.current_thread().name
            if not name.startswith("waiting-reader"):
                return
            with self.trace_lock:
                if statement.startswith("SELECT status,lease_until,result"):
                    self.observations[name] += 1
                    if (
                        len(self.observations) == 3
                        and min(self.observations.values()) >= 3
                    ):
                        self.observed_waiters.set()
                if statement.startswith("BEGIN IMMEDIATE"):
                    self.waiter_writes.append(statement)

        with super().connection() as db:
            db.set_trace_callback(trace)
            yield db


def test_active_job_waiters_poll_read_only_and_share_one_result(tmp_path):
    workspace = ObservedWorkspace(tmp_path)
    entered, release = threading.Event(), threading.Event()
    handlers = []

    def handler(payload):
        handlers.append(payload)
        entered.set()
        assert release.wait(5)
        return {"result": "shared"}

    def run():
        return workspace.run_cached(
            "extract", {"same": True}, handler, identity="fixture"
        )

    with ThreadPoolExecutor(max_workers=1) as owner:
        first = owner.submit(run)
        assert entered.wait(5)
        with ThreadPoolExecutor(
            max_workers=3, thread_name_prefix="waiting-reader"
        ) as pool:
            waiting = [pool.submit(run) for _ in range(3)]
            try:
                assert workspace.observed_waiters.wait(
                    5
                ), "waiters did not observe the live job repeatedly"
                assert workspace.waiter_writes == []
            finally:
                release.set()
            assert [future.result() for future in waiting] == [{"result": "shared"}] * 3
        assert first.result() == {"result": "shared"}
    assert len(handlers) == 1
    assert workspace.stats()["attempts"] == 1
