"""Contract tests use deterministic responses, not model-quality scores."""

import copy
from dataclasses import replace
import threading
import time

import pytest

from lamina.execution import section_pipeline
from lamina.ingest import ingest_paths
from lamina.production import (
    ProductionError,
    _Tracker,
    _windows,
    build_production,
    plan_production,
    run_production,
)
from lamina.providers import CommandProvider, ProviderError, StageProvider
from lamina.store import Workspace
from test_production import FixtureProvider, workspace


class SourceWriter(FixtureProvider):
    def call(self, stage, payload):
        data = payload["input"]
        if (
            stage in {"production_write", "production_repair"}
            and "unit_ids" in data["section"]
        ):
            self.requests.append((stage, copy.deepcopy(payload)))
            assert "assigned_ideas" not in data
            units = data["assigned_units"]
            result = {
                "title": "Wind and blades",
                "body": "\n\n".join(u["text"] for u in units),
                "used_unit_ids": [u["id"] for u in units],
                "omitted_units": [],
                "evidence": [
                    {"unit_id": u["id"], "quote": u["text"][:100]} for u in units
                ],
            }
            if data["format"] == "assessment":
                result.update(
                    candidate_body="What makes the blades turn?",
                    marking_body=result.pop("body"),
                )
            if data.get("operator_revision_note"):
                result["body"] += "\n" + data["operator_revision_note"]
            return result
        return super().call(stage, payload)


def assignments():
    return {
        "title": "Lease safety",
        "summary": "Compare expiry and stale writes",
        "sections": [
            {
                "id": "expiry",
                "title": "Expiry",
                "purpose": "Explain expiry",
                "unit_ids": ["u1", "u2"],
                "representation": {
                    "kind": "comparison",
                    "rationale": "Explain a condition",
                    "requirements": [],
                },
            },
            {
                "id": "writes",
                "title": "Writes",
                "purpose": "Explain fencing",
                "unit_ids": ["u3", "u4"],
                "context_unit_ids": ["u2"],
                "representation": {
                    "kind": "procedure",
                    "rationale": "Show the steps",
                    "requirements": [],
                },
            },
        ],
        "omitted": [],
        "shared_context": [],
    }


def test_auto_small_input_skips_reading_and_planning(tmp_path):
    ws, provider = workspace(tmp_path), SourceWriter()
    result = build_production(
        ws, provider, "Explain", ["s1", "s2"], {"workflow": "auto"}
    )
    assert result["plan"]["options"]["workflow"] == "direct"
    assert result["plan"]["metrics"]["extracted_ideas"] == 0
    assert [stage for stage, _ in provider.requests] == [
        "production_write",
        "production_review",
    ]
    assert result["title"] == "Wind and blades"
    assert set(result["sections"][0]["used_unit_ids"]) == {"u1", "u2", "u3", "u4"}
    repeat = run_production(ws, provider, result["plan"])
    assert repeat["metrics"]["provider_request_bytes"] == 0
    assert repeat["metrics"]["cache_hits"] == 2


def test_assigned_context_is_not_ownership_and_revision_is_local(tmp_path):
    ws, provider = workspace(tmp_path), SourceWriter()
    plan = plan_production(
        ws,
        provider,
        "Explain",
        ["s1", "s2"],
        {"workflow": "assigned", "assignments": assignments()},
    )
    assert provider.requests == []
    first = run_production(ws, provider, plan)
    request = next(
        p["input"]
        for s, p in provider.requests
        if s == "production_write" and p["input"]["section"]["id"] == "writes"
    )
    units = {unit["id"]: unit for unit in plan["units"]}
    assert {u["text"] for u in request["assigned_units"]} == {
        units[uid]["text"] for uid in ("u3", "u4")
    }
    assert [u["text"] for u in request["earlier_evidence_units"]] == [
        units["u2"]["text"]
    ]
    assert {u["id"] for u in request["assigned_units"]}.isdisjoint(
        u["id"] for u in request["earlier_evidence_units"]
    )
    assert set(first["sections"][1]["used_unit_ids"]) == {"u3", "u4"}
    before = len(provider.requests)
    revised = run_production(
        ws, provider, plan, {"section_notes": {"writes": "Explain the retry"}}
    )
    assert len(provider.requests) - before == 2
    assert revised["sections"][0] == first["sections"][0]
    assert revised["sections"][1] != first["sections"][1]


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "unknown"])
def test_assignments_must_account_for_sources_before_calls(tmp_path, mutation):
    ws, provider, spec = workspace(tmp_path), SourceWriter(), assignments()
    if mutation == "missing":
        spec["sections"][1]["unit_ids"].remove("u4")
    elif mutation == "duplicate":
        spec["sections"][1]["unit_ids"].append("u1")
    else:
        spec["sections"][1]["context_unit_ids"] = ["not-selected"]
    with pytest.raises(ProductionError):
        plan_production(
            ws,
            provider,
            "Explain",
            ["s1", "s2"],
            {"workflow": "assigned", "assignments": spec},
        )
    assert not provider.requests


