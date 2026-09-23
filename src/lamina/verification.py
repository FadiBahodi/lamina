"""Output-to-source links and coverage accounting, without semantic inference.

A source quote can be exact while the attached claim is false. These checks
establish where a claim appears and what source was cited. The reviewer judges
whether the evidence supports it, including conditions and contradictions.
"""

from __future__ import annotations

from .evidence import QuoteMatchError, resolve_quote


class VerificationError(ValueError):
    """An output-to-source link cannot be resolved exactly."""


CLAIM_SHAPE = {
    "id": "unique claim id within this section",
    "text": "exact, contiguous text from the finished body",
    "body_field": "body, candidate_body, or marking_body",
    "evidence": [{"unit_id": "source unit id", "quote": "exact source substring"}],
}


def validate_claims(raw, bodies: dict[str, str], units: dict[str, dict]) -> list[dict]:
    """Check supplied claim links; omission remains visible as an empty list.

    No sentence splitter decides what constitutes a factual claim. A writer can
    link a sentence, a table cell, or a longer qualified statement. A model review
    must check for material claims that were never linked.
    """
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise VerificationError("claims must be a list")
    found = set()
    out = []
    for claim in raw:
        if not isinstance(claim, dict):
            raise VerificationError("each claim must be an object")
        cid, text = claim.get("id"), claim.get("text")
        field = claim.get("body_field", "body")
        if not isinstance(cid, str) or not cid.strip() or cid in found:
            raise VerificationError("claim IDs must be nonempty and unique")
        if not isinstance(field, str) or field not in bodies:
            raise VerificationError("claim body_field must name a supplied output body")
        if not isinstance(text, str) or not text.strip() or text not in bodies[field]:
            raise VerificationError(
                "claim text must be an exact substring of its output body"
            )
        evidence = claim.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise VerificationError("each claim needs source evidence")
        checked, seen = [], set()
        for row in evidence:
            if not isinstance(row, dict) or set(row) != {"unit_id", "quote"}:
                raise VerificationError("claim evidence needs unit_id and quote")
            uid, quote = row["unit_id"], row["quote"]
            if not isinstance(uid, str) or uid not in units:
                raise VerificationError(
                    "claim evidence names an unavailable source unit"
                )
            try:
                quote = resolve_quote(quote, units[uid]["text"]).quote
            except QuoteMatchError as exc:
                raise VerificationError(
                    "claim evidence must resolve to exact source text: " + str(exc)
                ) from exc
            if (uid, quote) not in seen:
                checked.append({"unit_id": uid, "quote": quote})
                seen.add((uid, quote))
        found.add(cid)
        out.append({"id": cid, "text": text, "body_field": field, "evidence": checked})
    return out


def coverage_report(plan: dict, authored: list[dict]) -> dict:
    """Report the different coverage boundaries with explicit missing IDs.

    Reading a unit, citing it in an idea, assigning it, citing it in the output,
    and expressing all relevant content are different events. Only the first four
    are counted here. Citation ratios are diagnostics, never semantic recall.
    """
    units = {u["id"] for u in plan["units"]}
    ideas = {idea["id"]: idea for idea in plan.get("ideas", [])}
    windows = plan.get("windows", [])
    considered = {
        unit["id"] if isinstance(unit, dict) else unit
        for window in windows
        for unit in window["core"]
    }
    reader_cited = {
        e["unit_id"] for idea in ideas.values() for e in idea.get("evidence", [])
    }
    assigned = {
        uid
        for section in plan["route"]["sections"]
        for uid in section.get(
            "unit_ids",
            [
                uid
                for iid in section.get("idea_ids", [])
                for uid in ideas[iid]["unit_ids"]
            ],
        )
    }
    writer_cited = {e["unit_id"] for row in authored for e in row.get("evidence", [])}
    claims = [claim for row in authored for claim in row.get("claims", [])]
    claim_cited = {e["unit_id"] for claim in claims for e in claim["evidence"]}
    omitted = {
        row["unit_id"]
        for section in authored
        for row in section.get("omitted_units", [])
    }
    route_omitted = set()
    for row in plan["route"].get("omitted", []):
        if "unit_id" in row:
            route_omitted.add(row["unit_id"])
        elif row.get("idea_id") in ideas:
            route_omitted.update(ideas[row["idea_id"]]["unit_ids"])
        elif "target_id" in row:
            for target in (plan.get("retrieval_targets") or {}).get("targets", []):
                if target["id"] == row["target_id"]:
                    for iid in target["member_idea_ids"]:
                        route_omitted.update(ideas[iid]["unit_ids"])
    workflow = plan.get("options", {}).get("workflow", "planned")
    planned = workflow == "planned"
    return {
        "selected_unit_count": len(units),
        "reading": {
            "applicable": planned,
            "considered_unit_ids": sorted(considered & units) if planned else [],
            "unconsidered_unit_ids": sorted(units - considered) if planned else [],
            "cited_unit_ids": sorted(reader_cited & units) if planned else [],
            "uncited_unit_ids": sorted(units - reader_cited) if planned else [],
        },
        "assignment": {
            "assigned_unit_ids": sorted(assigned & units),
            "explicitly_omitted_unit_ids": sorted(route_omitted & units),
            "unaccounted_unit_ids": sorted(units - assigned - route_omitted),
        },
        "output": {
            "cited_unit_ids": sorted(writer_cited & units),
            "assigned_without_citation_unit_ids": sorted(assigned - writer_cited),
            "writer_omitted_unit_ids": sorted(omitted & units),
            "mapped_claim_count": len(claims),
            "claim_cited_unit_ids": sorted(claim_cited & units),
            "sections_without_claim_maps": [
                row["id"] for row in authored if not row.get("claims")
            ],
        },
        "scope": "Exact source and output links; citation counts do not measure entailment or semantic completeness.",
    }


