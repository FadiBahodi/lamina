"""Source addresses and repair mechanics; these tests do not establish recall."""

import copy

import pytest

from lamina.call_runtime import CallTracker
from lamina.context_budget import RequestBudget
from lamina.evidence import ValidationFailure
from lamina.production_contract import ProductionError, _SHAPES, _read_check, validated
from lamina.source_reading import ReaderReplyValidator, read_sources, reader_input
from lamina.source_spans import materialize_references, source_spans
from lamina.store import Workspace, canonical
from lamina.workload_profiles import WorkloadProfile


def unit(uid="u0", text="Do not proceed unless wind speed is below 12 m/s.", **extra):
    return {
        "id": uid,
        "source_id": "source",
        "heading": "Operation",
        "text": text,
        "role": "teaching",
        "content_id": "content-" + uid,
        **extra,
    }


def idea(ref, title="Operating limit", **extra):
    return {
        "title": title,
        "explanation": "Stop above the operating threshold.",
        "evidence_refs": [ref],
        **extra,
    }


def addressed_text(row):
    return "".join(span["text"] for span in row["spans"])


def options(**extra):
    return {
        "reading": "task",
        "format": "document",
        "workers": 1,
        "reader_workers": 1,
        "max_request_bytes": 100_000,
        **extra,
    }


class Provider:
    identity = "source-reference-fixture"

    def __init__(self, handler=None, workload=None):
        self.requests = []
        self.handler = handler
        self.budget = RequestBudget(100_000, workload=workload)

    def budget_for(self, stage):
        return self.budget

    def call(self, stage, request):
        self.requests.append(copy.deepcopy(request))
        if self.handler:
            return self.handler(request)
        return {
            "ideas": [
                idea(
                    {
                        "span_id": u["spans"][0]["id"],
                        "end_span_id": u["spans"][-1]["id"],
                    }
                )
                for u in request["input"]["core"]
            ]
        }


def run_read(tmp_path, provider, units, *, tracker=None, ws=None, **overrides):
    return read_sources(
        ws or Workspace(tmp_path),
        provider,
        {"goal": "Explain operation"},
        options(**overrides),
        [{"id": "source", "title": "Wind", "filename": "wind.md"}],
        units,
        tracker or CallTracker(),
    )


def test_spans_preserve_abbreviations_conditions_and_unicode_offsets():
    text = "Dr. A. uses 2.5 mg, i.e. the lower amount. Only if stable.\r\n\r\nDo not repeat if K⁺ < 3.5."
    spans = source_spans("u0", text)
    assert len(spans) == 3
    assert "".join(text[s["start"] : s["end"]] for s in spans) == text
    result = materialize_references(
        [{"span_id": spans[0]["id"], "end_span_id": spans[-1]["id"]}],
        {"u0": unit(text=text)},
    )
    assert result == [{"unit_id": "u0", "quote": text}]


@pytest.mark.parametrize("kind", ["table", "bullet_list", "ordered_list", "fence"])
def test_parser_owned_structures_remain_one_span(kind):
    text = "First condition\n\nSecond condition\n\nException"
    assert source_spans("u0", text, kind) == [
        {"id": "u0:s0", "start": 0, "end": len(text)}
    ]


@pytest.mark.parametrize(
    "reference,code",
    [
        ({"span_id": "foreign:s0"}, "foreign_span"),
        ({"span_id": "u0:s1", "end_span_id": "u0:s0"}, "invalid_span_range"),
        ({"span_id": "u0:s0", "end_span_id": "u1:s0"}, "invalid_span_range"),
        ({"span_id": "u0:s0", "phrase": "absent"}, "ambiguous_or_missing_phrase"),
    ],
)
def test_invalid_or_foreign_addresses_are_rejected(reference, code):
    with pytest.raises(ValidationFailure) as failure:
        materialize_references(
            reference and [reference],
            {"u0": unit(text="first\n\nsecond"), "u1": unit("u1")},
        )
    assert failure.value.code == code


def test_phrase_is_exact_and_unambiguous_within_its_address():
    own = {"u0": unit(text="same same\n\nDo not exceed 12.")}
    with pytest.raises(ValidationFailure, match="exactly once"):
        materialize_references([{"span_id": "u0:s0", "phrase": "same"}], own)
    assert (
        materialize_references(
            [{"span_id": "u0:s1", "phrase": "Do not exceed 12."}], own
        )[0]["quote"]
        == "Do not exceed 12."
    )


