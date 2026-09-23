import copy

import pytest

from lamina.verification import (
    VerificationError,
    check_document_sections,
    coverage_report,
    validate_claims,
)

UNITS = {"u1": {"text": "Turbine A stops above 20 m/s unless the test mode is active."}}
BODY = {"body": "Turbine A always stops above 20 m/s."}
CLAIMS = [
    {
        "id": "c1",
        "text": BODY["body"],
        "evidence": [{"unit_id": "u1", "quote": UNITS["u1"]["text"]}],
    }
]


def test_links_preserve_evidence_without_claiming_entailment():
    # The statement loses a material exception. Structural validation passes;
    # this is deliberately a semantic review duty, not string matching.
    checked = validate_claims(CLAIMS, BODY, UNITS)
    assert checked[0]["text"] == BODY["body"]
    assert checked[0]["evidence"][0]["quote"].endswith("test mode is active.")
    assert "entailed" not in checked[0]


@pytest.mark.parametrize(
    "mutate,message",
    [
        (lambda c: c[0].update(text="A claim absent from the output"), "output body"),
        (lambda c: c[0].update(body_field="marking_body"), "body_field"),
        (lambda c: c[0]["evidence"][0].update(unit_id="held_out"), "unavailable"),
        (
            lambda c: c[0]["evidence"][0].update(quote="Stops above 21 m/s"),
            "exact source",
        ),
        (lambda c: c.append(copy.deepcopy(c[0])), "unique"),
        (lambda c: c[0].update(evidence=[]), "source evidence"),
        (lambda c: c[0].update(id=[]), "unique"),
        (lambda c: c[0]["evidence"][0].update(unit_id=[]), "unavailable"),
    ],
)
def test_invalid_claim_bindings_fail(mutate, message):
    claims = copy.deepcopy(CLAIMS)
    mutate(claims)
    with pytest.raises(VerificationError, match=message):
        validate_claims(claims, BODY, UNITS)


def test_assessment_mapping_respects_named_body():
    bodies = {
        "candidate_body": "What threshold applies?",
        "marking_body": "The threshold is 20 m/s.",
    }
    claims = [
        {
            "id": "answer",
            "body_field": "marking_body",
            "text": bodies["marking_body"],
            "evidence": CLAIMS[0]["evidence"],
        }
    ]
    assert validate_claims(claims, bodies, UNITS)[0]["body_field"] == "marking_body"
    assert validate_claims(None, bodies, UNITS) == []


def test_claim_quote_uses_the_shared_conservative_source_resolver():
    text = "The controller reports ‘standby’ after\n sensor disagreement."
    claim = [
        {
            "id": "c",
            "text": "Standby is reported.",
            "evidence": [
                {
                    "unit_id": "u",
                    "quote": "The controller reports 'standby' after sensor disagreement.",
                }
            ],
        }
    ]
    checked = validate_claims(
        claim, {"body": "Standby is reported."}, {"u": {"text": text}}
    )
    assert checked[0]["evidence"][0]["quote"] == text


def test_coverage_distinguishes_reading_extraction_assignment_and_output():
    plan = {
        "options": {"workflow": "planned"},
        "units": [{"id": x} for x in ("u1", "u2", "u3")],
        "windows": [{"core": ["u1", "u2", "u3"]}],
        "ideas": [
            {"id": "i1", "unit_ids": ["u1"], "evidence": [{"unit_id": "u1"}]},
            {"id": "i2", "unit_ids": ["u2"], "evidence": [{"unit_id": "u2"}]},
        ],
        "route": {
            "sections": [{"id": "s1", "idea_ids": ["i1"]}],
            "omitted": [{"idea_id": "i2", "reason": "Outside brief"}],
        },
    }
    authored = [
        {
            "id": "s1",
            "evidence": [{"unit_id": "u1"}],
            "claims": validate_claims(CLAIMS, BODY, UNITS),
        }
    ]
    report = coverage_report(plan, authored)
    assert report["reading"]["unconsidered_unit_ids"] == []
    assert report["reading"]["uncited_unit_ids"] == ["u3"]
    assert report["assignment"]["explicitly_omitted_unit_ids"] == ["u2"]
    assert report["assignment"]["unaccounted_unit_ids"] == ["u3"]
    assert report["output"]["mapped_claim_count"] == 1