CONSISTENCY_SHAPE = {
    "findings": [
        {
            "section_ids": ["affected section id from the supplied pair"],
            "issue": "concrete contradiction, unnecessary repetition, broken reference or answer leakage",
            "repair_instruction": "specific correction preserving supported distinctions",
            "evidence": [
                {
                    "unit_id": "supplied source unit id",
                    "quote": "exact source substring",
                }
            ],
        }
    ]
}
CONSISTENCY_INSTRUCTION = (
    "Check the relationship between the two completed sections supplied here. "
    "Look for contradictory values or conditions, an unexplained change of meaning, "
    "unnecessary repetition, broken references, and examiner content leaking into candidate text. "
    "Preserve source disagreements explicitly when the sources themselves conflict; "
    "do not resolve them by inventing consensus. Distinguish historical, authoritative and "
    "supplemental sources. Each finding must identify affected supplied section IDs and an "
    "actionable correction. This pass checks their relationship, not prose taste. "
    "The supplied source quotations support citations; a clear result covers only this pair."
)


def _document_pairs(plan, include_adjacency=False):
    """Explicit relationships, plus ordered neighbors when requested."""
    sections = plan["route"]["sections"]
    order = {section["id"]: index for index, section in enumerate(sections)}
    pairs = {}

    def add(first, second, reason):
        if first == second or first not in order or second not in order:
            return
        key = tuple(sorted((first, second), key=order.get))
        pairs.setdefault(key, set()).add(reason)

    if include_adjacency:
        for previous, following in zip(sections, sections[1:]):
            add(previous["id"], following["id"], "consecutive sections")
    for section in sections:
        for predecessor in section.get("context_section_ids", []):
            add(predecessor, section["id"], "declared source context")
        for predecessor in section.get("candidate_context_ids", []):
            add(predecessor, section["id"], "declared candidate prerequisite")
    ideas = {idea["id"]: idea for idea in plan.get("ideas", [])}
    ownership = {}
    for section in sections:
        assigned = section.get("unit_ids")
        if assigned is None:
            assigned = {
                uid
                for iid in section.get("idea_ids", [])
                for uid in ideas[iid]["unit_ids"]
            }
        for uid in assigned:
            ownership.setdefault(uid, set()).add(section["id"])
    for index, shared in enumerate(plan["route"].get("shared_context", [])):
        declared = shared.get("section_ids")
        owners = sorted(
            (
                declared
                if declared is not None
                else {
                    sid
                    for e in shared["evidence"]
                    for sid in ownership.get(e["unit_id"], [])
                }
            ),
            key=order.get,
        )
        for position, first in enumerate(owners):
            for second in owners[position + 1 :]:
                add(first, second, f"shared source relationship {index + 1}")
    return [(pair, sorted(reasons)) for pair, reasons in pairs.items()]