def test_writer_cannot_silently_drop_assigned_unit(tmp_path):
    class Dropping(SourceWriter):
        def call(self, stage, payload):
            result = super().call(stage, payload)
            if stage == "production_write":
                result["used_unit_ids"].pop()
            return result

    with pytest.raises(ProductionError, match="every assigned source unit"):
        build_production(
            workspace(tmp_path), Dropping(), "Explain", ["s1"], {"workflow": "direct"}
        )


def test_direct_assessment_preserves_candidate_boundary(tmp_path):
    provider = SourceWriter()
    result = build_production(
        workspace(tmp_path),
        provider,
        "Ask a question",
        ["s1"],
        {"workflow": "direct", "format": "assessment"},
    )
    assert "lease expires" not in result["markdown"]
    assert "lease expires" in result["examiner_markdown"]
    assert result["assessment_checks"]["status"] == "passed"


def test_large_direct_request_fails_before_provider(tmp_path):
    ws, provider = workspace(tmp_path), SourceWriter()
    with pytest.raises(ProductionError, match="exceeds"):
        build_production(
            ws,
            provider,
            "Explain " * 1000,
            ["s1", "s2"],
            {"workflow": "direct", "max_input_bytes": 4096},
        )
    assert not provider.requests


def test_local_source_edit_reuses_other_reader_interpretations(tmp_path):
    path = tmp_path / "wind.md"
    path.write_text(
        "# Wind\n\n## Blades\n"
        + "Wind turns the blades. Another statement. " * 50
        + "\n\n## Shaft\n"
        + "The shaft carries rotation. Another statement. " * 50
    )
    ws, provider = Workspace(tmp_path / "db"), FixtureProvider()
    original_budget = provider.budget_for

    def one_structure_reader(stage):
        budget = original_budget(stage)
        return (
            replace(
                budget,
                workload=replace(budget.workload, max_items=1),
            )
            if stage == "production_read"
            else budget
        )

    # Separate owned structures explicitly so this edit-locality test does
    # not depend on incidental instruction/schema byte lengths.
    provider.budget_for = one_structure_reader
    ingest_paths([path], ws)
    old_id = ws.sources()[0]["id"]
    options = {"workflow": "planned"}
    first = plan_production(ws, provider, "Explain", [old_id], options)
    assert len(first["windows"]) == 2
    path.write_text(path.read_text().replace("turns", "can turn"))
    ingest_paths([path], ws)
    new_id = next(s["id"] for s in ws.sources() if s["id"] != old_id)
    before = len(provider.requests)
    second = plan_production(ws, provider, "Explain", [new_id], options)
    reads = [p for s, p in provider.requests[before:] if s == "production_read"]
    assert len(reads) == 1
    assert second["metrics"]["cache_hits"] == 1
    assert {u["id"] for u in first["units"]}.isdisjoint(
        u["id"] for u in second["units"]
    )
    allowed = {u["id"] for u in second["units"]}
    assert all(e["unit_id"] in allowed for i in second["ideas"] for e in i["evidence"])


