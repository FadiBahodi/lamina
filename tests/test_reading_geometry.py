"""Reader boundary halo, continued reading after failures and planning locality.

These are protocol fixtures. They establish the dependency shape of the work
(how many serial calls, what is visible to each call), not model quality.
"""

import copy

import pytest

from lamina.call_runtime import CallTracker
from lamina.context_budget import RequestBudget
from lamina.planning import plan_bounded
from lamina.production_contract import ProductionError, _options
from lamina.source_reading import read_sources
from lamina.source_spans import source_spans
from lamina.store import Workspace, canonical


def unit(uid, text, **extra):
    return {
        "id": uid,
        "source_id": "source",
        "heading": "Operation",
        "text": text,
        "role": "teaching",
        "content_id": "content-" + uid,
        "section_id": extra.pop("section_id", uid),
        "section_index": extra.pop("section_index", 0),
        **extra,
    }


PAGE = {
    "p1": "First sentence of page one. Second sentence of page one. Third sentence of page one. Fourth sentence of page one.",
    "p2": "Opening sentence of page two. Middle sentence of page two. Closing sentence of page two.",
    "p3": "Page three begins here. Page three continues. Page three ends.",
}


def options(**extra):
    return _options(
        {
            "reading": "task",
            "format": "document",
            "workers": 1,
            "reader_workers": 1,
            "max_request_bytes": 100_000,
            **extra,
        }
    )


class Provider:
    identity = "halo-fixture"

    def __init__(self, handler):
        self.requests = []
        self.handler = handler
        self.budget = RequestBudget(100_000)

    def budget_for(self, stage):
        return self.budget

    def call(self, stage, request):
        self.requests.append(copy.deepcopy(request))
        return self.handler(request)


def run(tmp_path, provider, units, **overrides):
    return read_sources(
        Workspace(tmp_path),
        provider,
        {"goal": "Explain operation"},
        options(**overrides),
        [{"id": "source", "title": "Pages", "filename": "pages.md"}],
        units,
        CallTracker(),
    )


def core_text(request):
    """Identify a request by its owned text; local aliases restart per window."""
    return request["input"]["core"][0]["spans"][0]["text"]


def own_everything(request):
    return {
        "ideas": [
            {
                "title": "Owned idea",
                "explanation": "Covers the owned unit.",
                "evidence_refs": [
                    {"span_id": u["spans"][0]["id"], "end_span_id": u["spans"][-1]["id"]}
                ],
            }
            for u in request["input"]["core"]
        ]
    }


def test_span_halo_shows_adjacent_boundary_spans_with_real_ids(tmp_path):
    units = [unit(uid, text) for uid, text in PAGE.items()]
    provider = Provider(own_everything)
    windows, ideas, unresolved = run(tmp_path, provider, units, reader_context_spans=2)
    assert unresolved == []
    assert len(windows) == 3 and len(ideas) == 3
    middle = next(
        r["input"] for r in provider.requests if core_text(r).startswith("Opening")
    )
    # Local aliases number the visible units in order: before, core, after.
    assert [u["id"] for u in middle["before"]] == ["u0"]
    assert [u["id"] for u in middle["core"]] == ["u1"]
    assert [u["id"] for u in middle["after"]] == ["u2"]
    # The halo shows the two spans nearest the owned core on each side, keyed by
    # the complete unit's span IDs, so a citation of a shown span resolves.
    before, after = middle["before"][0], middle["after"][0]
    p1_spans = source_spans("u0", PAGE["p1"])
    assert [s["id"] for s in before["spans"]] == [s["id"] for s in p1_spans[-2:]]
    assert [s["text"].strip() for s in before["spans"]] == [
        "Third sentence of page one.",
        "Fourth sentence of page one.",
    ]
    assert before["partial"].startswith("last 2 of 4 spans")
    assert [s["id"] for s in after["spans"]] == ["u2:s0", "u2:s1"]
    assert [s["text"].strip() for s in after["spans"]] == [
        "Page three begins here.",
        "Page three continues.",
    ]
    assert after["partial"].startswith("first 2 of 3 spans")
    first = next(
        r["input"] for r in provider.requests if core_text(r).startswith("First")
    )
    assert first["before"] == []
    assert first["after"][0]["partial"].startswith("first 2 of 3 spans")
    last = next(
        r["input"] for r in provider.requests if core_text(r).startswith("Page three")
    )
    assert last["after"] == []
    assert last["before"][0]["partial"].startswith("last 2 of 3 spans")
    # A unit with no more spans than the halo is shown complete, without a cut.
    wide = Provider(own_everything)
    run(tmp_path / "wide", wide, units, reader_context_spans=3)
    first = next(r["input"] for r in wide.requests if core_text(r).startswith("First"))
    assert "partial" not in first["after"][0]
    assert len(first["after"][0]["spans"]) == 3
    # The saved window records the halo and its cut for later inspection.
    saved = windows[1]
    assert saved["before"] == [units[0]["id"]] and saved["after"] == [units[2]["id"]]
    assert set(saved["partial"]) == {units[0]["id"], units[2]["id"]}


