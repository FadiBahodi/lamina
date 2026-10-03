"""The sweep route: read in parallel, deduplicate locally, audit a sample, publish cards.

This is the depth-two geometry the engine grew out of. Every reader window is
one independent call whose output is finished cards. No planner, no writer, no
per-section review chain. Duplicates are suppressed with local similarity (no
model calls). A fraction of windows receives one source-centred audit call that
looks for omissions and unsupported cards; its findings are attached, never
gating. A failed window loses its cards and is reported; the run never dies.

Models decide what a card tests and how to phrase it. Code owns window
boundaries, citations, duplicate accounting, sampling, and the receipt.
"""

from __future__ import annotations

import hashlib
import time

from .execution import bounded_collect
from .production_contract import (
    ProductionError,
    ProductionValidationError,
    _evidence,
    _str,
    validated,
)
from .similarity import DEFAULT_THRESHOLDS, suppress_duplicates, vectors_for
from .source_reading import reader_input, request_budget
from .call_runtime import make_envelope

AUDIT_STAGE = "sweep_audit"

CARD_INSTRUCTION = (
    "Read the owned source structures completely and write flashcards from them. "
    "Each returned idea is one card: title is the prompt, either a direct question or a "
    "cloze sentence that hides the tested term as {{c1::hidden text}}; explanation is the "
    "answer with its conditions, numbers, units and exceptions. Cover every distinct testable "
    "fact, distinction, threshold, exception, mechanism and procedure relevant to the brief. "
    "Prefer many precise cards over few broad ones; do not merge distinct facts into one card. "
    "Each card must originate in and cite owned core units. Also cite every visible neighbouring "
    "passage used to establish its meaning or conditions; that is support, not ownership. "
    "Respect source policies: historical claims remain historical; supplements do not silently "
    "override authority. "
)

AUDIT_INSTRUCTION = (
    "Audit the cards written from this source window against the visible source text. "
    "Report two kinds of finding. omission: a distinct testable fact, number, exception, "
    "distinction or procedure in the owned core text that no card tests. unsupported: a card "
    "whose prompt or answer states something the visible text does not support, misstates a "
    "number or condition, or attaches a fact to the wrong population or context. For each "
    "finding cite exact visible source text. Do not report wording or style preferences. "
    'Return {"findings": []} when the cards cover the core and every card is supported. '
)

AUDIT_SHAPE = {
    "findings": [
        {
            "kind": "omission|unsupported",
            "issue": "concrete missing fact or concrete unsupported statement",
            "card_ids": ["affected card id, or empty for an omission"],
            "evidence": [{"unit_id": "visible unit ID", "quote": "exact source substring"}],
        }
    ]
}


def sampled(window_id: str, rate: float) -> bool:
    """Deterministic sample so a restart audits the same windows and reuses the cache."""
    if rate <= 0:
        return False
    if rate >= 1:
        return True
    value = int(hashlib.sha256(window_id.encode("utf-8")).hexdigest()[:8], 16)
    return value / 0xFFFFFFFF < rate


def _card_text(idea: dict) -> str:
    return " ".join([idea["title"], idea["explanation"]])


def deduplicate(provider, ideas: list[dict], threshold) -> tuple[list[dict], dict, dict]:
    """Return ``(kept, suppressed, report)``. Suppression compares each card only
    with cards already kept, in source order, so chains cannot merge."""
    if not ideas:
        return [], {}, {"method": None, "threshold": None, "suppressed": 0}
    method, vectors = vectors_for(provider, [_card_text(idea) for idea in ideas])
    threshold = (
        DEFAULT_THRESHOLDS["duplicate"][method] if threshold is None else threshold
    )
    kept_indexes, suppressed_rows = suppress_duplicates(vectors, threshold)
    suppressed = {
        ideas[index]["id"]: {
            "duplicate_of": ideas[row["duplicate_of"]]["id"],
            "score": row["score"],
        }
        for index, row in suppressed_rows.items()
    }
    return (
        [ideas[index] for index in kept_indexes],
        suppressed,
        {
            "method": method,
            "threshold": threshold,
            "suppressed": len(suppressed),
            "scope": "Near-duplicate suppression by local similarity; a kept card may still overlap a distinct one.",
        },
    )