def test_dense_non_whitespace_text_does_not_collapse_to_one_window():
    units = [
        {"id": str(i), "source_id": "s", "heading": "H", "text": "风" * 1800}
        for i in range(100)
    ]
    windows = _windows(units, 1600, 0)
    assert len(windows) == 100
    assert all(not w["before"] and not w["after"] for w in windows)


def test_shared_context_evidence_is_authorized(tmp_path):
    ws, provider = workspace(tmp_path), SourceWriter()
    spec = assignments()
    spec["shared_context"] = [
        {
            "statement": "Fresh tokens matter",
            "evidence": [{"unit_id": "u4", "quote": "A retry uses the current token."}],
        }
    ]
    plan = plan_production(
        ws,
        provider,
        "Explain",
        ["s1", "s2"],
        {"workflow": "assigned", "assignments": spec},
    )
    from lamina.production import _section_context

    data, allowed = _section_context(plan, plan["route"]["sections"][0])
    assert "u4" in allowed
    assert [u["id"] for u in data["shared_evidence_units"]] == ["u4"]
    assert all(set(row) == {"id", "title", "purpose"} for row in data["shared_route"])


def test_review_can_finish_before_unrelated_slow_writer():
    reviewed = threading.Event()

    def write(section):
        if section["id"] == "slow":
            assert reviewed.wait(5), "review waited for an unrelated writer"
        return {"body": section["id"]}

    def review(pair):
        if pair[0]["id"] == "fast":
            reviewed.set()
        return {"findings": []}

    rows = [{"id": "slow"}, {"id": "fast"}]
    result, initial, remaining = section_pipeline(
        rows, write, review, None, writers=2, reviewers=1, workers=2
    )
    assert [r["body"] for r in result] == ["slow", "fast"]
    assert not initial and not remaining


def test_failed_call_is_measured(tmp_path):
    class Broken:
        identity = "broken"

        def call(self, *args):
            raise RuntimeError("failure")

    tracker = _Tracker(None)
    with pytest.raises(RuntimeError):
        tracker.call(
            Workspace(tmp_path),
            Broken(),
            "example",
            "one",
            "Do work",
            {},
            {},
            lambda x: x,
            10000,
        )
    assert tracker.metrics()["failed_requests"] == 1
    assert tracker.metrics()["provider_request_bytes"] > 0


def test_model_environment_is_frozen_and_cache_identity_changes(monkeypatch):
    monkeypatch.setenv("LAMINA_MODEL", "first")
    a = CommandProvider(["python"])
    monkeypatch.setenv("LAMINA_MODEL", "second")
    b = CommandProvider(["python"])
    assert a.identity != b.identity
    assert a.env["LAMINA_MODEL"] == "first"
    combined = StageProvider(a, {"production_write": b})
    assert combined.identity_for("production_read") == a.identity
    assert combined.identity_for("production_write") == b.identity


def test_optional_stage_limits_inherit_total_capacity():
    from lamina.production_contract import _options

    options = _options({"workers": 32, "reader_workers": 4})
    assert options["reader_workers"] == 4
    assert options["writer_workers"] == options["review_workers"] == 32


@pytest.mark.parametrize(
    "options",
    [
        {"workflow": []},
        {"workflow": "assigned", "assignments": {"sections": None}},
        {"workflow": "assigned", "assignments": {"sections": [{"id": []}]}},
    ],
)
def test_malformed_configuration_fails_cleanly_before_calls(tmp_path, options):
    provider = SourceWriter()
    with pytest.raises(ProductionError):
        plan_production(workspace(tmp_path), provider, "Explain", ["s1"], options)
    assert provider.requests == []


def test_model_name_does_not_count_as_token_measurement(tmp_path):
    import sys

    adapter = tmp_path / "adapter.py"
    adapter.write_text(
        'import json; print(json.dumps({"protocol":"lamina-response-1","result":{},"model":"example"}))'
    )
    provider = CommandProvider([sys.executable, str(adapter)])
    tracker = _Tracker(None)
    tracker.call(
        Workspace(tmp_path / "db"),
        provider,
        "example",
        "one",
        "Do work",
        {},
        {},
        lambda x: x,
        10000,
    )
    assert tracker.metrics()["usage_reported_calls"] == 0
    assert tracker.records[0]["usage"]["model"] == "example"