def test_halo_citation_resolves_against_the_full_neighbouring_unit(tmp_path):
    units = [unit(uid, text) for uid, text in PAGE.items()]

    def cite_halo(request):
        data = request["input"]
        core = data["core"][0]
        idea = {
            "title": "Idea with boundary support",
            "explanation": "Needs the previous page's last sentence.",
            "evidence_refs": [{"span_id": core["spans"][0]["id"]}],
        }
        if data["before"]:
            idea["evidence_refs"].append({"span_id": data["before"][0]["spans"][-1]["id"]})
        return {"ideas": [idea]}

    provider = Provider(cite_halo)
    _, ideas, _ = run(tmp_path, provider, units, reader_context_spans=1)
    second = ideas[1]
    assert second["unit_ids"] == [units[1]["id"]]
    assert second["support_unit_ids"] == [units[0]["id"]]
    quotes = {e["unit_id"]: e["quote"] for e in second["evidence"]}
    assert quotes[units[0]["id"]] == "Fourth sentence of page one."


def test_context_request_completes_partial_halo_before_stepping_to_next_group(tmp_path):
    units = [unit(uid, text) for uid, text in PAGE.items()]
    asked = []

    def ask_once(request):
        data = request["input"]
        if (
            core_text(request).startswith("Opening")
            and data["after"]
            and "partial" in data["after"][0]
        ):
            asked.append(data["after"][0]["partial"])
            return {
                "context_request": {
                    "direction": "after",
                    "reason": "The qualification continues on the next page",
                }
            }
        return own_everything(request)

    provider = Provider(ask_once)
    windows, ideas, _ = run(tmp_path, provider, units, reader_context_spans=1)
    assert len(asked) == 1
    saved = windows[1]
    assert saved["context_requests"] == [
        {
            "direction": "after",
            "reason": "The qualification continues on the next page",
            "unit_ids": [units[2]["id"]],
            "completed_partial": True,
        }
    ]
    # After completion the same unit is shown whole; no further unit was added.
    completed = [
        r["input"] for r in provider.requests if core_text(r).startswith("Opening")
    ]
    assert len(completed) == 2
    assert [u["id"] for u in completed[1]["after"]] == ["u2"]
    assert "partial" not in completed[1]["after"][0]
    assert len(completed[1]["after"][0]["spans"]) == 3
    assert len(ideas) == 3


def test_packing_measures_the_window_with_its_halo(tmp_path):
    units = [unit(uid, text) for uid, text in PAGE.items()]
    bare, haloed = Provider(own_everything), Provider(own_everything)
    run(tmp_path / "a", bare, units, reader_context_spans=0)
    run(tmp_path / "b", haloed, units, reader_context_spans=3)
    assert all(
        len(canonical(h).encode()) > len(canonical(b).encode())
        for b, h in zip(bare.requests, haloed.requests)
    )
    assert bare.requests[1]["input"]["before"] == []


def test_split_children_receive_a_fresh_inner_halo(tmp_path):
    units = [
        unit("a", "Alpha one. Alpha two."),
        unit("b", "Beta one. Beta two."),
        unit("c", "Gamma one. Gamma two."),
        unit("d", "Delta one. Delta two."),
    ]
    for row in units:
        row["section_id"], row["section_index"] = "s", 0

    class Truncating(Provider):
        def call(self, stage, request):
            self.requests.append(copy.deepcopy(request))
            if len(request["input"]["core"]) == 4:
                from lamina.providers import ProviderError

                raise ProviderError("too long", code="output_truncated")
            return own_everything(request)

    provider = Truncating(own_everything)
    windows, ideas, _ = run(tmp_path, provider, units, reader_context_spans=1)
    cores = {tuple(w["core"]): w for w in windows}
    assert set(cores) == {("a", "b"), ("c", "d")}
    assert cores[("a", "b")]["after"] == ["c"] and cores[("a", "b")]["before"] == []
    assert cores[("c", "d")]["before"] == ["b"] and cores[("c", "d")]["after"] == []
    assert len(ideas) == 4


