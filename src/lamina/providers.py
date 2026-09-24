"""JSON command adapter and deliberately limited, curated offline example."""

from __future__ import annotations

import concurrent.futures
import hashlib
import io
import json
import os
import queue
import subprocess
import threading
import time
import uuid
from dataclasses import replace
from importlib import resources
from pathlib import Path


class ProviderError(RuntimeError):
    """A public adapter failure; retry policy belongs to the calling runtime."""

    def __init__(
        self,
        message,
        *,
        code="provider_error",
        retryable=False,
        retry_after=None,
        usage=None,
    ):
        super().__init__(message)
        self.code = code
        self.retryable = bool(retryable)
        self.usage = _safe_usage(usage)
        self.retry_after = (
            float(retry_after)
            if type(retry_after) in {int, float} and 0 <= retry_after <= 3600
            else None
        )


def _safe_usage(usage):
    if not isinstance(usage, dict):
        return {}
    result = {
        key: value
        for key, value in usage.items()
        if key in {"input_tokens", "output_tokens", "cached_input_tokens"}
        and type(value) is int
        and value >= 0
    }
    if isinstance(usage.get("model"), str):
        result["model"] = usage["model"]
    return result


def _remote_error(error):
    # Adapter error text may contain source content, response bodies or credentials.
    # Expose a bounded vocabulary; keep diagnostics in the adapter's own logging.
    descriptions = {
        "rate_limit": "model endpoint rate limited the request",
        "timeout": "model endpoint timed out",
        "unavailable": "model endpoint is temporarily unavailable",
        "connection": "model endpoint connection failed",
        "authentication": "model endpoint rejected authentication",
        "invalid_request": "model endpoint rejected the request",
        "invalid_response": "model endpoint returned an invalid response",
        "output_truncated": "model output exceeded its output budget",
        "context_limit": "request exceeds the configured model context",
    }
    code = error.get("code") if isinstance(error, dict) else None
    if code not in descriptions:
        code = "adapter_error"
    return ProviderError(
        descriptions.get(code, "adapter reported a request failure"),
        code=code,
        retryable=code in {"rate_limit", "timeout", "unavailable", "connection"},
        retry_after=error.get("retry_after") if isinstance(error, dict) else None,
        usage=error.get("usage") if isinstance(error, dict) else None,
    )