def test_assessment_obeys_total_call_limit(tmp_path):
    from lamina.assessment_checks import SOLVE_STAGE, JUDGE_STAGE

    class Measuring(SourceWriter):
        def __init__(self):
            super().__init__()
            self.current = self.peak = 0
            self.measure_lock = threading.Lock()

        def call(self, stage, payload):
            if stage not in {SOLVE_STAGE, JUDGE_STAGE}:
                return super().call(stage, payload)
            with self.measure_lock:
                self.current += 1
                self.peak = max(self.peak, self.current)
            try:
                time.sleep(0.01)
                return super().call(stage, payload)
            finally:
                with self.measure_lock:
                    self.current -= 1

    provider = Measuring()
    result = build_production(
        workspace(tmp_path),
        provider,
        "Ask questions",
        ["s1", "s2"],
        {
            "workflow": "assigned",
            "assignments": assignments(),
            "format": "assessment",
            "workers": 1,
            "review_workers": 8,
        },
    )
    assert result["assessment_checks"]["status"] == "passed"
    assert provider.peak == 1


def test_assessment_uses_effective_request_budget(tmp_path):
    from lamina.assessment_checks import AssessmentCheckError, check_assessment
    from lamina.production import _plan_identity

    ws, provider = workspace(tmp_path), SourceWriter()
    receipt = build_production(
        ws,
        provider,
        "Ask a question",
        ["s1"],
        {"workflow": "direct", "format": "assessment"},
    )
    plan = copy.deepcopy(receipt["plan"])
    plan["options"]["max_input_bytes"] = 4096
    plan["plan_digest"] = _plan_identity(plan)
    receipt = {
        **receipt,
        "plan_digest": plan["plan_digest"],
        "sections": [{**receipt["sections"][0], "candidate_body": "Question " * 2000}],
    }
    before = len(provider.requests)
    with pytest.raises(AssessmentCheckError, match="exceeds"):
        check_assessment(ws, provider, plan, receipt)
    assert len(provider.requests) == before


def test_reverse_order_method_failure_propagates_without_deadlock(tmp_path):
    from lamina.method_runtime import run_method
    from test_method_runtime import garden, CountingProvider

    method = garden()
    first = copy.deepcopy(method["nodes"][0])
    second = {**first, "id": "middle", "depends_on": [first["id"]]}
    final = {**first, "id": "last", "depends_on": ["middle"]}
    method["nodes"] = [final, second, first]
    result = run_method(
        Workspace(tmp_path),
        CountingProvider(fail=first["id"]),
        method,
        {"site_notes": "Wind", "plant_notes": "Plants", "audience": "Readers"},
    )
    assert result["status"] == "failed"
    assert result["nodes"]["last"]["status"] == "skipped"


def test_assignment_id_normalization_preserves_context(tmp_path):
    spec = assignments()
    spec["sections"][1]["id"] = " writes "
    plan = plan_production(
        workspace(tmp_path),
        SourceWriter(),
        "Explain",
        ["s1", "s2"],
        {"workflow": "assigned", "assignments": spec},
    )
    assert plan["route"]["sections"][1]["id"] == "writes"
    assert plan["route"]["sections"][1]["context_unit_ids"] == ["u2"]


