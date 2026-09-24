"""Repeatable workload experiments and profiles selected by stored criteria."""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from .production_contract import REVISION
from .quality_evaluation import Canary, run_trial, summarize
from .store import digest
from .workload_profiles import WorkloadProfile

# Starting policies, not measured optima. Each stage owns different work.
STARTER_ITEMS = {
    "production_read": 96,
    "production_route": 64,
    "production_group": 24,
    "production_assign": 24,
    "production_targets": 12,
    "production_write": 6,
    "production_review": 6,
    "production_repair": 6,
    "production_consistency": 2,
    "assessment_blind_solve": 1,
    "assessment_judge": 1,
}

_PROMOTION_POLICY = "all-declared-checks-two-replicates-v1"
_REQUIRED_CHECK_STAGES = {"extraction", "assignment", "finished_output"}


def _policy_status(report, criteria):
    """Return why a report cannot support a promoted/pass QC status."""
    if type(report.get("replicates_required")) is not int or report.get(
        "replicates_required", 0
    ) < 2:
        return "insufficient_replicates"
    if (
        report.get("promotion_policy") != _PROMOTION_POLICY
        or not isinstance(criteria, dict)
        or criteria.get("minimum_fraction_per_stage_and_position") != 1.0
        or criteria.get("maximum_counterfacts_per_stage") != 0
        or set(criteria.get("required_stages", [])) != _REQUIRED_CHECK_STAGES
    ):
        return "ineligible_policy"
    return None


def starter_workloads():
    return {
        stage: {"max_items": limit, "basis": "configured"}
        for stage, limit in STARTER_ITEMS.items()
    }


class ExperimentalProvider:
    """Change one stage's workload; retain the adapter's actual capacity limits."""

    def __init__(self, provider, stage, limit, dimension="max_items"):
        self.provider, self.stage, self.limit, self.dimension = (
            provider,
            stage,
            limit,
            dimension,
        )
        self.identity = (
            provider.identity + ":experiment:" + digest([stage, dimension, limit])
        )

    def __getattr__(self, name):
        return getattr(self.provider, name)

    def identity_for(self, stage):
        identity = getattr(
            self.provider, "identity_for", lambda _: self.provider.identity
        )(stage)
        return (
            identity + ":experiment:" + digest([self.stage, self.dimension, self.limit])
            if stage == self.stage
            else identity
        )

    def budget_for(self, stage):
        budget = self.provider.budget_for(stage)
        if stage == self.stage:
            values = {self.dimension: self.limit}
            # Preserve the other declared workload guard while varying one axis.
            if budget.workload:
                other = (
                    "max_items"
                    if self.dimension == "max_input_tokens"
                    else "max_input_tokens"
                )
                values[other] = getattr(budget.workload, other)
            budget = replace(budget, workload=WorkloadProfile(stage, **values))
        return budget


def read_corpus(manifest):
    """Private or public sources plus declared lexical checks; no text is published."""
    manifest = Path(manifest).resolve()
    data = json.loads(manifest.read_text())
    paths = [(manifest.parent / p).resolve() for p in data["sources"]]
    if not paths or len({p.name for p in paths}) != len(paths):
        raise ValueError("corpus needs sources with distinct filenames")
    for path in paths:
        if not path.is_file():
            raise ValueError("corpus source is missing")
    canaries = [
        Canary(
            **{
                **row,
                "required": tuple(row["required"]),
                "forbidden": tuple(row.get("forbidden", [])),
            }
        )
        for row in data["canaries"]
    ]
    if not canaries or len({row.id for row in canaries}) != len(canaries):
        raise ValueError("corpus needs uniquely identified canaries")
    if any(
        row.source not in {p.name for p in paths} or not row.required
        for row in canaries
    ):
        raise ValueError("canaries must name supplied sources and required phrases")
    brief = data["brief"]
    if not isinstance(brief, str) or not brief.strip():
        raise ValueError("corpus needs a production brief")
    return paths, canaries, brief


