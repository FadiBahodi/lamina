"""Explicit task limits and their evidence, separate from context capacity.

Limits are operator-selected workload policies. An observed profile links an
evaluation report for a particular adapter and protocol. Neither status certifies
recall on an unseen source. This module supplies no universal size.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re

from .store import canonical


@dataclass(frozen=True)
class WorkloadProfile:
    stage: str
    max_input_tokens: int | None = None
    max_items: int | None = None
    basis: str = "configured"
    evidence: dict | None = None

    def __post_init__(self):
        if not isinstance(self.stage, str) or not self.stage:
            raise ValueError("workload profile needs a stage")
        for name in ("max_input_tokens", "max_items"):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or value < 1):
                raise ValueError(f"workload {name} must be a positive integer")
        if self.max_input_tokens is None and self.max_items is None:
            raise ValueError("workload profile needs an input-token or item limit")
        if self.basis not in {"configured", "observed"}:
            raise ValueError("workload basis must be configured or observed")
        if self.stage == "*" and (
            self.basis != "configured" or self.evidence is not None
        ):
            raise ValueError(
                "a wildcard workload must be configured without stage-specific evidence"
            )
        if self.evidence is not None:
            required = {
                "provider_identity",
                "protocol_revision",
                "report_sha256",
                "report_path",
            }
            if (
                not isinstance(self.evidence, dict)
                or set(self.evidence) != required
                or any(not isinstance(v, str) or not v for v in self.evidence.values())
                or not re.fullmatch(r"[0-9a-f]{64}", self.evidence["report_sha256"])
            ):
                raise ValueError(
                    "workload evidence needs provider_identity, protocol_revision "
                    "report_path and a lowercase report_sha256"
                )
            object.__setattr__(self, "evidence", dict(self.evidence))
        if self.basis == "observed" and self.evidence is None:
            raise ValueError("an observed workload profile needs evaluation evidence")
        if self.evidence is not None:
            self._validate_report()

    @property
    def identity(self) -> str:
        data = asdict(self)
        if data["evidence"] is not None:
            data["evidence"].pop("report_path")
        return "workload:" + hashlib.sha256(canonical(data).encode()).hexdigest()

    def _validate_report(self):
        """Check the linked observation's provenance without inferring a safe size."""
        try:
            payload = Path(self.evidence["report_path"]).read_bytes()
            report = json.loads(payload)
        except (OSError, ValueError) as exc:
            raise ValueError("workload evaluation report cannot be read") from exc
        if hashlib.sha256(payload).hexdigest() != self.evidence["report_sha256"]:
            raise ValueError("workload evaluation report digest does not match")
        if (
            not isinstance(report, dict)
            or report.get("evaluation") != "configured-provider-observations"
            or report.get("protocol_revision") != self.evidence["protocol_revision"]
        ):
            raise ValueError(
                "workload evidence must reference matching configured-provider observations"
            )
        trials = report.get("trials")
        if not isinstance(trials, list):
            raise ValueError("workload evaluation report has no trials")
        for trial in trials:
            if not isinstance(trial, dict) or trial.get("experimental_stage") not in {
                None,
                self.stage,
            }:
                continue
            if (
                trial.get("status") != "completed"
                or trial.get("protocol_revision") != self.evidence["protocol_revision"]
            ):
                continue
            budgets = trial.get("stage_budgets")
            budget = budgets.get(self.stage) if isinstance(budgets, dict) else None
            calls = trial.get("calls")
            if not isinstance(calls, list) or not any(
                isinstance(call, dict)
                and call.get("stage") == self.stage
                and call.get("status") == "completed"
                for call in calls
            ):
                continue
            workload = budget.get("workload") if isinstance(budget, dict) else None
            if isinstance(budget, dict) and (
                budget.get("configuration_identity")
                == self.evidence["provider_identity"]
                and isinstance(workload, dict)
                and all(
                    workload.get(name) == getattr(self, name)
                    for name in ("max_input_tokens", "max_items")
                )
            ):
                return
        raise ValueError(
            "workload report has no matching provider, stage and limit observation"
        )

    def validate_binding(self, *, provider_identity=None, protocol_revision=None):
        if self.evidence is None:
            return
        if provider_identity is not None and (
            self.evidence["provider_identity"] != provider_identity
        ):
            raise ValueError(
                "workload evidence belongs to another provider configuration"
            )
        if protocol_revision is not None and (
            self.evidence["protocol_revision"] != protocol_revision
        ):
            raise ValueError(
                "workload evidence belongs to another request protocol revision"
            )


def parse_workloads(value) -> dict[str, WorkloadProfile]:
    """Load per-stage profiles without inheriting one stage's limit into another."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("workload must map stage names to workload profiles")
    result = {}
    fields = {"max_input_tokens", "max_items", "basis", "evidence"}
    for stage, row in value.items():
        if isinstance(row, WorkloadProfile):
            if row.stage != stage:
                raise ValueError("workload map key does not match its profile stage")
            result[stage] = row
        elif isinstance(row, dict) and not set(row) - fields:
            result[stage] = WorkloadProfile(stage=stage, **row)
        else:
            raise ValueError(f"invalid workload profile for {stage!r}")
    return result


def with_workload(request: dict, items: int) -> dict:
    """Annotate semantic work owned by this request, outside the rendered prompt."""
    if type(items) is not int or items < 0:
        raise ValueError("workload_items must be a nonnegative integer")
    return {**request, "workload_items": items}