def test_continue_mode_keeps_reading_and_reports_unresolved_windows(tmp_path):
    units = [unit(uid, text) for uid, text in PAGE.items()]

    def fail_middle(request):
        if core_text(request).startswith("Opening"):
            from lamina.providers import ProviderError

            raise ProviderError("adapter failed", code="adapter")
        return own_everything(request)

    with pytest.raises(ProductionError, match="reading batch.*unresolved"):
        run(tmp_path / "abort", Provider(fail_middle), units, reading_failures="abort")

    windows, ideas, unresolved = run(
        tmp_path / "continue", Provider(fail_middle), units, reading_failures="continue"
    )
    assert [w["core"] for w in windows] == [["p1"], ["p3"]]
    assert {idea["unit_ids"][0] for idea in ideas} == {"p1", "p3"}
    assert len(unresolved) == 1
    assert unresolved[0]["core"] == ["p2"]
    assert unresolved[0]["source_id"] == "source"
    assert "adapter failed" in unresolved[0]["error"]


def test_continue_mode_still_aborts_when_nothing_was_read(tmp_path):
    def fail_all(request):
        from lamina.providers import ProviderError

        raise ProviderError("adapter failed", code="adapter")

    with pytest.raises(ProductionError, match="reading batch.*unresolved"):
        run(
            tmp_path,
            Provider(fail_all),
            [unit("p1", PAGE["p1"])],
            reading_failures="continue",
        )


def test_unknown_reading_failure_policy_is_rejected():
    with pytest.raises(ProductionError, match="reading_failures"):
        _options({"reading_failures": "ignore"})
    with pytest.raises(ProductionError, match="reader_context_spans"):
        _options({"reader_context_spans": 65})


def test_level_zero_grouping_batches_keep_source_order():
    from tests.test_bounded_planning import ScriptedPlanner, corpus

    ideas, units = corpus(96, sources=4, topics=8)
    provider = ScriptedPlanner()
    plan_bounded(
        ideas,
        units,
        {"goal": "Compare operating conditions"},
        provider,
        max_bytes=12_000,
        workers=2,
    )
    level_zero = [
        call for call in provider.calls if call["item"].startswith("level_0_batch_")
    ]
    assert len(level_zero) > 1
    for call in level_zero:
        sources = [card["source_ids"][0] for card in call["data"]["cards"]]
        # Each batch is a run of consecutive source positions: one source, or a
        # source boundary crossed once. Round-robin interleaving would alternate.
        changes = sum(1 for a, b in zip(sources, sources[1:]) if a != b)
        assert changes <= 1, sources


def test_build_continues_past_a_failed_window_and_stays_in_review(tmp_path):
    from lamina.production import build_production
    from lamina.providers import ProviderError
    from tests.test_production import FixtureProvider, workspace

    class FailsOneRead(FixtureProvider):
        def call(self, stage, payload):
            if stage == "production_read" and payload["input"]["source"]["id"] == "s2":
                raise ProviderError("adapter failed", code="adapter")
            return super().call(stage, payload)

    ws = workspace(tmp_path)
    with pytest.raises(ProductionError, match="reading batch.*unresolved"):
        build_production(
            ws,
            FailsOneRead(),
            "Explain safety",
            ["s1", "s2"],
            {"workflow": "planned", "reading_failures": "abort"},
        )
    # The default policy continues.
    result = build_production(
        workspace(tmp_path / "continue"),
        FailsOneRead(),
        "Explain safety",
        ["s1", "s2"],
        {"workflow": "planned"},
    )
    plan = result["plan"]
    unresolved = plan["planning"]["unresolved_reads"]
    assert [row["source_id"] for row in unresolved] == ["s2"]
    assert plan["metrics"]["unresolved_reader_windows"] == 1
    assert {w["source_id"] for w in plan["windows"]} == {"s1"}
    assert {idea["unit_ids"][0] for idea in plan["ideas"]} <= {"u1", "u2"}
    # The artifact exists, every written section comes from what was read, and
    # the receipt stays in review because source material was never read.
    assert result["sections"]
    assert result["status"] == "review"
    assert result["unresolved_reads"] == unresolved
    assert result["metrics"]["unresolved_reader_windows"] == 1
    assert result["findings"] == {}
