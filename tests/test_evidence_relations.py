"""Deterministic relationship nomination and evidence transport fixtures."""

from lamina.evidence_relations import CandidateIndex, compare_relations
from lamina.call_runtime import CallTracker
from lamina.production_contract import _options
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
    shared = [dict(idea, evidence=[{"unit_id": "u0", "quote": "Pump Orion stops below 10 kPa."}]) for idea in ideas]
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
