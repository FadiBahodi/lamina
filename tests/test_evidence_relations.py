"""Deterministic relationship nomination and evidence transport fixtures."""

from copy import deepcopy

import pytest

from lamina.evidence_relations import (
    CandidateIndex,
    OriginalSourceIndex,
    compare_relations,
)
from lamina.call_runtime import CallTracker
from lamina.production_contract import ProductionError, _options
from lamina.production_example import fixture_request_budget
from lamina.store import Workspace
from test_production import FixtureProvider


def corpus():
    units, ideas = [], []
    for n, text in enumerate(
        [
            "Pump Orion stops below 10 kPa.",
            "Pump Orion has a cold-start exception.",
            "The cold-start exception applies only in test mode.",
        ]
    ):
        uid, iid = f"u{n}", f"i{n}"
        units.append(
            {
                "id": uid,
                "source_id": f"s{n}",
                "role": "teaching",
                "heading": "Record",
                "text": text,
            }
        )
        ideas.append(
            {
                "id": iid,
                "title": "Pump condition",
                "explanation": text,
                "unit_ids": [uid],
                "evidence": [{"unit_id": uid, "quote": text}],
            }
        )
    return ideas, units


def test_nomination_is_independent_of_input_order():
    ideas, units = corpus()
    first = CandidateIndex(ideas, units).nominate(20)
    second = CandidateIndex(list(reversed(ideas)), list(reversed(units))).nominate(20)
    assert first == second
    # Similarity nominates the two related pairs; the pair with no shared
    # content stays below the threshold and never costs a model call.
    assert [row["idea_ids"] for row in first] == [["i0", "i1"], ["i1", "i2"]]
    assert all(row["signals"] == ["similarity:tfidf"] for row in first)
    assert all(0 < row["score"] < 1 for row in first)


def test_nomination_uses_provider_embeddings_when_offered():
    ideas, units = corpus()

    class Embedding:
        def embed(self, texts):
            # i0 and i2 are placed together; i1 is orthogonal to both.
            return [[1.0, 0.0], [0.0, 1.0], [0.9, 0.1]][: len(texts)]

    index = CandidateIndex(ideas, units, Embedding())
    assert index.method == "embedding"
    rows = index.nominate(20)
    assert [row["idea_ids"] for row in rows] == [["i0", "i2"]]
    assert rows[0]["signals"] == ["similarity:embedding"]
    # Structural lanes still nominate ideas that cite the same unit.
    shared = [
        dict(
            idea,
            evidence=[{"unit_id": "u0", "quote": "Pump Orion stops below 10 kPa."}],
        )
        for idea in ideas
    ]
    lanes = CandidateIndex(shared, units, Embedding()).nominate(20)
    assert all("support" in row["signals"] for row in lanes)
    assert len(lanes) == 3


def test_comparator_reopens_third_source_and_carries_all_evidence(tmp_path):
    ideas, units = corpus()

    class Comparator(FixtureProvider):
        def nominate_relations(self, ideas, units, limit):
            return [["i0", "i1", "i2"]]

        def call(self, stage, payload):
            assert stage == "production_compare"
            data = payload["input"]
            members = {i["id"] for i in data["ideas"]}
            return {
                "kind": "different_conditions",
                "statement": "Low-pressure stop has a cold-start exception only in test mode.",
                "evidence": [
                    {"unit_id": u["id"], "quote": u["text"]} for u in data["passages"]
                ],
                "followup_queries": ["test mode"] if members == {"i0", "i1"} else [],
            }

    rows, report = compare_relations(
        Workspace(tmp_path),
        Comparator(),
        ideas,
        units,
        {"goal": "Explain the conditions"},
        _options(None),
        CallTracker(),
    )
    expanded = next(row for row in rows if len(row["searches"]) == 2)
    assert set(expanded["member_idea_ids"]) == {"i0", "i1", "i2"}
    assert {e["unit_id"] for e in expanded["evidence"]} == {"u0", "u1", "u2"}
    assert report["nomination_recall"] == "unmeasured"
    assert report["comparison_accuracy"] == "unmeasured"


# Recovery tests use exact original passages and a deterministic comparison
# adapter. They establish access, permissions, transport and reuse, not recall
# or semantic comparison accuracy of a live model.
def recovery_corpus():
    ideas, units = corpus()
    ideas = ideas[:2]
    units = units[:2]
    units.extend(
        [
            {
                "id": "middle",
                "source_id": "s2",
                "role": "teaching",
                "heading": "Other equipment",
                "locator": "page 18",
                "text": "Paint is blue.",
            },
            {
                "id": "far",
                "source_id": "s2",
                "role": "teaching",
                "heading": "Seal addendum",
                "locator": "page 93",
                "text": "The housing is grey. Legacyseal lots require a five bar limit.",
            },
        ]
    )
    return ideas, units