def _consistency_check(raw, pair, units):
    if not isinstance(raw, dict) or not isinstance(raw.get("findings"), list):
        raise VerificationError("consistency review must return a findings list")
    findings = []
    for finding in raw["findings"]:
        if not isinstance(finding, dict):
            raise VerificationError("consistency finding must be an object")
        ids = finding.get("section_ids")
        if (
            not isinstance(ids, list)
            or not ids
            or any(not isinstance(sid, str) for sid in ids)
        ):
            raise VerificationError("consistency finding needs affected section IDs")
        if len(ids) != len(set(ids)) or set(ids) - set(pair):
            raise VerificationError(
                "consistency finding may affect only supplied sections"
            )
        issue, instruction = finding.get("issue"), finding.get("repair_instruction")
        if (
            not isinstance(issue, str)
            or not issue.strip()
            or not isinstance(instruction, str)
            or not instruction.strip()
        ):
            raise VerificationError(
                "consistency finding needs an issue and repair instruction"
            )
        evidence = finding.get("evidence", [])
        if not isinstance(evidence, list):
            raise VerificationError("consistency evidence must be a list")
        if evidence:
            # Reuse the same exact-reference validation; the synthetic body only
            # supplies a claim location for this source-link validation call.
            evidence = validate_claims(
                [{"id": "finding", "text": issue, "evidence": evidence}],
                {"body": issue},
                units,
            )[0]["evidence"]
        findings.append(
            {
                "section_ids": ids,
                "issue": issue,
                "repair_instruction": instruction,
                "evidence": evidence,
            }
        )
    return {"findings": findings}


def check_document_sections(
    plan, authored, invoke, fits=None, *, workers=1, include_adjacency=False
):
    """Audit completed section relationships with bounded, independent calls.

    ``invoke`` has the production planning callback signature
    ``(stage, item, instruction, shape, input, checker)``. ``fits`` accepts the same
    first four request fields as the planning budget callback: stage, instruction,
    shape, input. Full authored bodies are retained. An oversized pair is reported
    as unchecked and leaves this audit in review; it is never silently summarized.
    """
    from .execution import bounded_map

    rows = {row["id"]: row for row in authored}
    all_units = {unit["id"]: unit for unit in plan["units"]}
    pairs = _document_pairs(plan, include_adjacency)

    def audit(job):
        pair, reasons = job
        selected = [rows[sid] for sid in pair]
        cited = {e["unit_id"] for row in selected for e in row.get("evidence", [])}
        cited.update(
            e["unit_id"]
            for row in selected
            for claim in row.get("claims", [])
            for e in claim["evidence"]
        )
        shared = [
            row
            for row in plan["route"].get("shared_context", [])
            if (
                set(pair).issubset(row["section_ids"])
                if "section_ids" in row
                else any(e["unit_id"] in cited for e in row["evidence"])
            )
        ]
        cited.update(e["unit_id"] for row in shared for e in row["evidence"])
        units = {uid: all_units[uid] for uid in cited}
        source_ids = {u["source_id"] for u in units.values()}
        data = {
            "brief": plan["brief"],
            "format": plan["options"]["format"],
            "relationship": reasons,
            "sections": selected,
            "sources": [
                source
                for source in plan.get("sources", [])
                if source["id"] in source_ids
            ],
            "source_policy": {
                sid: role
                for sid, role in plan["options"].get("source_policy", {}).items()
                if sid in source_ids
            },
            "shared_context": shared,
        }
        if fits is not None and not fits(
            "production_consistency", CONSISTENCY_INSTRUCTION, CONSISTENCY_SHAPE, data
        ):
            return {
                "section_ids": list(pair),
                "relationship": reasons,
                "status": "unchecked",
                "reason": "Completed section pair exceeds the declared request budget; provide a model context that fits or revise the section boundaries.",
                "findings": [],
            }
        try:
            result = invoke(
                "production_consistency",
                ":".join(pair),
                CONSISTENCY_INSTRUCTION,
                CONSISTENCY_SHAPE,
                data,
                lambda raw: _consistency_check(raw, pair, units),
            )
        except Exception as exc:
            return {
                "section_ids": list(pair),
                "relationship": reasons,
                "status": "unchecked",
                "reason": str(exc),
                "error_type": type(exc).__name__,
                "findings": [],
            }
        return {
            "section_ids": list(pair),
            "relationship": reasons,
            "status": "review" if result["findings"] else "checked",
            "findings": result["findings"],
        }

    checks = bounded_map(audit, pairs, workers) if pairs else []
    checked = [row for row in checks if row["status"] != "unchecked"]
    total_pairs = len(rows) * (len(rows) - 1) // 2
    return {
        "status": (
            "review" if any(row["status"] != "checked" for row in checks) else "checked"
        ),
        "checks": checks,
        "findings": [finding for row in checks for finding in row["findings"]],
        "scope": {
            "selection": "Declared source/candidate dependencies and shared-context evidence linking multiple owners."
            + (" Consecutive sections also checked." if include_adjacency else ""),
            "checked_pair_count": len(checked),
            "unchecked_due_to_budget_or_failure": [
                row["section_ids"] for row in checks if row["status"] == "unchecked"
            ],
            "other_pair_count": total_pairs - len(pairs),
            "limitation": "Other cross-section relationships and missing relationships were not examined by this audit.",
        },
    }