class CommandProvider:
    """Run one stateless JSON command per request, without invoking a shell."""

    def __init__(
        self,
        command: list[str],
        timeout: float = 120,
        version: str | None = None,
        max_request_bytes: int = 2_000_000,
        env: dict[str, str] | None = None,
        request_format: str | None = None,
        budget=None,
        workload=None,
    ) -> None:
        if (
            not isinstance(command, list)
            or not command
            or any(not isinstance(x, str) or not x for x in command)
        ):
            raise ValueError("command must be a nonempty argument list")
        if not 1 <= timeout <= 3600:
            raise ValueError("timeout must be between 1 and 3600 seconds")
        if type(max_request_bytes) is not int or max_request_bytes < 1024:
            raise ValueError("max_request_bytes must be at least 1024")
        if env is not None and (
            not isinstance(env, dict)
            or any(
                not isinstance(k, str) or not isinstance(v, str) for k, v in env.items()
            )
        ):
            raise ValueError("adapter env must map names to strings")
        if request_format not in {None, "lamina-chat-1"}:
            raise ValueError("unknown adapter request_format")
        self.command, self.timeout = list(command), float(timeout)
        self.max_request_bytes = max_request_bytes
        self.env = {**os.environ, **(env or {})}
        self._local = threading.local()
        self.version = version or self.env.get("LAMINA_ADAPTER_VERSION", "unspecified")
        self.request_format = request_format
        from .workload_profiles import parse_workloads

        self.workloads = parse_workloads(workload)
        if budget is not None and budget.workload is not None:
            profile = budget.workload
            if profile.stage in self.workloads:
                raise ValueError("stage workload supplied in both budget and workload")
            self.workloads[profile.stage] = profile
            budget = replace(budget, workload=None)
        self._budget = budget
        self._stage_budgets = {}
        versions = []
        for arg in self.command:
            path = Path(arg)
            if path.is_file():
                versions.append(hashlib.sha256(path.read_bytes()).hexdigest())
        if request_format == "lamina-chat-1":
            from . import chat_protocol

            versions.append(
                hashlib.sha256(Path(chat_protocol.__file__).read_bytes()).hexdigest()
            )
        config = {
            key: value for key, value in self.env.items() if key.startswith("LAMINA_")
        }
        token = json.dumps(
            [
                self.command,
                versions,
                self.timeout,
                self.version,
                config,
                env,
                request_format,
                (
                    {
                        "max_request_bytes": budget.max_request_bytes,
                        "context_tokens": budget.context_tokens,
                        "output_tokens": budget.output_tokens,
                        "counting": budget.counting,
                    }
                    if budget is not None
                    else None
                ),
            ],
            sort_keys=True,
        )
        self.configuration_identity = (
            "command:" + hashlib.sha256(token.encode()).hexdigest()[:20]
        )
        for profile in self.workloads.values():
            profile.validate_binding(provider_identity=self.configuration_identity)
        workload_token = json.dumps(
            [
                self.configuration_identity,
                {k: v.identity for k, v in sorted(self.workloads.items())},
            ],
            sort_keys=True,
        )
        self.identity = (
            "command:" + hashlib.sha256(workload_token.encode()).hexdigest()[:20]
            if self.workloads
            else self.configuration_identity
        )

    def budget_for(self, stage):
        from .context_budget import RequestBudget

        if self._budget is None:
            needs_token_counter = bool(self.env.get("LAMINA_CONTEXT_TOKENS")) or any(
                profile.max_input_tokens is not None
                for profile in self.workloads.values()
            )
            if self.request_format == "lamina-chat-1" and needs_token_counter:
                from .chat_protocol import chat_token_count
                import tiktoken

                if not self.env.get("LAMINA_TOKENIZER"):
                    raise ValueError(
                        "token limits require an explicit LAMINA_TOKENIZER"
                    )
                encoding = tiktoken.get_encoding(self.env["LAMINA_TOKENIZER"])
                context_tokens = self.env.get("LAMINA_CONTEXT_TOKENS")
                self._budget = RequestBudget(
                    max_request_bytes=self.max_request_bytes,
                    context_tokens=int(context_tokens) if context_tokens else None,
                    output_tokens=(
                        int(self.env.get("LAMINA_MAX_OUTPUT_TOKENS", "8192"))
                        if context_tokens
                        else 0
                    ),
                    count_tokens=lambda request: chat_token_count(request, encoding),
                    counting="adapter-tokenizer-with-framing-reserve",
                )
            else:
                self._budget = RequestBudget(max_request_bytes=self.max_request_bytes)
        profile = self.workloads.get(stage, self.workloads.get("*"))
        if profile is None:
            return self._budget
        if profile.stage == "*":
            profile = replace(profile, stage=stage)
        if stage not in self._stage_budgets:
            self._stage_budgets[stage] = replace(self._budget, workload=profile)
        return self._stage_budgets[stage]

    def configuration_identity_for(self, stage):
        return self.configuration_identity

    def identity_for(self, stage):
        """Changing another stage's workload leaves this stage's cache reusable."""
        profile = self.workloads.get(stage, self.workloads.get("*"))
        if profile is not None and profile.stage == "*":
            profile = replace(profile, stage=stage)
        prefix = self.identity.split(":", 1)[0]
        if profile is None:
            return prefix + ":" + self.configuration_identity.split(":", 1)[1]
        token = json.dumps([self.configuration_identity, profile.identity])
        return prefix + ":" + hashlib.sha256(token.encode()).hexdigest()[:20]

    def last_usage(self):
        return getattr(self._local, "usage", {})

    def _request(self, stage, payload):
        self._local.usage = {}
        if payload.get("stage") != stage:
            raise ProviderError("stage mismatch in adapter request")
        text = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        if len(text.encode("utf-8")) > self.max_request_bytes:
            raise ProviderError(
                f"{stage} request exceeds {self.max_request_bytes} bytes"
            )
        return text

    def _reply(self, result):
        if not isinstance(result, dict):
            raise ProviderError("adapter reply must be a JSON object")
        if result.get("protocol") == "lamina-error-1":
            error = _remote_error(result.get("error", {}))
            self._local.usage = error.usage
            raise error
        if result.get("protocol") == "lamina-response-1":
            usage = result.get("usage", {})
            if not isinstance(usage, dict) or not isinstance(
                result.get("result"), dict
            ):
                raise ProviderError("response envelope needs result and usage objects")
            self._local.usage = _safe_usage(usage)
            if isinstance(result.get("model"), str):
                self._local.usage["model"] = result["model"]
            return result["result"]
        return result

    def call(self, stage: str, payload: dict) -> dict:
        request_text = self._request(stage, payload)
        try:
            process = subprocess.run(
                self.command,
                input=request_text,
                text=True,
                encoding="utf-8",
                capture_output=True,
                timeout=self.timeout,
                check=False,
                env=self.env,
            )
        except subprocess.TimeoutExpired as exc:
            raise ProviderError(
                f"{stage} adapter timed out after {self.timeout:g}s",
                code="timeout",
                retryable=True,
            ) from exc
        except OSError as exc:
            raise ProviderError(
                f"{stage} adapter could not start", code="adapter_start"
            ) from exc
        except UnicodeDecodeError as exc:
            raise ProviderError(
                f"{stage} adapter did not return UTF-8 JSON", code="invalid_response"
            ) from exc
        if process.returncode:
            raise ProviderError(f"{stage} adapter exited {process.returncode}")
        try:
            result = json.loads(process.stdout)
        except json.JSONDecodeError as exc:
            raise ProviderError(
                f"{stage} adapter did not return one JSON object"
            ) from exc
        return self._reply(result)

    def close(self):
        """One-shot commands have no retained process to close."""

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class PersistentCommandProvider(CommandProvider):
    """Multiplex bounded JSON-line requests through a lazily started process.

    A timeout or broken stream terminates that process and fails its outstanding
    calls. The next call starts a new process. A caller may retry failed calls
    under its own policy; this transport never resubmits a request itself.
    """

    def __init__(self, *args, max_pending=8, max_response_bytes=16_000_000, **kwargs):
        super().__init__(*args, **kwargs)
        if type(max_pending) is not int or not 1 <= max_pending <= 128:
            raise ValueError("max_pending must be between 1 and 128")
        if type(max_response_bytes) is not int or max_response_bytes < 1024:
            raise ValueError("max_response_bytes must be at least 1024")
        self.max_pending, self.max_response_bytes = max_pending, max_response_bytes
        self._slots = threading.BoundedSemaphore(max_pending)
        self._lock = threading.Lock()
        self._process = None
        self._outgoing = None
        self._pending = {}
        self._closed = False
        self.identity = "jsonl:" + self.identity.removeprefix("command:")

    def _start_locked(self):
        if self._closed:
            raise ProviderError("adapter is closed", code="closed")
        if self._process is not None:
            return self._process, self._outgoing
        try:
            process = subprocess.Popen(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                env={
                    **self.env,
                    "LAMINA_SERVICE_WORKERS": str(self.max_pending),
                    "LAMINA_SERVICE_MAX_REQUEST_BYTES": str(
                        self.max_request_bytes + 512
                    ),
                },
                bufsize=0,
            )
        except OSError as exc:
            raise ProviderError(
                "persistent adapter could not start", code="adapter_start"
            ) from exc
        outgoing = queue.Queue(self.max_pending)
        self._process, self._outgoing = process, outgoing
        threading.Thread(target=self._read, args=(process,), daemon=True).start()
        threading.Thread(
            target=self._write, args=(process, outgoing), daemon=True
        ).start()
        return process, outgoing

    def _break(self, process, error):
        with self._lock:
            if self._process is not process:
                return
            self._process = None
            outgoing, self._outgoing = self._outgoing, None
            pending, self._pending = self._pending, {}
        for future in pending.values():
            future.set_exception(error)
        # Wake the writer if idle. Killing also releases a blocked pipe write.
        try:
            outgoing.put_nowait(None)
        except queue.Full:
            pass
        if process.poll() is None:
            process.kill()
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            pass
        if process.stdin:
            process.stdin.close()
        if process.stdout:
            process.stdout.close()

    def _write(self, process, outgoing):
        try:
            while True:
                request = outgoing.get()
                if request is None:
                    return
                remaining = memoryview(request)
                while remaining:
                    written = process.stdin.write(remaining)
                    if not written:
                        raise OSError("adapter input closed")
                    remaining = remaining[written:]
                process.stdin.flush()
        except (OSError, ValueError):
            self._break(
                process,
                ProviderError(
                    "adapter stream disconnected", code="connection", retryable=True
                ),
            )

    def _read(self, process):
        try:
            with io.BufferedReader(process.stdout) as stream:
                while True:
                    line = stream.readline(self.max_response_bytes + 1)
                    if not line:
                        raise EOFError
                    if len(line) > self.max_response_bytes or not line.endswith(b"\n"):
                        raise ValueError
                    response = json.loads(line)
                    if not isinstance(response, dict) or not isinstance(
                        response.get("id"), str
                    ):
                        raise ValueError
                    if ("result" in response) == ("error" in response):
                        raise ValueError
                    with self._lock:
                        if self._process is not process:
                            return
                        future = self._pending.pop(response["id"], None)
                        if future is None:
                            raise ValueError
                        if "error" in response:
                            future.set_exception(_remote_error(response["error"]))
                        else:
                            future.set_result(response["result"])
        except (EOFError, OSError):
            self._break(
                process,
                ProviderError(
                    "adapter stream disconnected", code="connection", retryable=True
                ),
            )
        except (ValueError, TypeError, UnicodeError):
            self._break(
                process,
                ProviderError(
                    "adapter returned an invalid JSON-line response",
                    code="invalid_response",
                ),
            )

    def call(self, stage, payload):
        request_text = self._request(stage, payload)
        started = time.monotonic()
        if not self._slots.acquire(timeout=self.timeout):
            raise ProviderError(
                "adapter pending-call capacity timed out",
                code="timeout",
                retryable=True,
            )
        process = None
        try:
            future = concurrent.futures.Future()
            identifier = uuid.uuid4().hex
            with self._lock:
                process, outgoing = self._start_locked()
                self._pending[identifier] = future
                outgoing.put_nowait(
                    (
                        '{"protocol":"lamina-jsonl-1","id":'
                        + json.dumps(identifier)
                        + ',"payload":'
                        + request_text
                        + "}\n"
                    ).encode("utf-8")
                )
            remaining = max(0, self.timeout - (time.monotonic() - started))
            try:
                result = future.result(timeout=remaining)
            except ProviderError as exc:
                self._local.usage = exc.usage
                raise
            except concurrent.futures.TimeoutError as exc:
                error = ProviderError(
                    "persistent adapter request timed out",
                    code="timeout",
                    retryable=True,
                )
                self._break(process, error)
                raise error from exc
            return self._reply(result)
        finally:
            self._slots.release()

    def close(self):
        with self._lock:
            self._closed = True
            process = self._process
        if process is not None:
            self._break(process, ProviderError("adapter was closed", code="closed"))

    def restart(self):
        self.close()
        with self._lock:
            self._closed = False


