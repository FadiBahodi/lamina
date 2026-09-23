"""Blind candidate solve followed by a separately informed assessment judge.

This is an information boundary between provider calls, not a guarantee that a
stateful provider has no memory. It checks finished assessment sections; it does
not simulate an interactive candidate or establish clinical/content validity.
"""

from __future__ import annotations

import time
from .execution import bounded_map
from typing import Callable

from .production import (
    REVISION as PRODUCTION_REVISION,
    ProductionError,
    _form_exemplar_context,
    _plan_identity,
    _sources,
    _Tracker,
    request_limit,
)
from .source_policy import normalize_production_inputs
from .store import Workspace, digest

REVISION = "lamina-assessment-check-1"
SOLVE_STAGE = "assessment_blind_solve"
JUDGE_STAGE = "assessment_judge"
_KINDS = {
    "unanswerable",
    "ambiguous",
    "miskeyed",
    "answer_leak",
    "unsupported",
    "other",
}


class AssessmentCheckError(ValueError):
    """An invalid assessment receipt, request, or provider result."""


def _text(value: object, label: str, limit: int = 200000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise AssessmentCheckError(
            f"{label} must be nonempty text of at most {limit} characters"
        )
    return value.strip()


def _solve_result(raw: object) -> dict:
    if not isinstance(raw, dict) or set(raw) != {"answer", "uncertainties"}:
        raise AssessmentCheckError("blind solve must return answer and uncertainties")
    uncertainties = raw["uncertainties"]
    if not isinstance(uncertainties, list) or len(uncertainties) > 30:
        raise AssessmentCheckError("uncertainties must be a bounded list")
    return {
        "answer": _text(raw["answer"], "blind answer", 30000),
        "uncertainties": [_text(x, "uncertainty", 2000) for x in uncertainties],
    }


def _judge_result(raw: object, evidence: list[dict], section_id: str) -> dict:
    if (
        not isinstance(raw, dict)
        or set(raw) != {"findings"}
        or not isinstance(raw["findings"], list)
    ):
        raise AssessmentCheckError("judge must return a findings list")
    if len(raw["findings"]) > 30:
        raise AssessmentCheckError("judge findings exceed limit")
    allowed = {(row["unit_id"], row["quote"]) for row in evidence}
    findings = []
    for row in raw["findings"]:
        if not isinstance(row, dict) or set(row) != {
            "kind",
            "issue",
            "repair_instruction",
            "evidence",
        }:
            raise AssessmentCheckError("judge finding has invalid fields")
        kind = row["kind"]
        if kind not in _KINDS:
            raise AssessmentCheckError("judge finding kind is unknown")
        cites = row["evidence"]
        if not isinstance(cites, list) or len(cites) > 30:
            raise AssessmentCheckError("judge finding evidence must be a bounded list")
        checked = []
        seen = set()
        for citation in cites:
            if not isinstance(citation, dict) or set(citation) != {"unit_id", "quote"}:
                raise AssessmentCheckError("judge citation needs unit_id and quote")
            pair = (citation["unit_id"], citation["quote"])
            if pair not in allowed:
                raise AssessmentCheckError(
                    "judge cited evidence outside the section's exact source excerpts"
                )
            if pair not in seen:
                checked.append({"unit_id": pair[0], "quote": pair[1]})
                seen.add(pair)
        issue = _text(row["issue"], "judge issue", 4000)
        instruction = _text(row["repair_instruction"], "repair instruction", 4000)
        findings.append(
            {
                "id": "acf_"
                + digest([section_id, kind, issue, instruction, checked])[:12],
                "kind": kind,
                "issue": issue,
                "repair_instruction": instruction,
                "evidence": checked,
            }
        )
    return {"findings": findings}


def _inputs(workspace: Workspace, plan: dict, receipt: dict) -> list[dict]:
    if (
        not isinstance(plan, dict)
        or plan.get("revision") != PRODUCTION_REVISION
        or plan.get("plan_digest") != _plan_identity(plan)
    ):
        raise AssessmentCheckError("invalid or modified production plan")
    if plan.get("options", {}).get("format") != "assessment":
        raise AssessmentCheckError("production plan must have assessment format")
    if (
        not isinstance(receipt, dict)
        or receipt.get("revision") != PRODUCTION_REVISION
        or receipt.get("format") != "assessment"
        or receipt.get("plan_digest") != plan["plan_digest"]
    ):
        raise AssessmentCheckError("assessment receipt does not match plan")
    try:
        selected = normalize_production_inputs(
            workspace, [s["id"] for s in plan["sources"]], plan["options"]
        )
        _, all_units = _sources(workspace, selected["source_ids"])
        units = [
            u
            for u in all_units
            if u["source_id"] in set(selected["factual_source_ids"])
        ]
        exemplars = _form_exemplar_context(
            selected["sources"], all_units, selected["form_exemplar_ids"]
        )
    except (ProductionError, ValueError) as exc:
        raise AssessmentCheckError(str(exc)) from exc
    if (
        digest(selected["sources"]) != digest(plan["sources"])
        or digest(units) != digest(plan["units"])
        or digest(exemplars) != digest(plan["form_exemplars"])
        or digest(selected["observations"]) != digest(plan["experience"])
    ):
        raise AssessmentCheckError("selected sources changed; plan again")
    planned = plan["route"]["sections"]
    authored = receipt.get("sections")
    if not isinstance(authored, list) or len(planned) != len(authored):
        raise AssessmentCheckError("receipt sections do not match plan")
    by_unit = {u["id"]: u for u in units}
    rows = []
    prior_candidate = {}
    for index, (section, output) in enumerate(zip(planned, authored), 1):
        if not isinstance(output, dict) or output.get("id") != section["id"]:
            raise AssessmentCheckError(
                "receipt section identity/order differs from plan"
            )
        candidate = _text(output.get("candidate_body"), "candidate_body")
        marking = _text(output.get("marking_body"), "marking_body")
        cited = output.get("evidence")
        if not isinstance(cited, list) or not cited:
            raise AssessmentCheckError("section requires exact evidence")
        evidence = []
        for item in cited:
            if not isinstance(item, dict) or set(item) != {"unit_id", "quote"}:
                raise AssessmentCheckError("invalid section evidence")
            uid, quote = item["unit_id"], item["quote"]
            if (
                uid not in by_unit
                or not isinstance(quote, str)
                or not quote
                or quote not in by_unit[uid]["text"]
            ):
                raise AssessmentCheckError(
                    "section evidence is not an exact selected-source excerpt"
                )
            evidence.append({"unit_id": uid, "quote": quote})
        rows.append(
            {
                "section_id": section["id"],
                "ordinal": index,
                "candidate_body": candidate,
                "prior_candidate_bodies": [
                    prior_candidate[sid]
                    for sid in section.get("candidate_context_ids", [])
                ],
                "marking_body": marking,
                "evidence": evidence,
            }
        )
        prior_candidate[section["id"]] = candidate
    return rows


def check_assessment(
    workspace: Workspace,
    provider,
    plan: dict,
    receipt: dict,
    workers: int = 8,
    progress: Callable[[dict], None] | None = None,
) -> dict:
    """Check each finished section through blind solve and informed judge calls.

    Each solve contains the current prompt and explicitly declared prior prompts.
    The provider is responsible for keeping calls independent; using separate
    provider sessions is recommended for a stronger blind boundary. Changed
    prior candidate text invalidates only solves that declare it as context.
    """
    if type(workers) is not int or not 1 <= workers <= 128:
        raise AssessmentCheckError("workers must be an integer from 1 to 128")
    _text(getattr(provider, "identity", None), "provider.identity", 500)
    rows = _inputs(workspace, plan, receipt)
    max_bytes = request_limit(plan["options"])
    started = time.monotonic()
    tracker = _Tracker(progress, max_attempts=plan["options"]["max_attempts"])

    def call(stage, section_id, instruction, shape, data, checker):
        from .production_contract import ProductionValidationError

        def checked(raw):
            try:
                return checker(raw)
            except AssessmentCheckError as exc:
                raise ProductionValidationError(str(exc)) from exc

        try:
            return tracker.call(
                workspace,
                provider,
                stage,
                section_id,
                instruction,
                shape,
                data,
                checked,
                max_bytes,
                workload_items=1,
            )
        except ProductionError as exc:
            raise AssessmentCheckError(str(exc)) from exc

    def solve(row: dict) -> dict:
        return call(
            SOLVE_STAGE,
            row["section_id"],
            "Act as a candidate seeing only the candidate-facing assessment. Answer the current "
            "section using its prompt and prior candidate prompts. Do not assume an unseen answer key, "
            "source text, or future section. State uncertainty rather than inventing missing facts.",
            {"answer": "str", "uncertainties": ["str"]},
            {
                "current_candidate_body": row["candidate_body"],
                "prior_candidate_bodies": row["prior_candidate_bodies"],
            },
            _solve_result,
        )

    def judge(pair: tuple[dict, dict]) -> dict:
        row, answer = pair
        return call(
            JUDGE_STAGE,
            row["section_id"],
            "Independently compare the blind candidate answer with the candidate prompt, marking "
            "guide, and exact cited source excerpts. Flag concrete unanswerable, ambiguous, miskeyed, "
            "leaking, or unsupported material. Do not infer a defect merely from different wording. "
            "Use only supplied exact excerpts in finding citations; a clean result is not a truth guarantee.",
            {
                "findings": [
                    {
                        "kind": "unanswerable|ambiguous|miskeyed|answer_leak|unsupported|other",
                        "issue": "str",
                        "repair_instruction": "str",
                        "evidence": [
                            {"unit_id": "str", "quote": "exact supplied excerpt"}
                        ],
                    }
                ]
            },
            {
                "candidate_body": row["candidate_body"],
                "prior_candidate_bodies": row["prior_candidate_bodies"],
                "blind_answer": answer,
                "marking_body": row["marking_body"],
                "evidence": row["evidence"],
            },
            lambda raw: _judge_result(raw, row["evidence"], row["section_id"]),
        )

    def check(row):
        answer = solve(row)
        return answer, judge((row, answer))

    try:
        paired = bounded_map(check, rows, workers)
    except Exception as exc:
        exc.metrics = tracker.metrics()
        raise
    answers = [pair[0] for pair in paired]
    judgments = [pair[1] for pair in paired]
    checks = [
        {
            "section_id": row["section_id"],
            "ordinal": row["ordinal"],
            "blind_answer": answer,
            "findings": judgment["findings"],
        }
        for row, answer, judgment in zip(rows, answers, judgments)
    ]
    return {
        "revision": REVISION,
        "status": "review" if any(c["findings"] for c in checks) else "passed",
        "plan_digest": plan["plan_digest"],
        "checks": checks,
        "metrics": {
            "sections": len(checks),
            "flagged_sections": sum(bool(c["findings"]) for c in checks),
            **tracker.metrics(),
            "wall_ms": round((time.monotonic() - started) * 1000, 3),
        },
        "scope": "Model-generated blind answers and separate model judgments; no guaranteed provider isolation, interactive administration, or independent content validity.",
    }
