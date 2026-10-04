"""Properties the engine promises, checked on generated inputs.

Each test states one invariant from the documentation and lets Hypothesis
search for a counterexample. These are the contracts code enforces; model
quality is outside their reach.
"""

from __future__ import annotations

import re

from hypothesis import given, settings, strategies as st

from lamina.geometry import analyse
from lamina.production_contract import ProductionError, _read_check
from lamina.similarity import (
    discriminators,
    normalised,
    same_meaning_guard,
    suppress_duplicates,
    term_vectors,
)
from lamina.source_spans import source_spans

text = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00"),
    min_size=0,
    max_size=400,
)
prose = st.lists(
    st.sampled_from(
        ["The limit is eight bar.", "Older seals are limited to five bar.", "Check the gauge first!",
         "Does the exception apply?", "Give 0.1 mg IV.", "No pressure was observed.", "Dr. Smith agreed."]
    ),
    min_size=1,
    max_size=12,
).map(" ".join)


@settings(max_examples=300)
@given(text)
def test_spans_partition_the_source_text_exactly(body):
    """Every character of a unit belongs to exactly one span, in order, so a
    cited range reconstructs the original byte for byte."""
    spans = source_spans("u", body)
    assert "".join(body[s["start"]:s["end"]] for s in spans) == body
    assert all(spans[i]["end"] == spans[i + 1]["start"] for i in range(len(spans) - 1))
    assert all(s["end"] > s["start"] for s in spans)
    assert (spans[0]["start"] == 0 and spans[-1]["end"] == len(body)) if spans else body == ""
    assert [s["id"] for s in spans] == [f"u:s{i}" for i in range(len(spans))]


@settings(max_examples=200)
@given(prose, st.integers(min_value=1, max_value=6), st.sampled_from(["head", "tail"]))
def test_a_reader_can_cite_exactly_the_halo_spans_it_was_shown(neighbour_text, shown, side):
    """With a halo cut to ``shown`` spans of a neighbouring unit, every shown
    span resolves and every hidden span is rejected as foreign."""
    core = [{"id": "core", "text": "Owned sentence one. Owned sentence two.", "heading": "H", "role": "teaching"}]
    spans = source_spans("ctx", neighbour_text)
    context = [{"id": "ctx", "text": neighbour_text, "heading": "H", "role": "teaching",
                "visible_cut": {"side": side, "spans": shown}}]
    visible = spans[:shown] if side == "head" else spans[max(0, len(spans) - shown):]
    hidden = [s for s in spans if s not in visible]

    def idea(span_id):
        return {"ideas": [{"title": "t", "explanation": "e",
                           "evidence_refs": [{"span_id": "core:s0"}, {"span_id": span_id}]}]}

    for span in visible:
        checked = _read_check(idea(span["id"]), core, "w", context)
        assert checked["ideas"][0]["support_unit_ids"] == ["ctx"]
    for span in hidden:
        try:
            _read_check(idea(span["id"]), core, "w", context)
        except ProductionError:
            continue
        raise AssertionError(f"hidden span {span['id']} was accepted")


@settings(max_examples=300)
@given(prose)
def test_identical_cards_always_collapse_and_a_card_never_merges_with_itself_changed(body):
    texts = [body, body, body.upper()]
    kept, suppressed, related = suppress_duplicates(term_vectors(texts), 0.0, texts)
    assert kept == [0] and set(suppressed) == {1, 2}
    assert all(row["kind"] == "exact" for row in suppressed.values())
    assert same_meaning_guard(body, body) is None
    assert normalised(normalised(body)) == normalised(body)


number = st.from_regex(r"[0-9]{1,3}(\.[0-9]{1,2})?", fullmatch=True)


@settings(max_examples=300)
@given(prose, number, number)
def test_similarity_cannot_delete_a_card_whose_number_differs(body, a, b):
    """Two cards that differ only in a numeric literal are never merged,
    whatever their vector similarity."""
    if a == b:
        return
    x, y = f"{body} Give {a} mg.", f"{body} Give {b} mg."
    assert same_meaning_guard(x, y) == "numbers"
    kept, suppressed, related = suppress_duplicates(term_vectors([x, y]), 0.0, [x, y])
    assert kept == [0, 1] and suppressed == {}
    assert related[1]["kept_because"] == "numbers"


@settings(max_examples=200)
@given(prose, st.sampled_from(["no", "not", "never", "without", "contraindicated"]))
def test_similarity_cannot_delete_a_card_whose_negation_differs(body, negation):
    x, y = f"{body} This is {negation} indicated.", f"{body} This is indicated."
    assert same_meaning_guard(x, y) == "negation"
    kept, suppressed, _ = suppress_duplicates(term_vectors([x, y]), 0.0, [x, y])
    assert kept == [0, 1] and suppressed == {}