def calibrate(
    provider,
    output,
    *,
    stage="production_read",
    limits=(12, 24, 48),
    dimension="max_items",
    replicates=3,
    load=30,
    corpus=None,
    minimum_fraction=1.0,
    maximum_counterfacts=0,
    progress=None,
):
    """Run production end to end for each setting; save every replicate immediately."""
    if stage not in {"production_read", "production_write"}:
        raise ValueError(
            "calibration stage must be production_read or production_write"
        )
    if dimension not in {"max_items", "max_input_tokens"}:
        raise ValueError("unknown workload dimension")
    if (
        replicates < 1
        or not limits
        or any(type(n) is not int or n < 1 for n in limits)
        or len(set(limits)) != len(limits)
    ):
        raise ValueError(
            "supply positive distinct limits and a positive replicate count"
        )
    if not 0 <= minimum_fraction <= 1 or maximum_counterfacts < 0:
        raise ValueError("invalid acceptance criteria")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    created = datetime.now(timezone.utc).isoformat()
    report = {
        "evaluation": "configured-provider-observations",
        "protocol_revision": REVISION,
        "created_at": created,
        "stage": stage,
        "dimension": dimension,
        "replicates_required": replicates,
        "limits": list(limits),
        "trials": [],
        "promotion_policy": _PROMOTION_POLICY,
        "oracle_scope": "Declared lexical checks in authored text with matching source evidence.",
    }
    report_path = output / "report.json"
    for limit in limits:
        experimental = ExperimentalProvider(provider, stage, limit, dimension)
        for replicate in range(1, replicates + 1):
            if progress:
                progress({"limit": limit, "replicate": replicate, "status": "running"})
            trial = run_trial(
                experimental,
                output / f"limit-{limit}-replicate-{replicate}",
                load=load,
                reading="task",
                complete=True,
                corpus=corpus,
            )
            trial.update(
                experimental_stage=stage,
                experimental_limit=limit,
                experimental_dimension=dimension,
                replicate=replicate,
            )
            report["trials"].append(trial)
            report["summary"] = summarize(
                report["trials"],
                minimum_fraction=minimum_fraction,
                maximum_counterfacts=maximum_counterfacts,
                required_stages=["extraction", "assignment", "finished_output"],
            )
            report_path.write_text(json.dumps(report, indent=2) + "\n")
            if progress:
                progress(
                    {
                        "limit": limit,
                        "replicate": replicate,
                        "status": trial["status"],
                        "wall_ms": trial["wall_ms"],
                        "usage": trial["usage"],
                    }
                )
    profiles = promote_profiles(report_path)
    (output / "profiles.json").write_text(json.dumps(profiles, indent=2) + "\n")
    return {
        "report": str(report_path),
        "profiles": str(output / "profiles.json"),
        "promoted": sorted(profiles),
        "summary": report["summary"],
    }


def promote_profiles(report_path):
    """Select only a tested setting with all declared replicates passing the criteria."""
    report_path = Path(report_path).resolve()
    raw = report_path.read_bytes()
    report = json.loads(raw)
    if (
        report.get("evaluation") != "configured-provider-observations"
        or report.get("protocol_revision") != REVISION
    ):
        raise ValueError("promotion requires observations from the current protocol")
    stage, dimension = report["stage"], report["dimension"]
    passing = []
    criteria = report["summary"]["criteria"]
    if _policy_status(report, criteria):
        return {}
    for limit in report["limits"]:
        trials = [
            t
            for t in report["trials"]
            if t.get("experimental_stage") == stage
            and t.get("experimental_limit") == limit
        ]
        if len(trials) != report["replicates_required"] or {
            t.get("replicate") for t in trials
        } != set(range(1, report["replicates_required"] + 1)):
            continue
        if any(t.get("engine_status") != "ready" for t in trials):
            continue
        if len({t.get("corpus_sha256") for t in trials}) != 1 or not trials[0].get(
            "corpus_sha256"
        ):
            continue
        if len({t.get("evaluation_sha256") for t in trials}) != 1 or not trials[
            0
        ].get("evaluation_sha256"):
            continue
        if any(t.get("experimental_dimension") != dimension for t in trials):
            continue
        checked = summarize(
            trials,
            minimum_fraction=criteria["minimum_fraction_per_stage_and_position"],
            maximum_counterfacts=criteria["maximum_counterfacts_per_stage"],
            required_stages=criteria["required_stages"],
        )
        if not all(
            row["passed_all_observed_checks"] for row in checked["observations"]
        ):
            continue
        budgets = [t.get("stage_budgets", {}).get(stage, {}) for t in trials]
        if any(
            not b.get("workload") or b["workload"].get(dimension) != limit
            for b in budgets
        ):
            continue
        identities = {b.get("configuration_identity") for b in budgets}
        if len(identities) != 1 or None in identities:
            continue
        passing.append((limit, budgets[0]))
    if not passing:
        return {}
    _, budget = max(passing, key=lambda row: row[0])
    limits = {
        name: budget["workload"][name]
        for name in ("max_items", "max_input_tokens")
        if budget["workload"].get(name) is not None
    }
    profile = WorkloadProfile(
        stage,
        **limits,
        basis="observed",
        evidence={
            "provider_identity": budget["configuration_identity"],
            "protocol_revision": REVISION,
            "report_path": str(report_path),
            "report_sha256": hashlib.sha256(raw).hexdigest(),
        },
    )
    return {
        stage: {
            key: value
            for key, value in asdict(profile).items()
            if key != "stage" and value is not None
        }
    }