def test_requested_context_is_cached_and_never_becomes_owned_material(tmp_path):
    class ContextReader(FixtureProvider):
        def budget_for(self, stage):
            base = replace(super().budget_for(stage), max_request_bytes=100_000)
            if stage != "production_read":
                return base
            # A deterministic capacity fixture fits one owned structure plus
            # context. These token counts are fixtures, not model measurements.
            return replace(
                base,
                context_tokens=20,
                output_tokens=5,
                count_tokens=lambda request: 10 * len(request["input"]["core"])
                + 3
                * (len(request["input"]["before"]) + len(request["input"]["after"])),
            )

        def call(self, stage, payload):
            data = payload["input"]
            if (
                stage == "production_read"
                and data["core"][0]["id"] == "u1"
                and not data["after"]
            ):
                self.requests.append((stage, copy.deepcopy(payload)))
                return {
                    "context_request": {
                        "direction": "after",
                        "reason": "Need the qualification following the expiry statement",
                    }
                }
            return super().call(stage, payload)

    ws, provider = workspace(tmp_path), ContextReader()
    receipt = build_production(
        ws, provider, "Explain expiry", ["s1"], {"workflow": "planned"}
    )
    assert receipt["status"] == "ready"
    plan = receipt["plan"]
    first = next(window for window in plan["windows"] if window["core"] == ["u1"])
    assert first["after"] == ["u2"]
    assert first["context_requests"][0]["unit_ids"] == ["u2"]
    assert [idea["unit_ids"] for idea in plan["ideas"]] == [["u1"], ["u2"]]
    assert plan["metrics"]["failed_requests"] == 0
    assert (
        len([stage for stage, _ in provider.requests if stage == "production_read"])
        == 3
    )
    before = len(provider.requests)
    repeated = build_production(
        ws, provider, "Explain expiry", ["s1"], {"workflow": "planned"}
    )
    assert len(provider.requests) == before
    assert repeated["sections"] == receipt["sections"]
    assert repeated["plan"]["windows"] == plan["windows"]


def test_truncated_reader_splits_at_source_structures_then_finishes(tmp_path):
    class TruncatingReader(FixtureProvider):
        def call(self, stage, payload):
            if stage == "production_read" and len(payload["input"]["core"]) > 1:
                self.requests.append((stage, copy.deepcopy(payload)))
                raise ProviderError(
                    "reader output reached its limit", code="output_truncated"
                )
            return super().call(stage, payload)

    provider = TruncatingReader()
    receipt = build_production(
        workspace(tmp_path), provider, "Explain expiry", ["s1"], {"workflow": "planned"}
    )
    assert receipt["status"] == "ready"
    assert [window["core"] for window in receipt["plan"]["windows"]] == [["u1"], ["u2"]]
    assert [idea["unit_ids"] for idea in receipt["plan"]["ideas"]] == [["u1"], ["u2"]]
    reads = [
        request for stage, request in provider.requests if stage == "production_read"
    ]
    assert [len(request["input"]["core"]) for request in reads] == [2, 1, 1]
    assert receipt["plan"]["metrics"]["failed_requests"] == 1
    assert {
        citation["unit_id"]
        for section in receipt["sections"]
        for citation in section["evidence"]
    } == {"u1", "u2"}


@pytest.mark.parametrize(
    "reading, new_reads", [(None, 1), ("reusable", 0), ("task", 1)]
)
def test_new_brief_reuses_only_brief_independent_reading(tmp_path, reading, new_reads):
    ws, provider = workspace(tmp_path), FixtureProvider()
    options = {"workflow": "planned"}
    if reading is not None:
        options["reading"] = reading
    first = build_production(ws, provider, "Explain expiry", ["s1"], options)
    assert first["plan"]["options"]["reading"] == (reading or "task")
    before = len(provider.requests)
    second = build_production(
        ws, provider, "Compare expiry with termination", ["s1"], options
    )
    added = provider.requests[before:]
    assert first["status"] == second["status"] == "ready"
    assert len([stage for stage, _ in added if stage == "production_read"]) == new_reads
    assert any(stage == "production_route" for stage, _ in added)
    assert {
        request["input"]["brief"]["goal"]
        for stage, request in added
        if stage == "production_write"
    } == {"Compare expiry with termination"}
    assert second["plan"]["metrics"]["cache_hits"] == (
        1 if reading == "reusable" else 0
    )