def test_direct_coverage_does_not_invent_reader_work():
    plan = {
        "options": {"workflow": "direct"},
        "units": [{"id": "u1"}, {"id": "u2"}],
        "route": {"sections": [{"id": "s", "unit_ids": ["u1", "u2"]}], "omitted": []},
    }
    authored = [
        {
            "id": "s",
            "evidence": [{"unit_id": "u1"}],
            "omitted_units": [{"unit_id": "u2", "reason": "Outside brief"}],
        }
    ]
    report = coverage_report(plan, authored)
    assert report["reading"]["applicable"] is False
    assert report["assignment"]["unaccounted_unit_ids"] == []
    assert report["output"]["assigned_without_citation_unit_ids"] == ["u2"]
    assert report["output"]["writer_omitted_unit_ids"] == ["u2"]


def document_fixture():
    units = [
        {"id": f"u{i}", "source_id": "source", "text": f"Source fact {i}."}
        for i in range(1, 5)
    ]
    sections = [
        {"id": f"s{i}", "unit_ids": [f"u{i}"], "context_section_ids": []}
        for i in range(1, 5)
    ]
    sections[1]["context_section_ids"] = ["s1"]
    authored = [
        {
            "id": f"s{i}",
            "body": f"Source fact {i}.",
            "evidence": [{"unit_id": f"u{i}", "quote": f"Source fact {i}."}],
        }
        for i in range(1, 5)
    ]
    plan = {
        "brief": {"goal": "Explain fixture facts"},
        "options": {"format": "document", "source_policy": {"source": "authority"}},
        "sources": [{"id": "source", "title": "Original fixture"}],
        "units": units,
        "route": {
            "sections": sections,
            "shared_context": [
                {
                    "statement": "Facts one and three disagree.",
                    "evidence": [
                        authored[0]["evidence"][0],
                        authored[2]["evidence"][0],
                    ],
                }
            ],
        },
    }
    return plan, authored


def test_document_audit_checks_explicit_relationships_and_targets_findings():
    plan, authored = document_fixture()
    requests = []

    def invoke(stage, item, instruction, shape, data, check):
        requests.append(data)
        assert stage == "production_consistency"
        ids = [s["id"] for s in data["sections"]]
        finding = {
            "section_ids": ["s3"],
            "issue": "State which source condition applies.",
            "repair_instruction": "Keep the stated disagreement explicit.",
            "evidence": authored[2]["evidence"],
        }
        return check({"findings": [finding] if "s3" in ids else []})

    result = check_document_sections(plan, authored, invoke, workers=2)
    assert {tuple(s["id"] for s in r["sections"]) for r in requests} == {
        ("s1", "s2"),
        ("s1", "s3"),
    }
    assert result["status"] == "review"
    assert result["findings"][0]["section_ids"] == ["s3"]
    assert result["scope"]["checked_pair_count"] == 2
    assert result["scope"]["other_pair_count"] == 4


def test_document_audit_never_truncates_a_pair_to_claim_completion():
    plan, authored = document_fixture()
    original = copy.deepcopy(authored)
    result = check_document_sections(
        plan,
        authored,
        lambda *args: pytest.fail("Oversized request was invoked"),
        fits=lambda *args: False,
    )
    assert authored == original
    assert result["status"] == "review"
    assert result["scope"]["checked_pair_count"] == 0
    assert len(result["scope"]["unchecked_due_to_budget_or_failure"]) == 2


def test_document_audit_adjacency_is_explicit_and_failed_pair_stays_visible():
    plan, authored = document_fixture()

    def invoke(stage, item, instruction, shape, data, check):
        if item == "s2:s3":
            raise RuntimeError("Fixture exhausted retries")
        return check({"findings": []})

    result = check_document_sections(plan, authored, invoke, include_adjacency=True)
    assert len(result["checks"]) == 4
    assert result["scope"]["unchecked_due_to_budget_or_failure"] == [["s2", "s3"]]
    assert result["status"] == "review"


def test_document_audit_rejects_findings_about_unseen_sections():
    plan, authored = document_fixture()

    def invoke(stage, item, instruction, shape, data, check):
        return check(
            {
                "findings": [
                    {
                        "section_ids": ["absent"],
                        "issue": "Foreign",
                        "repair_instruction": "Foreign",
                        "evidence": [],
                    }
                ]
            }
        )

    result = check_document_sections(plan, authored, invoke)
    assert result["status"] == "review"
    assert all(row["error_type"] == "VerificationError" for row in result["checks"])