def audit_windows(workspace, provider, task, options, sources, windows, units, ideas, tracker):
    """One source-centred audit call per sampled window. Findings are advisory."""
    rate = options["audit_rate"]
    unit_map = {u["id"]: u for u in units}
    source_map = {s["id"]: s for s in sources}
    cards_by_window = {}
    for idea in ideas:
        cards_by_window.setdefault(idea["id"].split(":", 1)[0], []).append(idea)
    selected = [w for w in windows if sampled(w["id"], rate)]
    budget = request_budget(provider, AUDIT_STAGE, options)

    def audit(window):
        core = [unit_map[uid] for uid in window["core"]]
        before = [unit_map[uid] for uid in window["before"]]
        after = [unit_map[uid] for uid in window["after"]]
        view = {**window, "core": core, "before": before, "after": after}
        data, aliases = reader_input(view, source_map[window["source_id"]], task, options)
        data = {k: v for k, v in data.items() if k not in ("reading", "ownership")}
        reverse = {alias: uid for uid, alias in (aliases or {}).items()}
        forward = aliases or {}
        cards = cards_by_window.get(window["id"], [])
        data["cards"] = [
            {
                "id": idea["id"],
                "prompt": idea["title"],
                "answer": idea["explanation"],
                "cites": [forward.get(uid, uid) for uid in idea["unit_ids"]],
            }
            for idea in cards
        ]
        data["scope"] = (
            "Cards for this window only. Cards from neighbouring windows cover the "
            "before/after context; audit only the owned core text."
        )
        visible = {
            forward.get(u["id"], u["id"]): u for u in before + core + after
        }
        known = {idea["id"] for idea in cards}

        def check(raw):
            rows = raw.get("findings") if isinstance(raw, dict) else None
            if not isinstance(rows, list):
                raise ProductionValidationError("audit must return a findings list")
            findings = []
            for row in rows:
                if not isinstance(row, dict) or row.get("kind") not in {
                    "omission",
                    "unsupported",
                }:
                    raise ProductionValidationError(
                        "each audit finding needs kind omission or unsupported"
                    )
                card_ids = row.get("card_ids", [])
                if not isinstance(card_ids, list) or any(
                    not isinstance(c, str) or c not in known for c in card_ids
                ):
                    raise ProductionValidationError(
                        "audit card_ids must name cards from this window"
                    )
                evidence = _evidence(row.get("evidence"), visible, "audit")
                findings.append(
                    {
                        "kind": row["kind"],
                        "issue": _str(row.get("issue"), "audit.issue", 4000),
                        "card_ids": card_ids,
                        "evidence": [
                            {**e, "unit_id": reverse.get(e["unit_id"], e["unit_id"])}
                            for e in evidence
                        ],
                    }
                )
            return {"findings": findings}

        envelope = make_envelope(
            AUDIT_STAGE, AUDIT_INSTRUCTION, AUDIT_SHAPE, data, workload_items=len(cards)
        )
        result = tracker.call(
            workspace,
            provider,
            AUDIT_STAGE,
            window["id"],
            AUDIT_INSTRUCTION,
            AUDIT_SHAPE,
            data,
            lambda raw: validated(check, raw),
            budget.max_request_bytes,
            workload_items=envelope["workload_items"],
        )
        return {"window_id": window["id"], **result}

    outcomes = bounded_collect(
        audit, selected, min(options["workers"], options["review_workers"])
    )
    return {
        "rate": rate,
        "sampled_windows": [w["id"] for w in selected],
        "audited": [row.value for row in outcomes if row.ok],
        "failed": [
            {"window_id": selected[row.index]["id"], "error": str(row.error)}
            for row in outcomes
            if not row.ok
        ],
        "scope": "A sampled, source-centred model audit. Findings are advisory and never remove cards.",
    }


def card_sections(windows: list[dict], ideas: list[dict], units: list[dict]) -> list[dict]:
    """One output section per reader window, in source order, owning its kept cards."""
    unit_map = {u["id"]: u for u in units}
    by_window = {}
    for idea in ideas:
        by_window.setdefault(idea["id"].split(":", 1)[0], []).append(idea["id"])
    sections = []
    for window in windows:
        owned = by_window.get(window["id"], [])
        if not owned:
            continue
        first = unit_map[window["core"][0]]
        headings = list(
            dict.fromkeys(unit_map[uid]["heading"] for uid in window["core"])
        )
        sections.append(
            {
                "id": "section_" + window["id"].removeprefix("window_"),
                "title": " / ".join(h for h in headings if h) or first["locator"],
                "purpose": f"Cards from {first['locator']}",
                "idea_ids": owned,
                "context_section_ids": [],
                "candidate_context_ids": [],
                "representation": {
                    "kind": "cards",
                    "rationale": "Flashcards written directly by the reader.",
                    "requirements": [],
                },
            }
        )
    return sections


