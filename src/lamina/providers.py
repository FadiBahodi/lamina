"""JSON command adapter and deliberately limited, curated offline example."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from importlib import resources
from pathlib import Path


class ProviderError(RuntimeError):
    pass


class CommandProvider:
    """Invoke an executable with one JSON request on stdin and one JSON reply.

    The adapter may call any user-selected model. This library never invokes a
    shell or assumes an API vendor. A nonzero exit or invalid object fails the
    stage, leaving completed earlier stages cached for retry.
    """

    def __init__(self, command: list[str], timeout: float = 120,
                 version: str | None = None, max_request_bytes: int = 2_000_000) -> None:
        if not isinstance(command, list) or not command or any(
            not isinstance(x, str) or not x for x in command
        ):
            raise ValueError("command must be a nonempty argument list")
        if not 1 <= timeout <= 3600:
            raise ValueError("timeout must be between 1 and 3600 seconds")
        if max_request_bytes < 1024:
            raise ValueError("max_request_bytes must be at least 1024")
        self.command = list(command)
        self.timeout = float(timeout)
        self.max_request_bytes = max_request_bytes
        self.version = version or os.environ.get("LAMINA_ADAPTER_VERSION", "unspecified")
        # Local adapter edits invalidate cached model calls when a command
        # argument names a readable file. For other commands, argv is stable.
        versions = []
        for arg in self.command:
            path = Path(arg)
            if path.is_file():
                versions.append(hashlib.sha256(path.read_bytes()).hexdigest())
        token = json.dumps([self.command, versions, self.timeout, self.version], sort_keys=True)
        self.identity = "command:" + hashlib.sha256(token.encode()).hexdigest()[:20]

    def call(self, stage: str, payload: dict) -> dict:
        if payload.get("stage") != stage:
            raise ProviderError("stage mismatch in adapter request")
        request_text = json.dumps(payload, ensure_ascii=False)
        if len(request_text.encode("utf-8")) > self.max_request_bytes:
            raise ProviderError(f"{stage} request exceeds {self.max_request_bytes} bytes; split the source or increase the adapter limit")
        try:
            process = subprocess.run(
                self.command, input=request_text,
                text=True, capture_output=True, timeout=self.timeout, check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ProviderError(f"{stage} adapter timed out after {self.timeout:g}s") from exc
        except OSError as exc:
            raise ProviderError(f"{stage} adapter could not start: {exc}") from exc
        if process.returncode:
            detail = process.stderr.strip()[-1200:]
            raise ProviderError(f"{stage} adapter exited {process.returncode}: {detail}")
        try:
            result = json.loads(process.stdout)
        except json.JSONDecodeError as exc:
            raise ProviderError(f"{stage} adapter did not return one JSON object") from exc
        if not isinstance(result, dict):
            raise ProviderError(f"{stage} adapter reply must be a JSON object")
        return result


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
        self.expected_units = {}
        for path in sorted(example_root.glob("*.md")):
            body = path.read_text(encoding="utf-8").split("\n## ", 1)
            if len(body) != 2 or "\n" not in body[1]:
                raise ProviderError("offline guide has an unexpected section shape")
            heading, text = body[1].split("\n", 1)
            self.expected_units[path.name] = (heading.strip(), text.strip())
        if len(self.expected) != 3:
            raise ProviderError("the bundled three-file field guide is unavailable")
        fingerprint = hashlib.sha256(fixture_bytes + json.dumps(self.expected, sort_keys=True).encode()).hexdigest()
        self.identity = "curated-offline-field-guide:" + fingerprint[:20]

    def _manifest(self, data: dict, stage: str) -> None:
        given = data.get("source_manifest")
        if not isinstance(given, list):
            raise ProviderError("offline demo requires its exact bundled source manifest")
        pairs = {str(x.get("filename")): str(x.get("sha256")) for x in given if isinstance(x, dict)}
        if (len(given) != len(pairs) or not pairs or
                any(self.expected.get(name) != digest for name, digest in pairs.items()) or
                (stage in {"plan", "reconcile"} and pairs != self.expected)):
            raise ProviderError("offline demo only accepts the bundled original field guide")

    @staticmethod
    def _aliases(concepts: list[dict], templates: list[dict]) -> dict[str, dict]:
        by_title = {c.get("title"): c for c in concepts}
        if set(by_title) != {t["title"] for t in templates}:
            raise ProviderError("offline demo concept set differs from its curated guide")
        aliases = {t["alias"]: by_title[t["title"]] for t in templates}
        for t in templates:
            if not any(e.get("quote") == t["quote"] for e in aliases[t["alias"]].get("evidence", [])):
                raise ProviderError("offline demo concept evidence differs from its curated guide")
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
            if filename not in self.expected or source.get("sha256") != self.expected[filename]:
                raise ProviderError("offline demo received an unknown source")
            text = core.get("text") or ""
            if (core.get("source_id") != source.get("id") or core.get("role") != "teaching"
                    or (core.get("heading"), text) != self.expected_units[filename]):
                raise ProviderError("offline demo core unit differs from its bundled source")
            concepts = [t for t in templates if t["filename"] == filename and t["quote"] in text]
            # A source split may yield a unit without a featured quote; it is
            # still validated by the exact manifest, and returns no concepts.
            return {"concepts": [{"title": t["title"], "explanation": t["explanation"],
                                  "evidence": [{"unit_id": core["id"], "quote": t["quote"]}]}
                                 for t in concepts]}
        if stage == "reconcile":
            aliases = self._aliases(data.get("raw_concepts") or [], templates)
            rows = []
            for t in canonical_templates:
                members = [t["alias"], "lease_limit"] if t["alias"] == "lease" else [t["alias"]]
                rows.append({"title": t["title"], "explanation": t["explanation"],
                             "member_ids": [aliases[a]["id"] for a in members],
                             "evidence": [e for a in members for e in aliases[a]["evidence"]]})
            return {"concepts": rows}
        if stage == "plan":
            aliases = self._aliases(data.get("concepts") or [], canonical_templates)
            return {"title": self.fixture["title"],
                    "lessons": [{"id": l["id"], "title": l["title"],
                                 "concept_ids": [aliases[a]["id"] for a in l["aliases"]],
                                 "prerequisite_ids": l["prerequisite_ids"]}
                                for l in self.fixture["lessons"]], "deferred": []}
        if stage in {"author", "review"}:
            planned = data.get("lesson") or {}
            lid = planned.get("id")
            template = next((l for l in self.fixture["lessons"] if l["id"] == lid), None)
            if template is None:
                raise ProviderError("offline demo received an unknown lesson")
            aliases = self._aliases(data.get("concepts") or [],
                                    [t for t in canonical_templates if t["alias"] in template["aliases"]])
            if stage == "review":
                if planned.get("title") != template["title"]:
                    raise ProviderError("offline demo cannot review a changed lesson")
                return {"status": "pass", "issues": []}
            if planned.get("concept_ids") != [aliases[a]["id"] for a in template["aliases"]]:
                raise ProviderError("offline demo lesson assignment differs from fixture")
            def evidence(names: list[str]) -> list[dict]:
                return [dict(e) for alias in names for e in aliases[alias]["evidence"]]
            scenario_template = template.get("scenario")
            scenario = None
            if scenario_template:
                scenario = {
                    "title": scenario_template["title"],
                    "candidate_brief": scenario_template["candidate_brief"],
                    "findings": [{"id": f["id"], "label": f["label"], "text": f["text"],
                                  "evidence": evidence(f["evidence"])}
                                 for f in scenario_template["findings"]],
                    "decision_prompt": scenario_template["decision_prompt"],
                    "checklist": [{"id": c["id"], "criterion": c["criterion"],
                                   "evidence": evidence(c["evidence"])}
                                  for c in scenario_template["checklist"]],
                    "second_event": {"trigger": scenario_template["second_event"]["trigger"],
                                     "text": scenario_template["second_event"]["text"],
                                     "evidence": evidence(scenario_template["second_event"]["evidence"])},
                    "reassessment_prompt": scenario_template["reassessment_prompt"],
                    "debrief": scenario_template["debrief"],
                }
            return {"id": lid, "title": template["title"],
                    "concept_ids": planned["concept_ids"], "summary": template["summary"],
                    "sections": [{"heading": s["heading"], "body": s["body"],
                                  "evidence": evidence(s["evidence"])} for s in template["sections"]],
                    "questions": [{"id": q["id"], "kind": q["kind"], "prompt": q["prompt"],
                                   "answer": q["answer"], "rationale": q["rationale"],
                                   "concept_ids": [aliases[a]["id"] for a in q["aliases"]],
                                   "evidence": evidence(q["evidence"])} for q in template["questions"]],
                    "audio_script": template["audio_script"], "scenario": scenario}
        raise ProviderError(f"offline demo cannot perform stage {stage}")
