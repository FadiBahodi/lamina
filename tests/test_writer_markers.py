from __future__ import annotations

import pytest

from lamina.context_binding import bind_context, restore_references
from lamina.evidence import ValidationFailure
from lamina.production_contract import ProductionError, _authored_check
from lamina.source_spans import source_spans
from lamina.writer_markers import materialize_marked_body


def fixture_units():
    return {
        "original-unit": {
            "id": "original-unit",
            "source_id": "original-source",
            "heading": "Mechanism",
            "kind": "paragraph",
            "role": "teaching",
            "text": "Wind turns the blades. The shaft drives the generator.",
        }
    }


def bound_units():
    data = {
        "assigned_units": [fixture_units()["original-unit"]],
        "earlier_evidence_units": [],
        "shared_evidence_units": [],
    }
    return bind_context(data, fixture_units())


def test_binding_presents_each_source_character_once_with_compact_aliases():
    data, units, reverse = bound_units()
    addressed = data["assigned_units"][0]
    assert "text" not in addressed
    assert addressed["addressed_text"] == (
        "[s0]Wind turns the blades. [s1]The shaft drives the generator."
    )
    assert addressed["addressed_text"].count("Wind turns the blades.") == 1
    assert [span["id"] for span in units["unit:0"]["spans"]] == ["s0", "s1"]
    assert restore_references({"span_id": "s1"}, reverse) == {
        "span_id": "original-unit:s1"
    }


def test_indented_markdown_code_stays_one_source_span():
    text = "    first.call()\n    second.call()"
    assert source_spans("code", text, "code_block") == [
        {"id": "code:s0", "start": 0, "end": len(text)}
    ]


def test_markers_are_removed_and_exact_evidence_is_derived():
    _, units, _ = bound_units()
    result = materialize_marked_body(
        "Blades capture the wind.[s0] The shaft transfers rotation.[s1]", units
    )
    assert result["body"] == "Blades capture the wind. The shaft transfers rotation."
    assert result["evidence"] == [
        {"unit_id": "unit:0", "quote": "Wind turns the blades. "},
        {"unit_id": "unit:0", "quote": "The shaft drives the generator."},
    ]
    assert [claim["text"] for claim in result["claims"]] == [
        "Blades capture the wind.",
        "The shaft transfers rotation.",
    ]


def test_marker_before_punctuation_removes_only_redundant_seam_space():
    _, units, _ = bound_units()
    result = materialize_marked_body(
        "First statement [s0].  Second statement [s1].", units
    )
    assert result["body"] == "First statement.  Second statement."
    assert [claim["text"] for claim in result["claims"]] == [
        "First statement.",
        "Second statement.",
    ]
    assert all(claim["text"] in result["body"] for claim in result["claims"])


def test_marker_without_following_punctuation_preserves_authored_space():
    _, units, _ = bound_units()
    result = materialize_marked_body("Statement [s0] with continuation.", units)
    assert result["body"] == "Statement  with continuation."
    assert result["claims"][0]["text"] == "Statement"


@pytest.mark.parametrize(
    "marker", ["[s0,s1]", "[s0, s1]", "[ s0 , s1 ]", "[s0-s1]", "[s0 - s1]", "[s0–s1]", "[s0 – s1]"]
)
def test_marker_spacing_and_en_dash_resolve_authorized_spans(marker):
    _, units, _ = bound_units()
    result = materialize_marked_body(f"Supported statement.{marker}", units)
    assert result["body"] == "Supported statement."
    assert {row["unit_id"] for row in result["evidence"]} == {"unit:0"}
    assert "".join(row["quote"] for row in result["evidence"]) == (
        "Wind turns the blades. The shaft drives the generator."
    )


def test_nested_list_prose_is_not_mistaken_for_indented_code():
    _, units, _ = bound_units()
    result = materialize_marked_body(
        "- Parent point\n    - Supported nested point.[s0]", units
    )
    assert result["body"] == "- Parent point\n    - Supported nested point."


def test_actual_indented_code_remains_protected():
    _, units, _ = bound_units()
    with pytest.raises(ValidationFailure) as raised:
        materialize_marked_body("    literal [s0]\n", units)
    assert raised.value.code == "protected_writer_marker"