class RecoveryComparator(FixtureProvider):
    def __init__(self, query="legacyseal", max_items=1024, max_bytes=1_500_000):
        super().__init__()
        self.query, self.max_items, self.max_bytes = query, max_items, max_bytes

    def budget_for(self, stage):
        return fixture_request_budget(
            stage, max_items=self.max_items, max_request_bytes=self.max_bytes
        )

    def nominate_relations(self, ideas, units, limit):
        return [["i0", "i1"]]

    def call(self, stage, payload):
        self.requests.append((stage, deepcopy(payload)))
        data = payload["input"]
        seen = "legacyseal" in " ".join(u["text"] for u in data["passages"]).casefold()
        return {
            "kind": "different_conditions" if seen else "unresolved",
            "statement": (
                "Legacyseal lots require five bar."
                if seen
                else "Need the seal exception."
            ),
            "evidence": [
                {"unit_id": u["id"], "quote": u["text"]} for u in data["passages"]
            ],
            "followup_queries": [] if seen else [self.query],
        }


def recovery_run(tmp_path, provider, ideas, units, options=None):
    tracker = CallTracker()
    rows, report = compare_relations(
        Workspace(tmp_path),
        provider,
        ideas,
        units,
        {"goal": "Resolve the exception"},
        _options(options),
        tracker,
    )
    assert len(rows) == 1
    return rows[0], report, tracker


def test_original_index_reaches_omitted_unit_and_unquoted_suffix():
    ideas, units = recovery_corpus()
    # Neither title nor extracted explanation nor quote contains this qualifier.
    assert CandidateIndex(ideas, units).search("legacyseal", []) == []
    originals = OriginalSourceIndex(units)
    assert originals.search("legacyseal")[0]["unit_id"] == "far"
    # An idea may quote just the first sentence of a unit; search retains its tail.
    ideas.append(
        {
            "id": "i2",
            "title": "Housing",
            "explanation": "Grey housing",
            "unit_ids": ["far"],
            "evidence": [{"unit_id": "far", "quote": "The housing is grey."}],
        }
    )
    assert CandidateIndex(ideas, units).search("legacyseal", []) == []
    assert originals.search("legacyseal")[0]["locator"] == "page 93"
    assert originals.search("far")[0]["unit_id"] == "far"
    assert originals.search("Seal addendum")[0]["unit_id"] == "far"


def test_followup_reads_nonadjacent_unextracted_original_and_propagates_evidence(
    tmp_path,
):
    from lamina.production import _section_context

    ideas, units = recovery_corpus()
    provider = RecoveryComparator()
    row, report, _ = recovery_run(tmp_path, provider, ideas, units)
    assert row["kind"] == "different_conditions"
    assert row["member_idea_ids"] == ["i0", "i1"]  # no fabricated extracted idea
    assert row["reopened_unit_ids"] == ["far"]
    assert row["pending_unit_ids"] == []
    assert row["searches"][0]["read_status"] == "read"
    hit = row["searches"][0]["original_source_queries"][0]["hits"][0]
    assert (hit["unit_id"], hit["source_id"], hit["locator"]) == (
        "far",
        "s2",
        "page 93",
    )
    reopened = next(
        u for u in provider.requests[1][1]["input"]["passages"] if u["id"] == "far"
    )
    assert reopened["text"] == units[-1]["text"]
    assert reopened["policy"] == "authority"
    assert report["source_search_scope"]["unit_count"] == 4

    # Exercise the real downstream transport. The recovered original is context,
    # while the two extracted ideas retain their original source ownership.
    section = {
        "id": "section",
        "title": "Limits",
        "purpose": "Explain conditions",
        "idea_ids": ["i0", "i1"],
        "context_section_ids": [],
    }
    plan = {
        "brief": {"goal": "Explain"},
        "options": {"format": "guide"},
        "units": units,
        "ideas": [{**idea, "evidence_relations": [row]} for idea in ideas],
        "sources": [{"id": sid} for sid in ["s0", "s1", "s2"]],
        "route": {"title": "Limits", "sections": [section], "shared_context": []},
    }
    data, allowed = _section_context(plan, section)
    assert allowed["far"]["text"] == units[-1]["text"]
    assert data["shared_evidence_units"][-1]["id"] == "far"
    assert "far" not in {u["id"] for u in data["assigned_units"]}
    assert {"unit_id": "far", "quote": units[-1]["text"]} in data["evidence_relations"][
        0
    ]["evidence"]


def test_query_for_visible_suffix_is_reported_as_available_and_reread(tmp_path):
    ideas, units = recovery_corpus()
    units[0]["text"] += " Legacyseal lots require a five bar limit."

    class OnceMissed(RecoveryComparator):
        def call(self, stage, payload):
            result = super().call(stage, payload)
            if len(self.requests) == 1:
                result["followup_queries"] = ["legacyseal"]
            return result

    # Remove the nonadjacent hit: the answer is already in the visible unit's
    # unquoted tail. A recovery reread must not call this a failed source search.
    units = units[:2]
    row, _, _ = recovery_run(tmp_path, OnceMissed(), ideas, units)
    assert row["kind"] == "different_conditions"
    search = row["searches"][0]["original_source_queries"][0]
    assert search["hits"] == []
    assert search["already_visible_hits"][0]["unit_id"] == "u0"
    assert row["searches"][0]["read_status"] == "read"