def test_reader_resolves_references_and_accepts_legacy_quotes():
    owned = unit(text="first sentence. Its exception matters.\n\nAnother claim.")
    raw = {"ideas": [idea({"span_id": "u0:s0", "end_span_id": "u0:s2"})]}
    result = _read_check(raw, [owned], "w")
    assert result["ideas"][0]["evidence"] == [{"unit_id": "u0", "quote": owned["text"]}]
    assert result["ideas"][0]["unit_ids"] == ["u0"]
    legacy = {
        "title": "Legacy",
        "explanation": "Still accepted",
        "unit_ids": ["u0"],
        "evidence": [{"unit_id": "u0", "quote": "Another claim."}],
    }
    assert (
        _read_check({"ideas": [legacy]}, [owned], "w")["ideas"][0]["title"] == "Legacy"
    )


def test_source_text_occurs_once_in_reader_input():
    owned = unit(text="A distinctive source passage.")
    data, aliases = reader_input(
        {"id": "w", "core": [owned], "before": [], "after": []},
        {"id": "source", "filename": "wind.md"},
        {"goal": "Explain"},
        options(),
    )
    assert canonical(data).count(owned["text"]) == 1
    assert "text" not in data["core"][0]
    assert addressed_text(data["core"][0]) == owned["text"]
    assert data["core"][0]["spans"][0]["id"] == aliases[owned["id"]] + ":s0"


def test_delta_repair_retains_valid_rows_and_caches_the_merged_result(tmp_path):
    owned = unit()
    good = idea({"span_id": "u0:s0"}, title="KEEP THIS VALID ROW")
    bad = idea(
        {"span_id": "u0:s0", "phrase": "not in source"}, title="Repair only this"
    )
    replies = iter(
        [
            {"ideas": [good, bad]},
            {
                "replacements": [
                    {
                        "index": 1,
                        "idea": idea({"span_id": "u0:s0"}, title="Repair only this"),
                    }
                ]
            },
        ]
    )
    provider = Provider(lambda _: next(replies))
    validator = ReaderReplyValidator(
        lambda raw: validated(_read_check, raw, [owned], "w")
    )
    tracker, ws = CallTracker(), Workspace(tmp_path)

    def call():
        return tracker.call(
            ws,
            provider,
            "production_read",
            "w",
            "Read",
            _SHAPES["production_read"],
            {"core": [owned]},
            validator,
            100_000,
            repair_request=validator.repair_request,
            workload_items=1,
        )

    result = call()
    assert result["ideas"][0]["title"] == "KEEP THIS VALID ROW"
    assert [r["id"] for r in result["ideas"]] == ["w:idea_1", "w:idea_2"]
    repair = provider.requests[1]
    assert "KEEP THIS VALID ROW" not in canonical(repair)
    assert repair["input"]["repair"]["preserved_idea_count"] == 1
    assert [r["index"] for r in repair["input"]["repair"]["invalid_ideas"]] == [1]
    assert call() == result
    assert len(provider.requests) == 2
    assert tracker.metrics()["recovered_requests"] == 1


def test_reader_range_repair_names_cross_unit_and_reversed_endpoints():
    owned = [
        unit("u0", "First sentence. Second sentence."),
        unit("u1", "Third sentence. Fourth sentence."),
    ]
    raw = {
        "ideas": [
            idea({"span_id": "u0:s1", "end_span_id": "u1:s0"}),
            idea(
                {"span_id": "u1:s1", "end_span_id": "u1:s0"},
                title="Reversed range",
            ),
        ]
    }
    validator = ReaderReplyValidator(
        lambda value: validated(_read_check, value, owned, "w")
    )

    with pytest.raises(ValidationFailure) as failure:
        validator(raw)
    repair = validator.repair_request({"input": {}}, failure.value)

    guidance = [
        row["reference_guidance"][0]
        for row in repair["input"]["repair"]["invalid_ideas"]
    ]
    assert "u0:s1 -> u1:s0 crosses source units" in guidance[0]
    assert "use multiple evidence_refs" in guidance[0]
    assert "u1:s1 -> u1:s0 is reversed" in guidance[1]
    assert "select or reorder the endpoints" in guidance[1]
    assert "increasing span order" in repair["validation_feedback"]["instruction"]