@settings(max_examples=200)
@given(prose, st.from_regex(r"[A-Z]{2,4}", fullmatch=True), st.from_regex(r"[A-Z]{2,4}", fullmatch=True))
def test_similarity_cannot_delete_a_card_whose_abbreviation_differs(body, p, q):
    if p == q:
        return
    x, y = f"{body} Route: {p}.", f"{body} Route: {q}."
    assert discriminators(x)["short"] != discriminators(y)["short"]
    kept, suppressed, _ = suppress_duplicates(term_vectors([x, y]), 0.0, [x, y])
    assert kept == [0, 1] and suppressed == {}


call = st.tuples(
    st.sampled_from(["production_read", "production_group", "production_write", "production_review"]),
    st.integers(min_value=0, max_value=5000),
    st.integers(min_value=1, max_value=3000),
)


@settings(max_examples=200)
@given(st.lists(call, min_size=1, max_size=40), st.integers(min_value=1, max_value=32))
def test_the_schedule_bound_never_exceeds_the_measured_span(calls, workers):
    """For any set of timed calls, max(W/P, D) ≤ span when P is at least the
    peak in flight, and the critical path fits inside the span. The bound is
    a lower bound on wall time by construction; this checks the arithmetic
    and the dependency resolution never claim otherwise."""
    records = []
    for index, (stage, start, duration) in enumerate(calls):
        records.append({
            "stage": stage, "item": f"i{index}", "started_ms": start, "ended_ms": start + duration,
            "cache": "miss", "status": "completed", "after": [],
            "attempts": [{"started_ms": start, "wall_ms": duration, "status": "completed"}],
            "request_bytes": 1,
        })
    g = analyse(records, workers=workers)
    assert g["critical_path_ms"] <= g["span_ms"] + 1e-6
    assert g["model_ms"] <= g["peak_in_flight"] * g["span_ms"] + 1e-6
    if workers >= g["peak_in_flight"]:
        assert g["bound_ms"] <= g["span_ms"] + 1e-6
    assert g["edges"]["declared"] + g["edges"]["implied"] + g["edges"]["roots"] == g["calls"]
    assert re.fullmatch(r"critical_path|work_over_workers", g["bound_binding"])


def _route(sections, omitted):
    return {
        "title": "T",
        "summary": "S",
        "sections": [
            {
                "id": f"s{i}",
                "title": f"Section {i}",
                "purpose": "p",
                "idea_ids": ids,
                "representation": {"kind": "reference", "rationale": "r", "requirements": []},
            }
            for i, ids in enumerate(sections)
            if ids
        ],
        "omitted": [{"idea_id": i, "reason": "out of scope"} for i in omitted],
        "shared_context": [],
    }


idea_pool = st.lists(st.from_regex(r"i[0-9]{1,2}", fullmatch=True), min_size=1, max_size=12, unique=True)


@settings(max_examples=300)
@given(idea_pool, st.data())
def test_every_idea_has_exactly_one_owner_or_an_explicit_omission(ideas, data):
    """The outline check accepts a route only when the assigned sets and the
    omitted set partition the extracted ideas: no idea in two sections, none
    assigned and omitted, none forgotten, none invented."""
    from lamina.production_contract import _route_check

    cut = data.draw(st.integers(min_value=0, max_value=len(ideas)))
    assigned, omitted = ideas[:cut], ideas[cut:]
    pieces = data.draw(st.integers(min_value=1, max_value=max(1, len(assigned))))
    sections = [assigned[k::pieces] for k in range(pieces)]
    if not any(sections):
        sections = [[omitted.pop()]] if omitted else sections
    route = _route(sections, omitted)
    if not route["sections"]:
        return
    checked = _route_check(route, set(ideas), {})
    owners = [i for s in checked["sections"] for i in s["idea_ids"]]
    assert sorted(owners + [o["idea_id"] for o in checked["omitted"]]) == sorted(ideas)
    assert len(owners) == len(set(owners))
    # Perturbations that break the partition are rejected.
    broken = []
    if owners:
        twice = _route(sections + [[owners[0]]], omitted)
        broken.append(twice)
        forgotten = _route(sections, omitted[1:]) if omitted else _route(
            [s[1:] if s and s[0] == owners[0] else s for s in sections], omitted
        )
        broken.append(forgotten)
        invented = _route(sections + [["i999"]], omitted)
        broken.append(invented)
        both = _route(sections, omitted + [owners[0]])
        broken.append(both)
    for candidate in broken:
        if not candidate["sections"]:
            continue
        try:
            _route_check(candidate, set(ideas), {})
        except ProductionError:
            continue
        raise AssertionError(f"accepted a route that breaks the partition: {candidate}")