def test_clinical_less_than_and_greater_than_are_not_html():
    _, units, _ = bound_units()
    result = materialize_marked_body(
        "Treat angulation <60 degrees and displacement >50%.[s0]", units
    )
    assert result["body"] == "Treat angulation <60 degrees and displacement >50%."


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ("A claim.[s9]", "foreign_writer_span"),
        ("A claim.[s1-s0]", "invalid_writer_span_range"),
        ("A claim.[s0-bad]", "missing_writer_marker"),
        ("`literal [s0]`", "protected_writer_marker"),
        ("[link](https://example.test/[s0])", "protected_writer_marker"),
        ("[label [s0]](https://example.test)", "protected_writer_marker"),
        ("![alt [s0]](diagram.png)", "protected_writer_marker"),
        ("[ref]: https://example.test/[s0]", "protected_writer_marker"),
        ('<span data-source="[s0]">text</span>', "protected_writer_marker"),
        ("<!-- literal [s0] -->", "protected_writer_marker"),
        ("<https://example.test/[s0]>", "protected_writer_marker"),
        ("A claim.[s0]Next claim.", "adjacent_writer_marker_text"),
        ("A claim.[idea:3]", "foreign_writer_span"),
        ("A claim.[unit:0]", "foreign_writer_span"),
    ],
)
def test_invalid_or_content_bearing_markers_are_rejected(body, code):
    _, units, _ = bound_units()
    with pytest.raises(ValidationFailure) as raised:
        materialize_marked_body(body, units)
    assert raised.value.code == code


def test_escaped_compact_marker_round_trips_as_literal_markdown():
    _, units, _ = bound_units()
    result = materialize_marked_body(
        r"The notation \[s0] is literal, while this claim is supported.[s1]", units
    )
    assert result["body"] == (
        r"The notation \[s0] is literal, while this claim is supported."
    )
    assert result["claims"][0]["text"] == result["body"]


@pytest.mark.parametrize(
    "body",
    [
        "Explain the config key `[source:foo]`.[s0]",
        "```text\n[source:foo]\n```\nThe example is literal.[s0]",
        "Link to [the source](https://example.test/[source:foo]).[s0]",
    ],
)
def test_named_reference_text_inside_protected_markdown_is_literal(body):
    _, units, _ = bound_units()
    result = materialize_marked_body(body, units)
    assert "[source:foo]" in result["body"]
    assert result["claims"]


def test_even_backslashes_do_not_escape_a_compact_marker():
    _, units, _ = bound_units()
    result = materialize_marked_body("A supported statement.\\\\[s0]", units)
    assert result["body"] == "A supported statement.\\\\"


def test_authored_contract_accepts_marked_and_legacy_responses():
    _, units, _ = bound_units()
    section = {"id": "one", "title": "One", "idea_ids": ["idea:0"]}
    marked = _authored_check(
        {
            "body_marked": "Blades capture wind.[s0]",
            "used_idea_ids": ["idea:0"],
        },
        section,
        units,
        "document",
    )
    assert marked["body"] == "Blades capture wind."
    legacy = _authored_check(
        {
            "body": "Blades capture wind.",
            "used_idea_ids": ["idea:0"],
            "evidence": [
                {"unit_id": "unit:0", "quote": "Wind turns the blades."}
            ],
            "claims": [
                {
                    "id": "claim_1",
                    "text": "Blades capture wind.",
                    "body_field": "body",
                    "evidence": [
                        {"unit_id": "unit:0", "quote": "Wind turns the blades."}
                    ],
                }
            ],
        },
        section,
        units,
        "document",
    )
    assert legacy["body"] == marked["body"]


def test_assessment_markers_are_removed_from_both_export_boundaries():
    _, units, _ = bound_units()
    section = {"id": "one", "title": "One", "idea_ids": ["idea:0"]}
    result = _authored_check(
        {
            "candidate_body_marked": "What turns the blades?[s0]",
            "marking_body_marked": "Wind turns the blades.[s0]",
            "used_idea_ids": ["idea:0"],
        },
        section,
        units,
        "assessment",
    )
    assert result["candidate_body"] == "What turns the blades?"
    assert result["marking_body"] == "Wind turns the blades."
    assert all("[s" not in result[key] for key in ("candidate_body", "marking_body"))
    assert [claim["body_field"] for claim in result["claims"]] == [
        "candidate_body",
        "marking_body",
    ]


def test_marked_response_cannot_supply_parallel_claims_or_evidence():
    _, units, _ = bound_units()
    section = {"id": "one", "title": "One", "idea_ids": ["idea:0"]}
    with pytest.raises(ProductionError, match="derive claims and evidence"):
        _authored_check(
            {
                "body_marked": "Blades capture wind.[s0]",
                "used_idea_ids": ["idea:0"],
                "evidence": [],
            },
            section,
            units,
            "document",
        )