def quality_status(provider, stages, *, now=None, max_age_days=30):
    """Attach the configured QC report and workload status to a production receipt."""
    now = now or datetime.now(timezone.utc)
    result = {}
    for stage in stages:
        from .context_budget import RequestBudget

        profile = getattr(provider, "budget_for", lambda _: RequestBudget(1_500_000))(
            stage
        ).workload
        evidence = profile.evidence if profile else None
        path = getattr(provider, "qc_report", None) or (evidence or {}).get(
            "report_path"
        )
        row = {
            "workload_basis": profile.basis if profile else "unassessed",
            "qc_status": "unmeasured",
        }
        if profile:
            row["workload"] = {
                k: getattr(profile, k) for k in ("max_items", "max_input_tokens")
            }
        if evidence:
            row["profile_report_sha256"] = evidence["report_sha256"]
        if path:
            try:
                raw = Path(path).read_bytes()
                report = json.loads(raw)
                row.update(
                    report_sha256=hashlib.sha256(raw).hexdigest(),
                    created_at=report.get("created_at"),
                )
                if (
                    not getattr(provider, "qc_report", None)
                    and evidence
                    and row["report_sha256"] != evidence["report_sha256"]
                ):
                    row["qc_status"] = "report_changed"
                    result[stage] = row
                    continue
                if (
                    report.get("evaluation") != "configured-provider-observations"
                    or report.get("protocol_revision") != REVISION
                ):
                    row["qc_status"] = "configuration_mismatch"
                    result[stage] = row
                    continue
                if report.get("stage") != stage:
                    row["qc_status"] = "unmeasured_stage"
                    result[stage] = row
                    continue
                criteria = report.get("summary", {}).get("criteria")
                if policy_status := _policy_status(report, criteria):
                    row["qc_status"] = policy_status
                    result[stage] = row
                    continue
                identity = getattr(
                    provider,
                    "configuration_identity_for",
                    lambda _: getattr(
                        provider, "configuration_identity", provider.identity
                    ),
                )(stage)
                dimension = report.get("dimension")
                workload = row.get("workload", {})
                limit = workload.get(dimension) if isinstance(dimension, str) else None
                candidates = [
                    t
                    for t in report.get("trials", [])
                    if t.get("experimental_stage") == stage
                    and t.get("experimental_dimension") == dimension
                    and t.get("experimental_limit") == limit
                ]
                expected_replicates = set(
                    range(1, report["replicates_required"] + 1)
                )
                if len(candidates) != report["replicates_required"] or {
                    t.get("replicate") for t in candidates
                } != expected_replicates:
                    row["qc_status"] = "insufficient_replicates"
                    result[stage] = row
                    continue
                budgets = [t.get("stage_budgets", {}).get(stage, {}) for t in candidates]
                if any(
                    t.get("protocol_revision") != REVISION
                    or budget.get("configuration_identity") != identity
                    or any(
                        (budget.get("workload") or {}).get(k) != workload.get(k)
                        for k in ("max_items", "max_input_tokens")
                    )
                    for t, budget in zip(candidates, budgets)
                ):
                    row["qc_status"] = "configuration_mismatch"
                    result[stage] = row
                    continue
                corpus_hashes = {t.get("corpus_sha256") for t in candidates}
                evaluation_hashes = {t.get("evaluation_sha256") for t in candidates}
                if (
                    len(corpus_hashes) != 1
                    or None in corpus_hashes
                    or len(evaluation_hashes) != 1
                    or None in evaluation_hashes
                ):
                    row["qc_status"] = "evaluation_mismatch"
                    result[stage] = row
                    continue
                summary = summarize(
                    candidates,
                    minimum_fraction=criteria[
                        "minimum_fraction_per_stage_and_position"
                    ],
                    maximum_counterfacts=criteria["maximum_counterfacts_per_stage"],
                    required_stages=criteria["required_stages"],
                )
                row["qc_status"] = (
                    "passed"
                    if all(
                        r["passed_all_observed_checks"]
                        for r in summary["observations"]
                    )
                    and all(t.get("engine_status") == "ready" for t in candidates)
                    else "failed"
                )
                row["criteria"] = criteria
                row["corpus_sha256"] = sorted(corpus_hashes)
                row["evaluation_sha256"] = sorted(evaluation_hashes)
                row["trials"] = len(candidates)
                created = datetime.fromisoformat(report["created_at"])
                row["age_days"] = max(0, (now - created).total_seconds() / 86400)
                row["stale"] = row["age_days"] > max_age_days
            except (OSError, ValueError, KeyError, TypeError):
                row["qc_status"] = "unavailable"
        result[stage] = row
    return result


def write_model_configuration(models_path, result):
    """Write a usable copy beside the report, applying only passing profiles."""
    models_path = Path(models_path).resolve()
    data = json.loads(models_path.read_text())
    profiles = json.loads(Path(result["profiles"]).read_text())
    for row in [data["default"], *data.get("stages", {}).values()]:
        if row.get("workload") == "starter":
            row["workload"] = starter_workloads()
        for profile in row.get("workload", {}).values():
            evidence = profile.get("evidence")
            if evidence and evidence.get("report_path"):
                evidence["report_path"] = str(
                    (models_path.parent / evidence["report_path"]).resolve()
                )
    for stage, profile in profiles.items():
        row = data.get("stages", {}).get(stage, data["default"])
        row.setdefault("workload", {})[stage] = profile
    data["qc_report"] = result["report"]
    path = Path(result["report"]).parent / "models.json"
    with path.open("x") as stream:
        json.dump(data, stream, indent=2)
        stream.write("\n")
    return str(path)
