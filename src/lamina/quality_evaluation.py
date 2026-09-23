"""Observed canary survival through the real production path.

The oracle matches explicit phrases in authored statements and source quotes.
It detects known omissions and counterfacts; it does not certify semantic recall.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
import hashlib
from pathlib import Path
import re
import threading
import time

from .context_budget import RequestBudget
from .ingest import ingest_paths
from .production import plan_production, run_production
from .production_contract import REVISION
from .store import Workspace, canonical

ORACLE_VERSION = "local-qualified-phrase-and-source-2"


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
    for statement in re.split(r"(?<=[.!?])\s+|\n+", text):
        statement = normalized(statement)
        mentions = list(pattern.finditer(statement))
        cuts = [0, *(match.start() for match in mentions[1:]), len(statement)]
        for start, end in zip(cuts, cuts[1:]):
            if fragment := statement[start:end].strip():
                yield fragment


def score_canaries(canaries, rows, source_by_unit):
    """Match a local statement with locally supporting, correct-source evidence.

    Required phrases must occur together within one sentence or Markdown line,
    without borrowing values from a neighboring named subject. Citation text
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
                    else "required_phrase_missing" if relevant else "absent"
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

    def __init__(self, provider):
        self.provider = provider
        self.identity = provider.identity
        self.records = []
        self.lock = threading.Lock()

    def __getattr__(self, name):
        return getattr(self.provider, name)

    def budget_for(self, stage):
        return getattr(self.provider, "budget_for", lambda _: RequestBudget(1_500_000))(
            stage
        )

    def call(self, stage, payload):
        started = time.monotonic()
        try:
            output = self.provider.call(stage, payload)
        except Exception as exc:
            with self.lock:
                self.records.append(
                    {
                        "stage": stage,
                        "status": "failed",
                        "error_type": type(exc).__name__,
                    }
                )
            raise
        record = {
            "stage": stage,
            "status": "completed",
            "payload": payload,
            "output": output,
            "wall_ms": (time.monotonic() - started) * 1000,
            "response_bytes": len(canonical(output).encode("utf-8")),
            "measurement": asdict(self.budget_for(stage).measure(payload)),
            "usage": getattr(self.provider, "last_usage", lambda: {})(),
        }
        with self.lock:
            self.records.append(record)
        return output


def _source_map(plan):
    sources = {row["id"]: row["filename"] for row in plan["sources"]}
    return {row["id"]: sources[row["source_id"]] for row in plan["units"]}


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
                "text": output.get("body", ""),
                "evidence": [
                    {**item, "unit_id": f"{index}:{item['unit_id']}"}
                    for item in output.get("evidence", [])
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
        if record["status"] == "completed":
            data = record["payload"]["input"]
            core_text = "\n\n".join(unit["text"] for unit in data.get("core", []))
            row["source_characters"] = len(core_text) if "core" in data else None
            row["canary_source_positions"] = {
                fact.id: core_text.find(fact.subject) / max(1, len(core_text))
                for fact in canaries
                if fact.subject in core_text
                and data.get("source", {}).get("filename") == fact.source
            }
        out.append(row)
    return out


def run_trial(provider, folder, *, load, reading, complete, options=None):
    """Run original sources through production prompts, validation and scheduling.

    A new workspace per trial avoids cache hits masquerading as independent
    samples. The caller owns the adapter and closes it after all trials.
    """
    folder = Path(folder)
    if (folder / "workspace" / "workspace.sqlite3").exists():
        raise ValueError("each quality trial needs a fresh workspace")
    paths, canaries = make_corpus(folder / "sources", load)
    workspace = Workspace(folder / "workspace")
    ingest_paths(paths, workspace, "teaching")
    source_ids = [row["id"] for row in workspace.sources()]
    observed = ObservedProvider(provider)
    opts = {
        **(options or {}),
        "workflow": "planned",
        "reading": reading,
        "format": "document",
    }
    brief = (
        "Prepare an exhaustive reference for the fictional equipment specifications. "
        "Preserve every supported statement, qualification, negation, quantity, table association and historical restriction. "
        "Keep distinct equipment contexts separate."
    )
    started = time.monotonic()
    result = {
        "load": load,
        "load_unit": "background paragraphs",
        "reading": reading,
        "provider_identity": provider.identity,
        "protocol_revision": REVISION,
        "corpus_sha256": hashlib.sha256(
            b"".join(path.name.encode() + b"\0" + path.read_bytes() for path in paths)
        ).hexdigest(),
        "canaries": [asdict(row) for row in canaries],
        "options": opts,
        "source_bytes": sum(path.stat().st_size for path in paths),
    }
    plan = None
    try:
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
    result["wall_ms"] = (time.monotonic() - started) * 1000
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