def test_explicit_shared_scope_controls_the_relationship_and_disclosed_context():
    plan, authored = document_fixture()
    plan["route"]["sections"][1]["context_section_ids"] = []
    # The statement cites units owned by s1/s3 but explicitly concerns s2/s4.
    # Its semantic scope is authoritative; source ownership remains provenance.
    plan["route"]["shared_context"][0]["section_ids"] = ["s2", "s4"]
    seen = []

    def invoke(stage, item, instruction, shape, data, check):
        seen.append(data)
        return check({"findings": []})

    result = check_document_sections(plan, authored, invoke)
    assert result["scope"]["checked_pair_count"] == 1
    assert [s["id"] for s in seen[0]["sections"]] == ["s2", "s4"]
    assert seen[0]["shared_context"] == plan["route"]["shared_context"]


def test_production_document_review_has_a_separate_visible_finding(tmp_path):
    from lamina.production import build_production
    from test_production import workspace
    from test_source_workflows import SourceWriter, assignments

    class DocumentReviewer(SourceWriter):
        def call(self, stage, payload):
            if stage != "production_consistency":
                return super().call(stage, payload)
            self.requests.append((stage, payload))
            section = payload["input"]["sections"][1]
            return {
                "findings": [
                    {
                        "section_ids": [section["id"]],
                        "issue": "The transition does not explain how expiry differs from fencing.",
                        "repair_instruction": "Make that distinction explicit at the transition.",
                        "evidence": section["evidence"],
                    }
                ]
            }

    provider = DocumentReviewer()
    receipt = build_production(
        workspace(tmp_path),
        provider,
        "Explain the mechanism",
        ["s1", "s2"],
        {"workflow": "assigned", "assignments": assignments(), "document_review": True},
    )
    assert receipt["status"] == "review"
    assert len(receipt["sections"]) == 2
    assert receipt["findings"] == {}
    assert receipt["document_checks"]["findings"][0]["section_ids"] == ["writes"]
    assert sum(stage == "production_consistency" for stage, _ in provider.requests) == 1


def test_oversized_actual_review_retains_the_draft_and_marks_unperformed(tmp_path):
    from lamina.production import build_production
    from test_production import workspace
    from test_source_workflows import SourceWriter

    class LongWriter(SourceWriter):
        def call(self, stage, payload):
            result = super().call(stage, payload)
            if stage == "production_write":
                result["body"] *= 100
            return result

    provider = LongWriter()
    receipt = build_production(
        workspace(tmp_path),
        provider,
        "Explain source details",
        ["s1"],
        {"workflow": "direct", "max_input_bytes": 20000},
    )
    assert receipt["status"] == "review"
    assert len(receipt["sections"][0]["body"]) > 20000
    findings = [finding for rows in receipt["findings"].values() for finding in rows]
    assert findings and all(finding["verification_unperformed"] for finding in findings)
    assert [stage for stage, _ in provider.requests] == ["production_write"]


@pytest.mark.parametrize(
    "fmt,bodies,discarded",
    [
        (
            "document",
            {"body": "Kept fact.", "marking_body": "Discarded key."},
            "marking_body",
        ),
        (
            "assessment",
            {
                "candidate_body": "Which fact?",
                "marking_body": "Kept fact.",
                "body": "Discarded prose.",
            },
            "body",
        ),
    ],
)
def test_authored_contract_rejects_claims_in_discarded_format_fields(
    fmt, bodies, discarded
):
    from lamina.production_contract import _authored_check

    section = {"id": "s", "title": "Fixture", "idea_ids": ["i"]}
    evidence = [{"unit_id": "u", "quote": "Kept fact."}]
    raw = {
        **bodies,
        "used_idea_ids": ["i"],
        "evidence": evidence,
        "claims": [
            {
                "id": "c",
                "body_field": discarded,
                "text": bodies[discarded],
                "evidence": evidence,
            }
        ],
    }
    with pytest.raises(VerificationError, match="body_field"):
        _authored_check(raw, section, {"u": {"text": "Kept fact."}}, fmt)


def test_authored_claims_resolve_against_the_body_that_is_actually_stored():
    from lamina.production_contract import _authored_check

    section = {"id": "s", "title": "Fixture", "idea_ids": ["i"]}
    units = {"u": {"text": "Kept fact."}}
    evidence = [{"unit_id": "u", "quote": "Kept fact."}]
    raw = {
        "body": "  Kept fact.  ",
        "used_idea_ids": ["i"],
        "evidence": evidence,
        "claims": [{"id": "c", "text": "Kept fact.", "evidence": evidence}],
    }
    checked = _authored_check(raw, section, units, "document")
    assert checked["body"] == "Kept fact."
    assert checked["claims"][0]["text"] in checked["body"]
    raw["claims"][0]["text"] = raw["body"]
    with pytest.raises(VerificationError, match="exact substring"):
        _authored_check(raw, section, units, "document")