def test_delta_cannot_replace_valid_rows_or_drop_unresolved_rows(tmp_path):
    good = idea({"span_id": "u0:s0"}, title="Kept")
    bad = idea({"span_id": "u0:s0", "phrase": "not there"})
    replies = iter(
        [{"ideas": [good, bad]}, {"replacements": [{"index": 0, "idea": good}]}]
    )
    provider = Provider(lambda _: next(replies))
    validator = ReaderReplyValidator(
        lambda raw: validated(_read_check, raw, [unit()], "w")
    )
    with pytest.raises(ValidationFailure) as failure:
        CallTracker().call(
            Workspace(tmp_path),
            provider,
            "production_read",
            "w",
            "Read",
            _SHAPES["production_read"],
            {"core": [unit()]},
            validator,
            100_000,
            repair_request=validator.repair_request,
        )
    assert failure.value.partial_results["ideas"][0]["title"] == "Kept"
    assert failure.value.partial_results["invalid_ideas"][0]["index"] == 1


def test_later_delta_preserves_rows_fixed_by_the_preceding_attempt(tmp_path):
    valid = idea({"span_id": "u0:s0"}, title="Original valid row")
    invalid = idea({"span_id": "u0:s0", "phrase": "missing"})
    first_fix = idea({"span_id": "u0:s0"}, title="First repaired row")
    second_fix = idea({"span_id": "u0:s0"}, title="Second repaired row")
    replies = iter(
        [
            {"ideas": [valid, invalid, invalid]},
            {
                "replacements": [
                    {"index": 1, "idea": first_fix},
                    {"index": 2, "idea": invalid},
                ]
            },
            {"replacements": [{"index": 2, "idea": second_fix}]},
        ]
    )
    provider = Provider(lambda _: next(replies))
    validator = ReaderReplyValidator(
        lambda raw: validated(_read_check, raw, [unit()], "w")
    )
    result = CallTracker(max_attempts=3).call(
        Workspace(tmp_path),
        provider,
        "production_read",
        "w",
        "Read",
        _SHAPES["production_read"],
        {"core": [unit()]},
        validator,
        100_000,
        repair_request=validator.repair_request,
    )
    assert [row["title"] for row in result["ideas"]] == [
        "Original valid row",
        "First repaired row",
        "Second repaired row",
    ]
    assert provider.requests[2]["input"]["repair"]["preserved_idea_count"] == 2
    assert [
        row["index"] for row in provider.requests[2]["input"]["repair"]["invalid_ideas"]
    ] == [2]
    assert "First repaired row" not in canonical(provider.requests[2])


def test_unprofiled_reading_uses_structural_groups_and_preserves_slide_parts(tmp_path):
    provider = Provider()
    rows = [
        unit("a", "Slide title", structural_group="slide:1"),
        unit("b", "Slide table", structural_group="slide:1"),
        unit("c", "Separate paragraph"),
    ]
    windows, ideas = run_read(tmp_path, provider, rows)
    assert [len(w["core"]) for w in windows] == [2, 1]
    assert [r["workload_items"] for r in provider.requests] == [2, 1]
    assert len(ideas) == 3


def test_unprofiled_reading_batches_contiguous_prose_by_section(tmp_path):
    provider = Provider()
    rows = [
        unit(
            f"u{index}",
            f"Section text {index}.",
            section_id="section-a" if index < 10 else "section-b",
            section_index=0 if index < 10 else 1,
        )
        for index in range(12)
    ]
    windows, ideas = run_read(tmp_path, provider, rows)
    assert [[uid for uid in window["core"]] for window in windows] == [
        [f"u{index}" for index in range(8)],
        ["u8", "u9"],
        ["u10", "u11"],
    ]
    assert [request["workload_items"] for request in provider.requests] == [8, 2, 2]
    assert len(ideas) == 12


def test_section_batching_still_obeys_complete_request_budget(tmp_path):
    class SmallBudgetProvider(Provider):
        def budget_for(self, stage):
            # A deterministic fixture ceiling for the complete serialized request;
            # it is not a supported model workload size.
            return RequestBudget(3_250)

    provider = SmallBudgetProvider()
    rows = [
        unit(
            f"u{index}",
            "A bounded paragraph with enough source text to affect the complete request. "
            * 3,
            section_id="section-a",
            section_index=0,
        )
        for index in range(4)
    ]
    windows, _ = run_read(tmp_path, provider, rows)
    assert len(windows) > 1
    assert all(request["input"]["core"] for request in provider.requests)
    assert all(len(canonical(request).encode()) <= 3_250 for request in provider.requests)