def test_source_edit_reuses_unchanged_writer_and_restores_current_citations(tmp_path):
    path = tmp_path / "wind.md"
    path.write_text(
        "# Wind\n\n## Blades\nWind turns the blades.\n\n## Shaft\nThe shaft carries rotation.\n"
    )
    ws, provider = Workspace(tmp_path / "db"), SourceWriter()

    def build_source():
        previous_ids = {source["id"] for source in ws.sources()}
        ingest_paths([path], ws)
        source = next(
            source for source in ws.sources() if source["id"] not in previous_ids
        )
        sid = source["id"]
        units = ws.units("teaching", [sid])
        assigned = {
            "title": "Wind turbine components",
            "summary": "Explain each component",
            "sections": [
                {
                    "id": unit["heading"].lower(),
                    "title": unit["heading"],
                    "purpose": "Describe this component",
                    "unit_ids": [unit["id"]],
                    "representation": {
                        "kind": "explanation",
                        "rationale": "Explain the mechanism",
                        "requirements": [],
                    },
                }
                for unit in units
            ],
            "omitted": [],
            "shared_context": [],
        }
        return build_production(
            ws,
            provider,
            "Explain the turbine",
            [sid],
            {"workflow": "assigned", "assignments": assigned},
        )

    first = build_source()
    path.write_text(path.read_text().replace("Wind turns", "Wind can turn"))
    before = len(provider.requests)
    revised = build_source()
    calls = provider.requests[before:]
    assert [(stage, request["input"]["section"]["id"]) for stage, request in calls] == [
        ("production_write", "blades"),
        ("production_review", "blades"),
    ]
    assert revised["metrics"]["cache_hits"] == 2
    assert first["status"] == revised["status"] == "ready"
    old_units = {unit["id"] for unit in first["plan"]["units"]}
    current = {unit["id"]: unit for unit in revised["plan"]["units"]}
    assert old_units.isdisjoint(current)
    for section in revised["sections"]:
        assert set(section["used_unit_ids"]).issubset(current)
        for citation in section["evidence"]:
            assert citation["unit_id"] in current
            assert citation["quote"] in current[citation["unit_id"]]["text"]
    assert revised["sections"][1]["body"] == first["sections"][1]["body"]
    assert revised["sections"][1]["evidence"] != first["sections"][1]["evidence"]


def test_reader_failure_keeps_valid_rows_and_other_windows_are_cached(tmp_path):
    class PartlyInvalidReader(FixtureProvider):
        broken = True

        def call(self, stage, payload):
            result = super().call(stage, payload)
            if (
                stage == "production_read"
                and payload["input"]["source"]["id"] == "s1"
                and self.broken
            ):
                row = (
                    result["replacements"][0]["idea"]
                    if "replacements" in result
                    else result["ideas"][1]
                )
                row["evidence"][0]["quote"] = "unsupported quotation"
            return result

    ws, provider = workspace(tmp_path), PartlyInvalidReader()
    with pytest.raises(ProductionError, match="reading batch.*unresolved") as raised:
        build_production(
            ws, provider, "Explain safety", ["s1", "s2"], {"workflow": "planned"}
        )
    partial = raised.value.partial_results
    assert {uid for idea in partial["ideas"] for uid in idea["unit_ids"]} == {
        "u3",
        "u4",
    }
    failed = partial["failed_windows"][0]["partial"]
    assert [idea["unit_ids"] for idea in failed["ideas"]] == [["u1"]]
    assert failed["invalid_ideas"][0]["index"] == 1
    assert raised.value.metrics["failed_requests"] == 1
    assert raised.value.metrics["failed_attempts"] == 2
    assert not any(stage == "production_route" for stage, _ in provider.requests)

    provider.broken = False
    before = len(provider.requests)
    recovered = build_production(
        ws, provider, "Explain safety", ["s1", "s2"], {"workflow": "planned"}
    )
    new_reads = [
        request
        for stage, request in provider.requests[before:]
        if stage == "production_read"
    ]
    assert recovered["status"] == "ready"
    assert len(new_reads) == 1 and new_reads[0]["input"]["source"]["id"] == "s1"
    assert {uid for idea in recovered["plan"]["ideas"] for uid in idea["unit_ids"]} == {
        "u1",
        "u2",
        "u3",
        "u4",
    }