class StageProvider:
    """Choose a configured adapter by stage; no routing model is involved."""

    def __init__(self, default, stages):
        self.default, self.stages = default, dict(stages)
        self._local = threading.local()
        config = [default.identity, {k: v.identity for k, v in sorted(stages.items())}]
        self.identity = (
            "stages:" + hashlib.sha256(json.dumps(config).encode()).hexdigest()[:20]
        )

    def identity_for(self, stage):
        provider = self.stages.get(stage, self.default)
        return getattr(provider, "identity_for", lambda _: provider.identity)(stage)

    def configuration_identity_for(self, stage):
        provider = self.stages.get(stage, self.default)
        return getattr(provider, "configuration_identity", provider.identity)

    def budget_for(self, stage):
        from .context_budget import RequestBudget

        provider = self.stages.get(stage, self.default)
        method = getattr(provider, "budget_for", None)
        return (
            method(stage)
            if method
            else RequestBudget(
                max_request_bytes=getattr(provider, "max_request_bytes", 2_000_000)
            )
        )

    def call(self, stage, payload):
        provider = self.stages.get(stage, self.default)
        self._local.provider = provider
        return provider.call(stage, payload)

    def last_usage(self):
        return getattr(
            getattr(self._local, "provider", None), "last_usage", lambda: {}
        )()

    def close(self):
        for provider in {
            id(p): p for p in [self.default, *self.stages.values()]
        }.values():
            getattr(provider, "close", lambda: None)()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def configured_provider(path):
    """Load a startup-only JSON adapter configuration. Secrets can stay in env."""
    data = json.loads(Path(path).read_text())
    if (
        not isinstance(data, dict)
        or set(data) - {"default", "stages", "qc_report"}
        or "default" not in data
    ):
        raise ValueError("provider configuration needs default and optional stages")

    def make(row):
        fields = {
            "command",
            "timeout",
            "version",
            "max_request_bytes",
            "env",
            "request_format",
            "transport",
            "workload",
        }
        if not isinstance(row, dict):
            raise ValueError("invalid adapter configuration")
        transport = row.get("transport", "command")
        if transport == "jsonl":
            fields |= {"max_pending", "max_response_bytes"}
        if transport not in {"command", "jsonl"} or set(row) - fields:
            raise ValueError("invalid adapter configuration")
        row = dict(row)
        if row.get("workload") == "starter":
            from .calibration import starter_workloads

            row["workload"] = starter_workloads()
        if isinstance(row.get("workload"), dict):
            row["workload"] = json.loads(json.dumps(row["workload"]))
            for profile in row["workload"].values():
                evidence = (
                    profile.get("evidence") if isinstance(profile, dict) else None
                )
                if isinstance(evidence, dict) and isinstance(
                    evidence.get("report_path"), str
                ):
                    location = Path(evidence["report_path"])
                    if not location.is_absolute():
                        evidence["report_path"] = str(
                            Path(path).resolve().parent / location
                        )
        factory = PersistentCommandProvider if transport == "jsonl" else CommandProvider
        return factory(
            **{key: value for key, value in row.items() if key != "transport"}
        )

    stages = data.get("stages", {})
    if not isinstance(stages, dict) or any(not isinstance(k, str) for k in stages):
        raise ValueError("stages must map stage names to adapter configurations")
    provider = StageProvider(make(data["default"]), {k: make(v) for k, v in stages.items()})
    if "qc_report" in data:
        if not isinstance(data["qc_report"], str):
            provider.close()
            raise ValueError("qc_report must be a report path")
        provider.qc_report = str((Path(path).resolve().parent / data["qc_report"]).resolve())
    return provider


