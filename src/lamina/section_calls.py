"""One production run's section calls: write, review and repair, singly or batched.

Each call binds the section's visible context (see ``section_context``) to
compact local aliases, validates the response against the section's
assignment, and restores canonical unit IDs. A review that does not fit the
reviewer's capacity returns an explicit unperformed-verification finding, so
the section stays in review instead of failing the run.
"""

from __future__ import annotations

from .production_contract import (
    ProductionError,
    _FORM,
    _SHAPES,
    _authored_check,
    _review_check,
    request_limit,
    validated,
)
from .section_context import (
    _REPAIR_INSTRUCTION,
    _REPAIR_SCOPE,
    _REVIEW_INSTRUCTION,
    _authored_shape,
    _review_text_context,
    _section_items,
    _write_request,
)


def _unperformed_review(exc):
    return {
        "findings": [
            {
                "issue": "Review was not performed: " + str(exc),
                "repair_instruction": "Use a reviewer with sufficient capacity or revise the section boundaries.",
                "evidence": [],
                "verification_unperformed": True,
            }
        ]
    }


class SectionCalls:
    """The write, review and repair callbacks ``execution.section_pipeline`` schedules.

    ``contexts`` maps each section ID to its ``(data, units)`` context and
    ``notes`` maps section IDs to operator revision notes.
    """

    def __init__(self, workspace, provider, plan, opts, contexts, notes, tracker):
        self.workspace, self.provider, self.tracker = workspace, provider, tracker
        self.plan, self.opts = plan, opts
        self.contexts, self.notes = contexts, notes

    def _authored(self, raw, section, local_units):
        return validated(_authored_check, raw, section, local_units, self.opts["format"])

    def _call(self, stage, section, instruction, shape, data, units, checker):
        from .context_binding import bind_context, restore_references

        bound, bound_units, reverse = bind_context(data, units)
        if stage == "production_review":
            bound = _review_text_context(bound, bound_units)
        result = self.tracker.call(
            self.workspace,
            self.provider,
            stage,
            section["id"],
            instruction,
            shape,
            bound,
            lambda raw: checker(raw, bound["section"], bound_units),
            request_limit(self.opts),
            workload_items=_section_items(section),
        )
        return restore_references(result, reverse)

    def write(self, section):
        instruction, shape, data, units = _write_request(
            self.plan,
            section,
            self.contexts[section["id"]],
            self.notes.get(section["id"]),
        )
        return self._call(
            "production_write", section, instruction, shape, data, units, self._authored
        )

    def review(self, pair):
        section, draft = pair
        context, units = self.contexts[section["id"]]
        data = {**context, "draft": draft}
        from .context_budget import ContextBudgetError

        try:
            return self._call(
                "production_review",
                section,
                _REVIEW_INSTRUCTION + _FORM[self.opts["format"]],
                _SHAPES["production_review"],
                data,
                units,
                lambda raw, sec, local: validated(_review_check, raw, local),
            )
        except ProductionError as exc:
            if not isinstance(exc.__cause__, ContextBudgetError):
                raise
            return _unperformed_review(exc)

    def repair(self, pair):
        section, draft, findings = pair
        if any(row.get("verification_unperformed") for row in findings):
            return draft
        context, units = self.contexts[section["id"]]
        data = {
            **context,
            "draft": draft,
            "findings": findings,
            "scope": _REPAIR_SCOPE,
        }
        if section["id"] in self.notes:
            data["operator_revision_note"] = self.notes[section["id"]]
        return self._call(
            "production_repair",
            section,
            _REPAIR_INSTRUCTION + _FORM[self.opts["format"]],
            _authored_shape("production_repair", self.plan, section, self.opts["format"]),
            data,
            units,
            self._authored,
        )

    def many(self, stage, inputs):
        """Write or review several sections in one request where capacity allows."""
        from .section_batching import call_sections

        return call_sections(
            [self._batch_job(stage, item) for item in inputs],
            workspace=self.workspace,
            provider=self.provider,
            tracker=self.tracker,
            stage=stage,
            max_bytes=request_limit(self.opts),
            single=lambda job: self._single(stage, job),
            finish=lambda job, value: self._finish(stage, job, value),
        )

    def _batch_job(self, stage, item):
        """The exact single-section envelope and local validator for one batch member."""
        from .call_runtime import make_envelope
        from .context_binding import bind_context

        if stage == "production_write":
            section = item
            instruction, shape, data, units = _write_request(
                self.plan,
                section,
                self.contexts[section["id"]],
                self.notes.get(section["id"]),
            )
        else:
            section, draft = item
            context, units = self.contexts[section["id"]]
            data = {**context, "draft": draft}
            instruction = _REVIEW_INSTRUCTION + _FORM[self.opts["format"]]
            shape = _SHAPES["production_review"]
        bound, local_units, reverse = bind_context(data, units)
        if stage == "production_review":
            bound = _review_text_context(bound, local_units)

        def check(raw):
            if stage == "production_write":
                return self._authored(raw, bound["section"], local_units)
            return validated(_review_check, raw, local_units)

        return {
            "id": section["id"],
            "checker": check,
            "reverse": reverse,
            "instruction": instruction,
            "envelope": make_envelope(
                stage,
                instruction,
                shape,
                bound,
                workload_items=_section_items(section),
            ),
        }

    def _single(self, stage, job):
        envelope = job["envelope"]
        return self.tracker.call(
            self.workspace,
            self.provider,
            stage,
            job["id"],
            job["instruction"],
            envelope["expected_shape"],
            envelope["input"],
            job["checker"],
            request_limit(self.opts),
            workload_items=envelope["workload_items"],
        )

    def _finish(self, stage, job, value):
        from .context_binding import restore_references

        # Match the single-section contract: insufficient review capacity
        # remains explicit unfinished verification, even in deferred calls.
        if stage == "production_review":
            from .context_budget import ContextBudgetError

            if isinstance(value, ProductionError) and isinstance(
                value.__cause__, ContextBudgetError
            ):
                value = _unperformed_review(value)
        return (
            value
            if isinstance(value, Exception)
            else restore_references(value, job["reverse"])
        )