def test_split_reader_requests_adjacent_sibling_before_outer_context(tmp_path):
    ws = Workspace(tmp_path)
    ws.put_source(
        {
            "id": "s",
            "title": "Sequence",
            "filename": "sequence.md",
            "sha256": "s",
            "role": "teaching",
        }
    )
    ws.put_units(
        [
            {
                "id": name,
                "source_id": "s",
                "role": "teaching",
                "ordinal": n,
                "heading": name,
                "locator": f"part {n}",
                "text": f"{name} supplies a distinct condition. A second sentence preserves context.",
            }
            for n, name in enumerate("abcde")
        ]
    )

    class SplitReader(FixtureProvider):
        def budget_for(self, stage):
            base = replace(super().budget_for(stage), max_request_bytes=100_000)
            if stage != "production_read":
                return base
            return replace(
                base,
                context_tokens=45,
                output_tokens=2,
                count_tokens=lambda request: 10 * len(request["input"]["core"])
                + len(request["input"]["before"])
                + len(request["input"]["after"]),
            )

        def call(self, stage, payload):
            if stage == "production_read":
                data = payload["input"]
                owned = [unit["id"] for unit in data["core"]]
                if owned in (["a", "b", "c", "d"], ["a", "b"]):
                    if not data["after"]:
                        self.requests.append((stage, copy.deepcopy(payload)))
                        return {
                            "context_request": {
                                "direction": "after",
                                "reason": "The next structure supplies the qualification",
                            }
                        }
                    if len(owned) == 4:
                        self.requests.append((stage, copy.deepcopy(payload)))
                        raise ProviderError(
                            "too much reader output", code="output_truncated"
                        )
                    assert [unit["id"] for unit in data["after"]] == [
                        "c"
                    ], "split child skipped its adjacent sibling"
            return super().call(stage, payload)

    provider = SplitReader()
    result = build_production(
        ws, provider, "Explain the sequence", ["s"], {"workflow": "planned"}
    )
    assert result["status"] == "ready"
    windows = {tuple(window["core"]): window for window in result["plan"]["windows"]}
    assert windows[("a", "b")]["after"] == ["c"]
    assert windows[("c", "d")]["after"] == ["e"]
    assert sorted(uid for window in windows.values() for uid in window["core"]) == list(
        "abcde"
    )
    assert {uid for idea in result["plan"]["ideas"] for uid in idea["unit_ids"]} == set(
        "abcde"
    )


def test_partial_reader_diagnostics_restore_exact_ingested_source_ids(tmp_path):
    path = tmp_path / "wind.md"
    path.write_text(
        "# Wind\n\n## Blades\nWind turns the blades. A further condition.\n\n## Shaft\nThe shaft carries rotation. A further condition.\n"
    )
    ws = Workspace(tmp_path / "db")
    ingest_paths([path], ws)
    source_id = ws.sources()[0]["id"]
    original_units = ws.units("teaching", [source_id])

    class InvalidSecondIdea(FixtureProvider):
        def call(self, stage, payload):
            result = super().call(stage, payload)
            if stage == "production_read":
                assert payload["input"]["core"][0]["id"] == "u0"
                row = (
                    result["replacements"][0]["idea"]
                    if "replacements" in result
                    else result["ideas"][1]
                )
                row["evidence"][0]["quote"] = "unsupported quotation"
            return result

    with pytest.raises(ProductionError) as raised:
        build_production(
            ws, InvalidSecondIdea(), "Explain", [source_id], {"workflow": "planned"}
        )
    failed = raised.value.partial_results["failed_windows"][0]
    partial = failed["partial"]
    assert partial["source_id"] == source_id
    assert partial["window_id"] == failed["id"]
    assert partial["core_unit_ids"] == [unit["id"] for unit in original_units]
    assert partial["ideas"][0]["id"].startswith(failed["id"] + ":")
    assert partial["ideas"][0]["unit_ids"] == [original_units[0]["id"]]
    assert partial["ideas"][0]["evidence"][0]["unit_id"] == original_units[0]["id"]