def test_profile_limits_owned_span_count_independently_of_context_capacity(tmp_path):
    provider = Provider(workload=WorkloadProfile(stage="production_read", max_items=2))
    windows, ideas = run_read(tmp_path, provider, [unit("a"), unit("b"), unit("c")])
    assert [len(w["core"]) for w in windows] == [2, 1]
    assert len(ideas) == 3


def test_cached_local_references_rebind_to_current_source_revision(tmp_path):
    ws, provider = Workspace(tmp_path), Provider()
    first = run_read(tmp_path, provider, [unit("old")], ws=ws)
    second = run_read(tmp_path, provider, [unit("new")], ws=ws)
    assert len(provider.requests) == 1
    assert first[1][0]["evidence"][0]["unit_id"] == "old"
    assert second[1][0]["evidence"][0]["unit_id"] == "new"


def test_context_request_keeps_ownership_and_is_cached(tmp_path):
    def handler(request):
        data = request["input"]
        if addressed_text(data["core"][0]) == "Only in that condition." and not data["before"]:
            return {
                "context_request": {
                    "direction": "before",
                    "reason": "Need the preceding condition",
                }
            }
        return {"ideas": [idea({"span_id": u["spans"][0]["id"]}) for u in data["core"]]}

    ws, provider = Workspace(tmp_path), Provider(handler)
    rows = [
        unit("a", "Wind is below the threshold."),
        unit("b", "Only in that condition."),
    ]
    windows, ideas = run_read(tmp_path, provider, rows, ws=ws)
    assert len(provider.requests) == 3
    assert windows[1]["before"] == ["a"]
    assert ideas[1]["unit_ids"] == ["b"]
    run_read(tmp_path, provider, rows, ws=ws)
    assert len(provider.requests) == 3


def test_context_request_adds_one_complete_adjacent_section_group(tmp_path):
    def handler(request):
        data = request["input"]
        if addressed_text(data["core"][0]) == "Needs the next section." and not data["after"]:
            return {
                "context_request": {
                    "direction": "after",
                    "reason": "The next section defines the operating condition",
                }
            }
        return {
            "ideas": [idea({"span_id": row["spans"][0]["id"]}) for row in data["core"]]
        }

    provider = Provider(handler)
    rows = [
        unit("a", "Needs the next section.", section_id="first", section_index=0),
        unit("b", "Condition part one.", section_id="second", section_index=1),
        unit("c", "Condition part two.", section_id="second", section_index=1),
        unit("d", "Later material.", section_id="third", section_index=2),
    ]
    windows, ideas = run_read(tmp_path, provider, rows)
    first = next(window for window in windows if window["core"] == ["a"])
    assert first["after"] == ["b", "c"]
    assert first["context_requests"][0]["unit_ids"] == ["b", "c"]
    assert next(row for row in ideas if row["unit_ids"] == ["a"])


def test_context_requests_stop_after_two_adjacent_group_extensions(tmp_path):
    def handler(request):
        data = request["input"]
        if addressed_text(data["core"][0]) == "Keep asking for context.":
            return {
                "context_request": {
                    "direction": "after",
                    "reason": "Fixture requests another source section",
                }
            }
        return {
            "ideas": [idea({"span_id": row["spans"][0]["id"]}) for row in data["core"]]
        }

    provider = Provider(handler)
    rows = [
        unit("a", "Keep asking for context.", section_id="first", section_index=0),
        unit("b", "Second section.", section_id="second", section_index=1),
        unit("c", "Third section.", section_id="third", section_index=2),
        unit("d", "Fourth section.", section_id="fourth", section_index=3),
    ]
    with pytest.raises(ProductionError, match="more than two adjacent context groups"):
        run_read(tmp_path, provider, rows)
    requests = [
        request
        for request in provider.requests
        if addressed_text(request["input"]["core"][0]) == "Keep asking for context."
    ]
    assert len(requests) == 3
    assert [[addressed_text(row) for row in request["input"]["after"]] for request in requests] == [
        [],
        ["Second section."],
        ["Second section.", "Third section."],
    ]
