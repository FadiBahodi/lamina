"""Observed canary survival through the real production path.

The oracle matches explicit phrases in authored statements and source quotes.
It detects known omissions and counterfacts; it does not certify semantic recall.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
import hashlib
import os
from pathlib import Path
import re
import threading
import time

from .context_budget import RequestBudget
from .ingest import ingest_paths
from .production import plan_production, run_production
from .production_contract import REVISION
from .store import Workspace, canonical

ORACLE_VERSION = "local-qualified-phrase-and-source-3"


def normalized(text):
    return " ".join(text.split()).casefold()


def contains_phrase(text, phrase):
    return (
        re.search(
            r"(?<!\w)" + re.escape(normalized(phrase)) + r"(?!\w)", normalized(text)
        )
        is not None
    )


@dataclass(frozen=True)
class Canary:
    id: str
    source: str
    subject: str
    required: tuple[str, ...]
    forbidden: tuple[str, ...]
    position: str
    kind: str


_MARKDOWN_BLOCK = re.compile(
    r"^\s*(?:#{1,6}(?:\s|$)|(?:[-*+]|\d+[.)])\s+|>\s?|```|~~~|\|)"
)


def _prose_blocks(text):
    """Join hard-wrapped prose while retaining authored block boundaries."""
    prose = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if not line.strip():
            if prose:
                yield " ".join(prose)
                prose = []
        elif _MARKDOWN_BLOCK.match(line):
            if prose:
                yield " ".join(prose)
                prose = []
            yield line
        else:
            prose.append(line.strip())
    if prose:
        yield " ".join(prose)


def relation_spans(text, subjects):
    """Conservative lexical statements, split again at another named subject.

    This is an evaluation grammar for the declared canaries. It deliberately
    rejects some valid prose; it is not a general sentence or entailment parser.
    """
    names = "|".join(
        re.escape(normalized(name))
        for name in sorted(set(subjects), key=len, reverse=True)
    )
    pattern = re.compile(r"(?<!\w)(?:" + names + r")(?!\w)")
    for block in _prose_blocks(text):
        for statement in re.split(r"(?<=[.!?])\s+", block):
            statement = normalized(statement)
            mentions = list(pattern.finditer(statement))
            cuts = [0, *(match.start() for match in mentions[1:]), len(statement)]
            for start, end in zip(cuts, cuts[1:]):
                if fragment := statement[start:end].strip():
                    yield fragment


def score_canaries(canaries, rows, source_by_unit):
    """Match a local statement with locally supporting, correct-source evidence.

    Required phrases must occur together within one prose sentence or Markdown
    block, without borrowing values from a neighboring named subject. Ordinary
    single newlines are treated as source-extraction hard wraps. Citation text
    cannot supply a phrase missing from the model's explanation or body.
    """
    checked = []
    subjects = [fact.subject for fact in canaries]
    row_spans = [(row, list(relation_spans(row["text"], subjects))) for row in rows]
    for fact in canaries:
        relevant = [
            (row, spans)
            for row, spans in row_spans
            if any(contains_phrase(span, fact.subject) for span in spans)
        ]
        authored = [
            row
            for row, spans in relevant
            if any(
                all(contains_phrase(span, phrase) for phrase in fact.required)
                for span in spans
            )
        ]
        counterfacts = [
            phrase
            for phrase in fact.forbidden
            if any(contains_phrase(row["text"], phrase) for row, _ in relevant)
        ]
        supported = []
        for row in authored:
            evidence_spans = [
                span
                for item in row.get("evidence", [])
                if source_by_unit.get(item["unit_id"]) == fact.source
                for span in relation_spans(item["quote"], subjects)
            ]
            if any(
                all(contains_phrase(span, phrase) for phrase in fact.required)
                for span in evidence_spans
            ):
                supported.append(row)
        status = (
            "counterfact"
            if counterfacts
            else (
                "preserved"
                if supported
                else (
                    "wrong_or_missing_source"
                    if authored
                    else "required_phrase_missing"
                    if relevant
                    else "absent"
                )
            )
        )
        checked.append(
            {
                **asdict(fact),
                "status": status,
                "matching_row_ids": [row["id"] for row in supported],
                "counterfacts": counterfacts,
            }
        )
    preserved = sum(row["status"] == "preserved" for row in checked)
    by_position = {}
    for position in sorted({row["position"] for row in checked}):
        subset = [row for row in checked if row["position"] == position]
        by_position[position] = {
            "preserved": sum(row["status"] == "preserved" for row in subset),
            "total": len(subset),
        }
    return {
        "oracle": ORACLE_VERSION,
        "preserved": preserved,
        "total": len(checked),
        "fraction": preserved / len(checked) if checked else None,
        "counterfacts": sum(row["status"] == "counterfact" for row in checked),
        "by_position": by_position,
        "checks": checked,
    }


def make_corpus(folder, load):
    """Original fictional equipment data; load counts background paragraphs.

    All background statements are distinct and carry a condition and a number.
    The oracle covers the declared canaries only, not every background fact.
    """
    if type(load) is not int or load < 1:
        raise ValueError("load must be a positive number of background paragraphs")
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    first = "In the 2026 specification, Rotor Nacre stops above 17 m/s unless supervised service mode is active."
    middle = "Rotor Umber does not reset while its red lamp is illuminated."
    last = "Vessel Sable permits 14 kPa only after its purge has run for 2 minutes."
    table = (
        "| Circuit | Fixture specification |\n| --- | --- |\n"
        "| Panel Jade lane L | Current is 6 mA only below 4 C. |\n"
        "| Panel Jade lane M | Current is 9 mA only at or above 4 C. |"
    )
    paragraphs = [
        f"Auxiliary assembly {index:05d} records code {index + 100} only after its amber indicator remains steady for {index % 19 + 1} seconds."
        for index in range(load)
    ]
    cut = load // 2
    text = (
        "\n\n".join([first, *paragraphs[:cut], middle, table, *paragraphs[cut:], last])
        + "\n"
    )
    archive = "The 2018 specification states that Rotor Nacre stops above 13 m/s; that historical setting does not apply to the 2026 controller.\n"
    paths = [folder / "current.md", folder / "historical.md"]
    paths[0].write_text(text, encoding="utf-8")
    paths[1].write_text(archive, encoding="utf-8")
    canaries = [
        Canary(
            "threshold",
            "current.md",
            "Rotor Nacre",
            ("2026", "Rotor Nacre", "17 m/s", "unless supervised service mode"),
            ("Rotor Nacre always stops above 17 m/s",),
            "start",
            "qualification",
        ),
        Canary(
            "negation",
            "current.md",
            "Rotor Umber",
            ("Rotor Umber", "does not reset", "red lamp"),
            (
                "Rotor Umber resets while its red lamp",
                "Rotor Umber generates electricity from its red lamp",
            ),
            "middle",
            "negation",
        ),
        Canary(
            "table-l",
            "current.md",
            "Panel Jade lane L",
            ("Panel Jade lane L", "6 mA", "only below 4 C"),
            ("Panel Jade lane L uses 9 mA",),
            "middle-table",
            "association",
        ),
        Canary(
            "table-m",
            "current.md",
            "Panel Jade lane M",
            ("Panel Jade lane M", "9 mA", "only at or above 4 C"),
            ("Panel Jade lane M uses 6 mA",),
            "middle-table",
            "association",
        ),
        Canary(
            "sequence",
            "current.md",
            "Vessel Sable",
            ("Vessel Sable", "14 kPa", "only after", "2 minutes"),
            ("Vessel Sable permits 14 kPa before",),
            "end",
            "sequence",
        ),
        Canary(
            "history",
            "historical.md",
            "Rotor Nacre",
            ("2018", "Rotor Nacre", "13 m/s", "does not apply", "2026"),
            ("13 m/s applies to the 2026 controller",),
            "separate-source",
            "authority-context",
        ),
    ]
    return paths, canaries


class ObservedProvider:
    """Transparent wrapper retaining requests for position and draft diagnostics."""

    def __init__(self, provider, journal_path=None):
        self.provider = provider
        self.identity = provider.identity
        self.records = []
        self.lock = threading.Lock()
        self.journal_path = Path(journal_path) if journal_path is not None else None
        if self.journal_path is not None:
            self.journal_path.parent.mkdir(parents=True, exist_ok=True)
        self._source_token_cache = {}
        self._source_token_lock = threading.Lock()

    def __getattr__(self, name):
        return getattr(self.provider, name)

    def budget_for(self, stage):
        return getattr(self.provider, "budget_for", lambda _: RequestBudget(1_500_000))(
            stage
        )

    @staticmethod
    def _source_text(stage, payload):
        if stage != "production_read":
            return ""
        data = payload.get("input", {})
        core = data.get("core")
        if not isinstance(core, list):
            return ""
        return "\n\n".join(
            unit.get("text", "".join(span["text"] for span in unit.get("spans", [])))
            for unit in core
        )

    def _record(self, record):
        with self.lock:
            if self.journal_path is not None:
                try:
                    with self.journal_path.open("a", encoding="utf-8") as stream:
                        stream.write(canonical(record) + "\n")
                        stream.flush()
                        os.fsync(stream.fileno())
                except Exception as exc:
                    # Observation must never discard a valid provider response.
                    record["journal_error"] = type(exc).__name__
            self.records.append(record)

    def _source_tokens(self, text):
        counter = getattr(self.provider, "source_token_count", None)
        if text is None or not callable(counter):
            return None, None
        with self._source_token_lock:
            if text in self._source_token_cache:
                return self._source_token_cache[text], None
            try:
                count = counter(text)
                if type(count) is not int or count < 0:
                    raise ValueError(
                        "provider source_token_count must return a nonnegative integer"
                    )
            except Exception as exc:
                return None, type(exc).__name__
            self._source_token_cache[text] = count
            return count, None

    def _output_allowance(self, stage, budget):
        method = getattr(self.provider, "output_limit_for", None)
        if callable(method):
            try:
                limit = method(stage)
                if limit is not None and (type(limit) is not int or limit < 1):
                    raise ValueError(
                        "provider output_limit_for must return a positive integer or None"
                    )
                if limit is not None:
                    return limit, None
            except Exception as exc:
                error = type(exc).__name__
            else:
                error = None
        else:
            error = None
        return (budget.output_tokens or None), error

    def _usage(self):
        try:
            usage = getattr(self.provider, "last_usage", lambda: {})()
            if not isinstance(usage, dict):
                raise TypeError("provider last_usage must return a dictionary")
            return usage, None
        except Exception as exc:
            return {}, type(exc).__name__

    def call(self, stage, payload):
        budget = self.budget_for(stage)
        measurement = asdict(budget.measure(payload))
        output_allowance, output_allowance_error = self._output_allowance(stage, budget)
        started = time.monotonic()
        try:
            output = self.provider.call(stage, payload)
        except Exception as exc:
            wall_ms = (time.monotonic() - started) * 1000
            usage, usage_error = self._usage()
            source_tokens, source_token_error = (
                self._source_tokens(self._source_text(stage, payload))
                if stage == "production_read"
                else (None, None)
            )
            record = {
                "stage": stage,
                "status": "failed",
                "error_type": type(exc).__name__,
                "payload": payload,
                "wall_ms": wall_ms,
                "measurement": measurement,
                "usage": usage,
                "source_tokens": source_tokens,
                "output_token_allowance": output_allowance,
            }
            if usage_error:
                record["usage_error"] = usage_error
            if source_token_error:
                record["source_token_error"] = source_token_error
            if output_allowance_error:
                record["output_allowance_error"] = output_allowance_error
            self._record(record)
            raise
        wall_ms = (time.monotonic() - started) * 1000
        usage, usage_error = self._usage()
        source_tokens, source_token_error = (
            self._source_tokens(self._source_text(stage, payload))
            if stage == "production_read"
            else (None, None)
        )
        record = {
            "stage": stage,
            "status": "completed",
            "payload": payload,
            "output": output,
            "wall_ms": wall_ms,
            "response_bytes": len(canonical(output).encode("utf-8")),
            "measurement": measurement,
            "usage": usage,
            "source_tokens": source_tokens,
            "output_token_allowance": output_allowance,
        }
        if usage_error:
            record["usage_error"] = usage_error
        if source_token_error:
            record["source_token_error"] = source_token_error
        if output_allowance_error:
            record["output_allowance_error"] = output_allowance_error
        self._record(record)
        return output


def _source_map(plan):
    sources = {row["id"]: row["filename"] for row in plan["sources"]}
    return {row["id"]: sources[row["source_id"]] for row in plan["units"]}


def _source_control(workspace, canaries):
    """Prove the declared lexical checks can match the ingested source itself."""
    sources = {row["id"]: row["filename"] for row in workspace.sources()}
    units = workspace.units("teaching")
    source_by_unit = {row["id"]: sources[row["source_id"]] for row in units}
    rows = []
    for row in units:
        text = row.get(
            "text", "".join(span.get("text", "") for span in row.get("spans", []))
        )
        rows.append(
            {
                "id": row["id"],
                "text": text,
                "evidence": [{"unit_id": row["id"], "quote": text}],
            }
        )
    return score_canaries(canaries, rows, source_by_unit)


def _evaluation_identity(paths, canaries, brief, options):
    """Private task identity; source text is represented only by content hashes."""
    return {
        "sources": [
            {
                "filename": path.name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for path in paths
        ],
        "brief": brief,
        "canaries": [asdict(row) for row in canaries],
        "options": options,
    }


def _idea_rows(ideas):
    return [
        {
            "id": row["id"],
            "text": row["title"] + "\n" + row["explanation"],
            "evidence": row["evidence"],
        }
        for row in ideas
    ]


def _body_rows(rows):
    return [
        {"id": row["id"], "text": row["body"], "evidence": row.get("evidence", [])}
        for row in rows
    ]


def _writer_units(data):
    """Reconstruct private validator units from writer-addressed request text."""
    units = {}
    marker = re.compile(r"\[(s\d+)\]")
    for key in (
        "assigned_units",
        "earlier_evidence_units",
        "shared_evidence_units",
    ):
        for row in data.get(key, []):
            if row["id"] in units:
                continue
            addressed = row.get("addressed_text")
            matches = list(marker.finditer(addressed or ""))
            if not matches or len({match.group(1) for match in matches}) != len(
                matches
            ):
                continue
            text_parts, spans, offset = [], [], 0
            for position, match in enumerate(matches):
                end = (
                    matches[position + 1].start()
                    if position + 1 < len(matches)
                    else len(addressed)
                )
                part = addressed[match.end() : end]
                text_parts.append(part)
                spans.append(
                    {"id": match.group(1), "start": offset, "end": offset + len(part)}
                )
                offset += len(part)
            units[row["id"]] = {
                **row,
                "text": "".join(text_parts),
                "spans": spans,
            }
    return units


def _draft_body(output, data):
    """Materialize raw marked writer output for pre-review quality scoring."""
    if "body_marked" not in output and "candidate_body_marked" not in output:
        return output.get("body", ""), output.get("evidence", [])
    try:
        from .writer_markers import materialize_marked_body

        units = _writer_units(data)
        if "body_marked" in output:
            marked = materialize_marked_body(output["body_marked"], units)
            return marked["body"], marked["evidence"]
        candidate = materialize_marked_body(
            output["candidate_body_marked"], units, body_field="candidate_body"
        )
        marking = materialize_marked_body(
            output["marking_body_marked"], units, body_field="marking_body"
        )
        evidence, seen = [], set()
        for row in candidate["evidence"] + marking["evidence"]:
            key = (row["unit_id"], row["quote"])
            if key not in seen:
                evidence.append(row)
                seen.add(key)
        return candidate["body"] + "\n" + marking["body"], evidence
    except (KeyError, TypeError, ValueError):
        return "", []


def _draft_score(records, canaries):
    # Latest writing attempt per section. Canonical local aliases are namespaced
    # by request before scoring, because unit:0 can name different source units.
    latest = {}
    for index, record in enumerate(records):
        if record["stage"] == "production_write" and record["status"] == "completed":
            latest[record["payload"]["input"]["section"]["id"]] = (index, record)
    rows, sources = [], {}
    for index, record in latest.values():
        data, output = record["payload"]["input"], record["output"]
        body, evidence = _draft_body(output, data)
        names = {source["id"]: source["filename"] for source in data["factual_sources"]}
        for key in (
            "assigned_units",
            "earlier_evidence_units",
            "shared_evidence_units",
        ):
            for unit in data.get(key, []):
                sources[f"{index}:{unit['id']}"] = names[unit["source_id"]]
        rows.append(
            {
                "id": str(index),
                "text": body,
                "evidence": [
                    {**item, "unit_id": f"{index}:{item['unit_id']}"}
                    for item in evidence
                ],
            }
        )
    return score_canaries(canaries, rows, sources)


def _call_details(records, canaries):
    out = []
    for record in records:
        row = {
            key: value
            for key, value in record.items()
            if key not in {"payload", "output"}
        }
        usage = record.get("usage", {})
        prompt_tokens = usage.get("input_tokens")
        output_tokens = usage.get("output_tokens")
        output_allowance = record.get("output_token_allowance")
        row["prompt_tokens"] = (
            prompt_tokens if type(prompt_tokens) is int and prompt_tokens >= 0 else None
        )
        row["output_token_fraction"] = (
            output_tokens / output_allowance
            if type(output_tokens) is int
            and output_tokens >= 0
            and type(output_allowance) is int
            and output_allowance > 0
            else None
        )
        if "payload" in record:
            data = record["payload"]["input"]
            core_text = (
                ObservedProvider._source_text(record["stage"], record["payload"])
                if "core" in data
                else ""
            )
            row["source_characters"] = (
                len(core_text)
                if record["stage"] == "production_read" and "core" in data
                else None
            )
            source_tokens = record.get("source_tokens")
            row["source_to_prompt_fraction"] = (
                source_tokens / prompt_tokens
                if type(source_tokens) is int
                and type(prompt_tokens) is int
                and prompt_tokens > 0
                else None
            )
            ideas = (
                record.get("output", {}).get("ideas")
                if record["stage"] == "production_read"
                and record["status"] == "completed"
                else None
            )
            row["read_idea_count"] = len(ideas) if isinstance(ideas, list) else None
            row["read_ideas_per_1000_source_tokens"] = (
                1000 * len(ideas) / source_tokens
                if isinstance(ideas, list)
                and type(source_tokens) is int
                and source_tokens > 0
                else None
            )
            row["canary_source_positions"] = {
                fact.id: core_text.find(fact.subject) / max(1, len(core_text))
                for fact in canaries
                if fact.subject in core_text
                and data.get("source", {}).get("filename") == fact.source
            }
        out.append(row)
    return out


def run_trial(provider, folder, *, load, reading, complete, options=None, corpus=None):
    """Run original sources through production prompts, validation and scheduling.

    A new workspace per trial avoids cache hits masquerading as independent
    samples. The caller owns the adapter and closes it after all trials.
    """
    folder = Path(folder)
    if (folder / "workspace" / "workspace.sqlite3").exists():
        raise ValueError("each quality trial needs a fresh workspace")
    folder.mkdir(parents=True, exist_ok=True)
    paths, canaries = (
        make_corpus(folder / "sources", load) if corpus is None else corpus[:2]
    )
    workspace = Workspace(folder / "workspace")
    ingest_paths(paths, workspace, "teaching")
    source_ids = [row["id"] for row in workspace.sources()]
    observed = ObservedProvider(provider, folder / "calls.jsonl")
    opts = {
        **(options or {}),
        "workflow": "planned",
        "reading": reading,
        "format": "document",
    }
    brief = (
        corpus[2]
        if corpus is not None
        else (
            "Prepare an exhaustive reference for the fictional equipment specifications. "
            "Preserve every supported statement, qualification, negation, quantity, table association and historical restriction. "
            "Keep distinct equipment contexts separate."
        )
    )
    evaluation_identity = _evaluation_identity(paths, canaries, brief, opts)
    started = time.monotonic()
    result = {
        "load": load if corpus is None else len(workspace.units("teaching")),
        "load_unit": "background paragraphs" if corpus is None else "source units",
        "reading": reading,
        "provider_identity": provider.identity,
        "protocol_revision": REVISION,
        "corpus_sha256": hashlib.sha256(
            b"".join(path.name.encode() + b"\0" + path.read_bytes() for path in paths)
        ).hexdigest(),
        "canaries": [asdict(row) for row in canaries],
        "options": opts,
        "source_bytes": sum(path.stat().st_size for path in paths),
        "evaluation_identity": evaluation_identity,
        "evaluation_sha256": hashlib.sha256(
            canonical(evaluation_identity).encode("utf-8")
        ).hexdigest(),
    }
    plan = None
    try:
        result["source_control"] = _source_control(workspace, canaries)
        failed_controls = [
            row
            for row in result["source_control"]["checks"]
            if row["status"] != "preserved"
        ]
        if failed_controls:
            failures = ", ".join(
                f"{row['id']}={row['status']}" for row in failed_controls
            )
            raise ValueError(
                f"source control failed under {ORACLE_VERSION}: {failures}; "
                "revise the canary phrases or source selection before model calls"
            )
        plan = plan_production(workspace, observed, brief, source_ids, opts)
        source_by_unit = _source_map(plan)
        result["extraction"] = score_canaries(
            canaries, _idea_rows(plan["ideas"]), source_by_unit
        )
        assigned = {
            iid for section in plan["route"]["sections"] for iid in section["idea_ids"]
        }
        result["assignment"] = score_canaries(
            canaries,
            _idea_rows([row for row in plan["ideas"] if row["id"] in assigned]),
            source_by_unit,
        )
        result["planning_metrics"] = plan["metrics"]
        result["idea_count"] = len(plan["ideas"])
        result["planning_strategy"] = plan["planning"]
        if complete:
            receipt = run_production(workspace, observed, plan)
            result["initial_draft"] = _draft_score(observed.records, canaries)
            result["review_observations"] = [
                {
                    "stage": row["stage"],
                    "finding_count": len(row["output"].get("findings", [])),
                }
                for row in observed.records
                if row["stage"] == "production_review" and row["status"] == "completed"
            ]
            result["finished_output"] = score_canaries(
                canaries, _body_rows(receipt["sections"]), source_by_unit
            )
            result["engine_status"] = receipt["status"]
            result["production_metrics"] = receipt["metrics"]
            result["citation_coverage"] = receipt["coverage"]
            (folder / "output.md").write_text(receipt["markdown"], encoding="utf-8")
        result["status"] = "completed"
        (folder / "plan.json").write_text(canonical(plan), encoding="utf-8")
    except Exception as exc:
        result.update(
            status="failed",
            error_type=type(exc).__name__,
            error=str(exc),
            failure_metrics=getattr(exc, "metrics", {}),
        )
    result["calls"] = _call_details(observed.records, canaries)
    result["usage"] = {
        name: sum(row.get("usage", {}).get(name, 0) for row in observed.records)
        for name in (
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "cached_input_tokens",
            "reasoning_tokens",
            "thinking_tokens",
        )
        if any(name in row.get("usage", {}) for row in observed.records)
    }
    result["read_ideas_per_1000_input_tokens"] = (
        1000
        * result.get("idea_count", 0)
        / sum(
            row.get("usage", {}).get("input_tokens", 0)
            for row in observed.records
            if row["stage"] == "production_read"
        )
        if sum(
            row.get("usage", {}).get("input_tokens", 0)
            for row in observed.records
            if row["stage"] == "production_read"
        )
        else None
    )
    result["wall_ms"] = (time.monotonic() - started) * 1000
    result["read_source_token_exposure"] = (
        sum(
            row.get("source_tokens") or 0
            for row in result["calls"]
            if row["stage"] == "production_read"
        )
        or None
    )
    corpus_text = "\n\n".join(unit["text"] for unit in workspace.units("teaching"))
    corpus_tokens, corpus_count_error = observed._source_tokens(corpus_text)
    result["corpus_tokens"] = corpus_tokens
    result["corpus_token_count_error"] = corpus_count_error
    result["ideas_per_1000_source_tokens"] = (
        1000 * result["idea_count"] / corpus_tokens
        if corpus_tokens and "idea_count" in result
        else None
    )
    result["stage_budgets"] = {}
    for stage in sorted({row["stage"] for row in observed.records}):
        budget = observed.budget_for(stage)
        result["stage_budgets"][stage] = {
            "configuration_identity": getattr(
                provider,
                "configuration_identity_for",
                lambda _: getattr(
                    provider, "configuration_identity", provider.identity
                ),
            )(stage),
            "context_tokens": budget.context_tokens,
            "output_tokens": budget.output_tokens,
            "max_request_bytes": budget.max_request_bytes,
            "counting": budget.counting,
            "workload": (
                asdict(budget.workload) if getattr(budget, "workload", None) else None
            ),
        }
    (folder / "trial.json").write_text(canonical(result), encoding="utf-8")
    return result


def summarize(trials, *, minimum_fraction, maximum_counterfacts, required_stages):
    """Apply caller-supplied criteria to every replicate and every position.

    The largest observed passing load is a sampled result, with no interpolation
    or claim that all smaller or unseen inputs will pass.
    """
    if (
        not 0 <= minimum_fraction <= 1
        or type(maximum_counterfacts) is not int
        or maximum_counterfacts < 0
    ):
        raise ValueError("invalid explicit acceptance criteria")
    if not trials:
        raise ValueError("at least one observed trial is required")
    if not required_stages or set(required_stages) - {
        "extraction",
        "assignment",
        "initial_draft",
        "finished_output",
    }:
        raise ValueError("required_stages must select known measured outputs")
    groups = defaultdict(list)
    for trial in trials:
        groups[(trial["provider_identity"], trial["reading"], trial["load"])].append(
            trial
        )
    rows = []
    for (provider, reading, load), members in sorted(groups.items()):
        passed = all(
            trial["status"] == "completed"
            and all(
                stage in trial
                and trial[stage]["fraction"] is not None
                and trial[stage]["fraction"] >= minimum_fraction
                and trial[stage]["counterfacts"] <= maximum_counterfacts
                and all(
                    position["preserved"] / position["total"] >= minimum_fraction
                    for position in trial[stage]["by_position"].values()
                )
                for stage in required_stages
            )
            for trial in members
        )
        rows.append(
            {
                "provider_identity": provider,
                "reading": reading,
                "load": load,
                "replicates": len(members),
                "passed_all_observed_checks": passed,
            }
        )
    maxima = {}
    for row in rows:
        if row["passed_all_observed_checks"]:
            key = row["provider_identity"] + ":" + row["reading"]
            maxima[key] = max(maxima.get(key, 0), row["load"])
    return {
        "criteria": {
            "minimum_fraction_per_stage_and_position": minimum_fraction,
            "maximum_counterfacts_per_stage": maximum_counterfacts,
            "required_stages": list(required_stages),
        },
        "observations": rows,
        "largest_sampled_passing_load": maxima,
        "interpretation": "Observed lexical canary checks only. No fitted knee, confidence bound, unseen-corpus recall certificate or automatic profile promotion.",
    }