def test_search_permissions_exclude_assessments_exemplars_and_unselected_sources(
    tmp_path,
):
    ideas, units = recovery_corpus()
    forbidden = [
        {**units[-1], "id": "heldout", "source_id": "exam", "role": "assessment"},
        {**units[-1], "id": "form", "source_id": "exemplar"},
        {**units[-1], "id": "outside", "source_id": "unselected"},
    ]
    policy = {
        "s0": "authority",
        "s1": "authority",
        "s2": "historical",
        "exam": "authority",
        "exemplar": "form_exemplar",
    }
    provider = RecoveryComparator()
    row, _, _ = recovery_run(
        tmp_path, provider, ideas, units + forbidden, {"source_policy": policy}
    )
    assert row["reopened_unit_ids"] == ["far"]
    for _, payload in provider.requests:
        assert not {u["id"] for u in payload["input"]["passages"]} & {
            "heldout",
            "form",
            "outside",
        }
    assert provider.requests[-1][1]["input"]["passages"][0]["policy"] == "historical"
    bad_ideas = deepcopy(ideas)
    bad_ideas[0]["evidence"][0]["unit_id"] = "heldout"
    with pytest.raises(ProductionError, match="selected factual teaching"):
        recovery_run(
            tmp_path / "bad",
            provider,
            bad_ideas,
            units + forbidden,
            {"source_policy": policy},
        )


def test_changed_previously_unextracted_source_invalidates_negative_search_cache(
    tmp_path,
):
    ideas, units = recovery_corpus()
    units[-1]["text"] = "The housing is grey."
    provider = RecoveryComparator()
    first, _, _ = recovery_run(tmp_path, provider, ideas, units)
    assert first["kind"] == "unresolved"
    assert first["unresolved_reason"] == "no_new_evidence"
    assert first["searches"][0]["found_unit_ids"] == []
    provider.requests.clear()
    same, _, tracker = recovery_run(tmp_path, provider, ideas, units)
    assert same == first
    assert provider.requests == []
    assert tracker.metrics()["cache_hits"] == 1
    units[-1]["text"] += " Legacyseal lots require a five bar limit."
    changed, _, tracker = recovery_run(tmp_path, provider, ideas, units)
    assert (
        changed["source_search_scope"]["digest"]
        != first["source_search_scope"]["digest"]
    )
    assert changed["kind"] == "different_conditions"
    assert len(provider.requests) == 2
    assert tracker.metrics()["cache_hits"] == 0


@pytest.mark.parametrize("change", ["add", "remove", "policy"])
def test_search_scope_tracks_collection_and_permission_changes(tmp_path, change):
    ideas, units = recovery_corpus()
    policy = {"s0": "authority", "s1": "authority", "s2": "authority"}
    before = OriginalSourceIndex(units, policy).scope["digest"]
    if change == "add":
        units.append({**units[-1], "id": "another", "text": "No new distinction."})
    elif change == "remove":
        units.pop()
    else:
        policy["s2"] = "historical"
    assert OriginalSourceIndex(units, policy).scope["digest"] != before
    # Input ordering alone does not alter scope identity.
    assert (
        OriginalSourceIndex(units, policy).scope
        == OriginalSourceIndex(list(reversed(units)), policy).scope
    )


@pytest.mark.parametrize("limit", ["items", "bytes"])
def test_oversized_followup_remains_unresolved_without_trimming_source(tmp_path, limit):
    ideas, units = recovery_corpus()
    provider = RecoveryComparator(
        max_items=2 if limit == "items" else 1024, max_bytes=12000
    )
    if limit == "bytes":
        units[-1]["text"] += " Complete source structure." * 1000
    row, _, tracker = recovery_run(tmp_path, provider, ideas, units)
    assert row["kind"] == "unresolved"
    assert row["unresolved_reason"] == "followup_request_budget"
    assert row["searches"][0]["read_status"] == "budget_exceeded"
    assert row["pending_unit_ids"] == ["far"]
    assert row["reopened_unit_ids"] == []
    assert len(provider.requests) == 1
    assert tracker.metrics()["failed_requests"] == 0


def test_repeated_followups_stop_at_explicit_comparison_limit(tmp_path):
    ideas, units = recovery_corpus()

    class NeverSettled(RecoveryComparator):
        def call(self, stage, payload):
            result = super().call(stage, payload)
            result["followup_queries"] = ["legacyseal"]
            return result

    provider = NeverSettled()
    row, _, _ = recovery_run(tmp_path, provider, ideas, units)
    assert len(provider.requests) == 3
    assert row["kind"] == "unresolved"
    assert row["unresolved_reason"] == "followup_limit"
