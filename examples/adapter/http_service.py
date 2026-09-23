#!/usr/bin/env python3
"""Persistent JSON-lines chat adapter with a bounded shared HTTP connection pool."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
import sys
import threading

import httpx

from http_chat import (
    AdapterFailure,
    endpoint,
    http_failure,
    request_body,
    response_result,
)


def main():
    workers = int(os.environ.get("LAMINA_SERVICE_WORKERS", "8"))
    if not 1 <= workers <= 128:
        raise ValueError("LAMINA_SERVICE_WORKERS must be 1–128")
    maximum = int(os.environ.get("LAMINA_SERVICE_MAX_REQUEST_BYTES", "2000000"))
    write_lock = threading.Lock()
    slots = threading.BoundedSemaphore(workers)
    with (
        httpx.Client(
            http2=os.environ.get("LAMINA_HTTP2") == "1",
            limits=httpx.Limits(
                max_connections=workers, max_keepalive_connections=workers
            ),
            timeout=100,
            follow_redirects=False,
            headers={"Authorization": "Bearer " + os.environ["LAMINA_API_KEY"]},
        ) as client,
        ThreadPoolExecutor(max_workers=workers) as executor,
    ):
        url = endpoint()

        def run(row):
            try:
                request = row["payload"]
                response = client.post(url, json=request_body(request))
                if response.status_code >= 400:
                    raise http_failure(
                        response.status_code, response.headers.get("Retry-After")
                    )
                try:
                    envelope = response.json()
                except ValueError as exc:
                    raise AdapterFailure("invalid_response") from exc
                reply = {"id": row["id"], "result": response_result(envelope, request)}
            except AdapterFailure as exc:
                reply = {"id": row["id"], "error": exc.error()}
            except httpx.TimeoutException:
                reply = {"id": row["id"], "error": {"code": "timeout"}}
            except httpx.TransportError:
                reply = {"id": row["id"], "error": {"code": "connection"}}
            except Exception:
                reply = {"id": row["id"], "error": {"code": "invalid_request"}}
            try:
                with write_lock:
                    sys.stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
                    sys.stdout.flush()
            finally:
                slots.release()

        while True:
            line = sys.stdin.buffer.readline(maximum + 1)
            if not line:
                break
            if len(line) > maximum or not line.endswith(b"\n"):
                return 1
            row = json.loads(line)
            if (
                not isinstance(row, dict)
                or row.get("protocol") != "lamina-jsonl-1"
                or not isinstance(row.get("id"), str)
                or not isinstance(row.get("payload"), dict)
            ):
                return 1
            slots.acquire()
            executor.submit(run, row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