def render_cards(ideas: list[dict], units: list[dict]) -> str:
    unit_map = {u["id"]: u for u in units}
    lines = []
    for idea in ideas:
        locator = unit_map[idea["unit_ids"][0]]["locator"]
        lines.append(f"**Q:** {idea['title']}  ")
        lines.append(f"**A:** {idea['explanation']}  ")
        lines.append(f"<sub>{locator}</sub>")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def authored_sections(plan: dict) -> list[dict]:
    """Deterministic section objects for the sweep route; no model calls."""
    ideas = {idea["id"]: idea for idea in plan["ideas"]}
    sections = []
    for section in plan["route"]["sections"]:
        owned = [ideas[iid] for iid in section["idea_ids"]]
        evidence = list(
            {(e["unit_id"], e["quote"]): e for idea in owned for e in idea["evidence"]}.values()
        )
        sections.append(
            {
                "id": section["id"],
                "title": section["title"],
                "body": render_cards(owned, plan["units"]),
                "used_idea_ids": [idea["id"] for idea in owned],
                "evidence": evidence,
                "claims": [
                    {
                        "text": idea["title"],
                        "answer": idea["explanation"],
                        "evidence": idea["evidence"],
                    }
                    for idea in owned
                ],
            }
        )
    return sections


def card_rows(plan: dict) -> list[dict]:
    """Flat card list for TSV/JSON export: prompt, answer, source, citations."""
    unit_map = {u["id"]: u for u in plan["units"]}
    source_map = {s["id"]: s for s in plan["sources"]}
    suppressed = set((plan.get("duplicates") or {}).keys())
    rows = []
    for section in plan["route"]["sections"]:
        for iid in section["idea_ids"]:
            idea = next(i for i in plan["ideas"] if i["id"] == iid)
            if iid in suppressed:
                continue
            first = unit_map[idea["unit_ids"][0]]
            rows.append(
                {
                    "id": idea["id"],
                    "prompt": idea["title"],
                    "answer": idea["explanation"],
                    "kind": "cloze" if "{{c1::" in idea["title"] else "basic",
                    "source": source_map[first["source_id"]]["title"],
                    "locator": first["locator"],
                    "heading": first["heading"],
                    "unit_ids": idea["unit_ids"],
                    "support_unit_ids": idea.get("support_unit_ids", []),
                    "quotes": [e["quote"] for e in idea["evidence"]],
                }
            )
    return rows


def cards_tsv(rows: list[dict]) -> str:
    """Anki-importable TSV: prompt, answer, tags. Tabs and newlines in fields
    become spaces/<br>, which Anki renders."""

    def field(text: str) -> str:
        return text.replace("\t", " ").replace("\r", "").replace("\n", "<br>")

    def tag(text: str) -> str:
        return "".join(c if c.isalnum() else "_" for c in text.strip())[:60] or "lamina"

    lines = []
    for row in rows:
        tags = " ".join(dict.fromkeys([tag(row["source"]), tag(row["heading"] or "")]))
        lines.append("\t".join([field(row["prompt"]), field(row["answer"]), tags]))
    return "\n".join(lines) + ("\n" if lines else "")


def plan_sweep(workspace, provider, task, opts, selection, sources, units, tracker, progress=None):
    """Read, deduplicate and audit; return the plan fields the sweep route needs."""
    from .source_reading import read_sources

    started = time.monotonic()
    windows, ideas, unresolved = read_sources(
        workspace, provider, task, opts, sources, units, tracker, None
    )
    if not ideas:
        raise ProductionError("Readers found no anchored cards in the selected sources")
    read_ms = round((time.monotonic() - started) * 1000, 3)
    kept, suppressed, dedup_report = deduplicate(provider, ideas, opts["dedup_threshold"])
    audit = audit_windows(
        workspace, provider, task, opts, sources, windows, units, kept, tracker
    )
    sections = card_sections(windows, kept, units)
    route = {
        "title": task["goal"][:100],
        "summary": task["goal"][:3000],
        "sections": sections,
        "omitted": [
            {"idea_id": iid, "reason": f"duplicate of {row['duplicate_of']}"}
            for iid, row in suppressed.items()
        ],
        "shared_context": [],
    }
    return {
        "windows": windows,
        "ideas": ideas,
        "duplicates": suppressed,
        "route": route,
        "planning": {
            "routing": {"mode": "sweep"},
            "unresolved_reads": unresolved,
            "dedup": dedup_report,
            "audit": audit,
            "timing": {"read_ms": read_ms},
        },
    }