class DemoProvider:
    """Curated output for the exact bundled guide, never arbitrary generation."""

    def __init__(self) -> None:
        fixture_path = resources.files("lamina").joinpath("demo/fixture.json")
        fixture_bytes = fixture_path.read_bytes()
        self.fixture = json.loads(fixture_bytes)
        example_root = Path(__file__).resolve().parent / "demo" / "sources"
        self.expected = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(example_root.glob("*.md"))
        }
        from .ingest import read_source

        self.expected_units = {
            path.name: {
                (unit["heading"], unit["text"]) for unit in read_source(path)[1]
            }
            for path in sorted(example_root.glob("*.md"))
        }
        if len(self.expected) != 3:
            raise ProviderError("the bundled three-file field guide is unavailable")
        fingerprint = hashlib.sha256(
            fixture_bytes + json.dumps(self.expected, sort_keys=True).encode()
        ).hexdigest()
        self.identity = "curated-offline-field-guide:" + fingerprint[:20]

    def _manifest(self, data: dict, stage: str) -> None:
        given = data.get("source_manifest")
        if not isinstance(given, list):
            raise ProviderError(
                "offline demo requires its exact bundled source manifest"
            )
        pairs = {
            str(x.get("filename")): str(x.get("sha256"))
            for x in given
            if isinstance(x, dict)
        }
        if (
            len(given) != len(pairs)
            or not pairs
            or any(self.expected.get(name) != digest for name, digest in pairs.items())
            or (stage in {"plan", "reconcile"} and pairs != self.expected)
        ):
            raise ProviderError(
                "offline demo only accepts the bundled original field guide"
            )

    @staticmethod
    def _aliases(concepts: list[dict], templates: list[dict]) -> dict[str, dict]:
        by_title = {c.get("title"): c for c in concepts}
        if set(by_title) != {t["title"] for t in templates}:
            raise ProviderError(
                "offline demo concept set differs from its curated guide"
            )
        aliases = {t["alias"]: by_title[t["title"]] for t in templates}
        for t in templates:
            if not any(
                e.get("quote") == t["quote"]
                for e in aliases[t["alias"]].get("evidence", [])
            ):
                raise ProviderError(
                    "offline demo concept evidence differs from its curated guide"
                )
        return aliases

    def call(self, stage: str, payload: dict) -> dict:
        if payload.get("stage") != stage or payload.get("protocol") != "lamina-stage-1":
            raise ProviderError("unsupported offline demo stage protocol")
        data = payload.get("input")
        if not isinstance(data, dict):
            raise ProviderError("offline demo input must be an object")
        self._manifest(data, stage)
        templates = self.fixture["concepts"]
        canonical_templates = [t for t in templates if t["alias"] != "lease_limit"]
        if stage == "extract":
            source = data.get("source") or {}
            core = data.get("core") or {}
            filename = source.get("filename")
            if (
                filename not in self.expected
                or source.get("sha256") != self.expected[filename]
            ):
                raise ProviderError("offline demo received an unknown source")
            text = core.get("text") or ""
            if (
                core.get("source_id") != source.get("id")
                or core.get("role") != "teaching"
                or (core.get("heading"), text) not in self.expected_units[filename]
            ):
                raise ProviderError(
                    "offline demo core unit differs from its bundled source"
                )
            concepts = [
                t for t in templates if t["filename"] == filename and t["quote"] in text
            ]
            # A source split may yield a unit without a featured quote; it is
            # still validated by the exact manifest, and returns no concepts.
            return {
                "concepts": [
                    {
                        "title": t["title"],
                        "explanation": t["explanation"],
                        "evidence": [{"unit_id": core["id"], "quote": t["quote"]}],
                    }
                    for t in concepts
                ]
            }
        if stage == "reconcile":
            aliases = self._aliases(data.get("raw_concepts") or [], templates)
            rows = []
            for t in canonical_templates:
                members = (
                    [t["alias"], "lease_limit"]
                    if t["alias"] == "lease"
                    else [t["alias"]]
                )
                rows.append(
                    {
                        "title": t["title"],
                        "explanation": t["explanation"],
                        "member_ids": [aliases[a]["id"] for a in members],
                        "evidence": [
                            e for a in members for e in aliases[a]["evidence"]
                        ],
                    }
                )
            return {"concepts": rows}
        if stage == "plan":
            aliases = self._aliases(data.get("concepts") or [], canonical_templates)
            return {
                "title": self.fixture["title"],
                "lessons": [
                    {
                        "id": l["id"],
                        "title": l["title"],
                        "concept_ids": [aliases[a]["id"] for a in l["aliases"]],
                        "prerequisite_ids": l["prerequisite_ids"],
                    }
                    for l in self.fixture["lessons"]
                ],
                "deferred": [],
            }
        if stage in {"author", "review"}:
            planned = data.get("lesson") or {}
            lid = planned.get("id")
            template = next(
                (l for l in self.fixture["lessons"] if l["id"] == lid), None
            )
            if template is None:
                raise ProviderError("offline demo received an unknown lesson")
            aliases = self._aliases(
                data.get("concepts") or [],
                [t for t in canonical_templates if t["alias"] in template["aliases"]],
            )
            if stage == "review":
                if planned.get("title") != template["title"]:
                    raise ProviderError("offline demo cannot review a changed lesson")
                return {"status": "pass", "issues": []}
            if planned.get("concept_ids") != [
                aliases[a]["id"] for a in template["aliases"]
            ]:
                raise ProviderError(
                    "offline demo lesson assignment differs from fixture"
                )

            def evidence(names: list[str]) -> list[dict]:
                return [dict(e) for alias in names for e in aliases[alias]["evidence"]]

            scenario_template = template.get("scenario")
            scenario = None
            if scenario_template:
                scenario = {
                    "title": scenario_template["title"],
                    "candidate_brief": scenario_template["candidate_brief"],
                    "findings": [
                        {
                            "id": f["id"],
                            "label": f["label"],
                            "text": f["text"],
                            "evidence": evidence(f["evidence"]),
                        }
                        for f in scenario_template["findings"]
                    ],
                    "decision_prompt": scenario_template["decision_prompt"],
                    "checklist": [
                        {
                            "id": c["id"],
                            "criterion": c["criterion"],
                            "evidence": evidence(c["evidence"]),
                        }
                        for c in scenario_template["checklist"]
                    ],
                    "second_event": {
                        "trigger": scenario_template["second_event"]["trigger"],
                        "text": scenario_template["second_event"]["text"],
                        "evidence": evidence(
                            scenario_template["second_event"]["evidence"]
                        ),
                    },
                    "reassessment_prompt": scenario_template["reassessment_prompt"],
                    "debrief": scenario_template["debrief"],
                }
            return {
                "id": lid,
                "title": template["title"],
                "concept_ids": planned["concept_ids"],
                "summary": template["summary"],
                "sections": [
                    {
                        "heading": s["heading"],
                        "body": s["body"],
                        "evidence": evidence(s["evidence"]),
                    }
                    for s in template["sections"]
                ],
                "questions": [
                    {
                        "id": q["id"],
                        "kind": q["kind"],
                        "prompt": q["prompt"],
                        "answer": q["answer"],
                        "rationale": q["rationale"],
                        "concept_ids": [aliases[a]["id"] for a in q["aliases"]],
                        "evidence": evidence(q["evidence"]),
                    }
                    for q in template["questions"]
                ],
                "audio_script": template["audio_script"],
                "scenario": scenario,
            }
        raise ProviderError(f"offline demo cannot perform stage {stage}")
