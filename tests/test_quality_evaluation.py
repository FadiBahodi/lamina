"""These tests exercise oracle behavior, never model capability."""

import importlib.util
from pathlib import Path

import pytest

from lamina.quality_evaluation import Canary, score_canaries, run_trial, summarize


def fixture_module():
    path = Path(__file__).resolve().parents[1] / "benchmarks" / "quality_titration.py"
    spec = importlib.util.spec_from_file_location("quality_titration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture_provider():
    return fixture_module().SilentOmissionProvider(max_items=100)


def fact():
    return Canary(
        "negation",
        "primary.md",
        "Rotor Umber",
        ("Rotor Umber", "does not reset", "red lamp"),
        ("Rotor Umber resets while",),
        "middle",
        "negation",
    )


def row(text, quote=None, source="correct"):
    return {
        "id": "r1",
        "text": text,
        "evidence": [{"unit_id": source, "quote": quote or text}],
    }


SOURCE = "Rotor Umber does not reset while its red lamp is illuminated."


def test_citation_does_not_supply_missing_authored_qualification():
    result = score_canaries(
        [fact()],
        [row("Rotor Umber has a red lamp.", SOURCE)],
        {"correct": "primary.md"},
    )
    assert result["preserved"] == 0
    assert result["checks"][0]["status"] == "required_phrase_missing"


def test_source_identity_and_authored_content_both_required():
    result = score_canaries(
        [fact()], [row(SOURCE, source="wrong")], {"wrong": "archive.md"}
    )
    assert result["checks"][0]["status"] == "wrong_or_missing_source"
    result = score_canaries([fact()], [row(SOURCE)], {"correct": "primary.md"})
    assert result["fraction"] == 1


def test_known_counterfact_overrides_simultaneous_correct_statement():
    result = score_canaries(
        [fact()],
        [
            row(
                SOURCE + " Rotor Umber resets while its red lamp is illuminated.",
                SOURCE,
            )
        ],
        {"correct": "primary.md"},
    )
    assert result["preserved"] == 0
    assert result["counterfacts"] == 1


def test_no_paraphrase_entailment_claim():
    result = score_canaries(
        [fact()],
        [row("An illuminated red lamp prevents Rotor Umber from resetting.", SOURCE)],
        {"correct": "primary.md"},
    )
    assert result["preserved"] == 0
    assert result["oracle"] == "local-qualified-phrase-and-source-2"


def test_silent_omission_passes_engine_but_fails_output_oracle(tmp_path):
    trial = run_trial(
        fixture_provider(), tmp_path / "trial", load=6, reading="task", complete=True
    )
    assert trial["status"] == "completed", trial
    assert trial["engine_status"] == "ready"
    assert trial["citation_coverage"]["reading"]["uncited_unit_ids"] == []
    assert (
        trial["citation_coverage"]["output"]["assigned_without_citation_unit_ids"] == []
    )
    assert trial["extraction"]["preserved"] == 5
    assert trial["extraction"]["total"] == 6
    assert trial["finished_output"]["preserved"] == 5
    assert trial["calls"]
    position_sets = [
        set(call.get("canary_source_positions", {}))
        for call in trial["calls"]
        if call["stage"] == "production_read"
    ]
    assert {"history"} in position_sets
    assert all(not {"threshold", "history"} <= keys for keys in position_sets)
    assert all(call["status"] == "completed" for call in trial["calls"])
    assert trial["stage_budgets"]["production_read"]["output_tokens"] == 0
    summary = summarize(
        [trial],
        minimum_fraction=1,
        maximum_counterfacts=0,
        required_stages=["extraction", "assignment", "finished_output"],
    )
    assert not summary["observations"][0]["passed_all_observed_checks"]
    assert summary["largest_sampled_passing_load"] == {}


def test_reusable_inventory_still_exposes_observed_miss(tmp_path):
    trial = run_trial(
        fixture_provider(),
        tmp_path / "trial",
        load=2,
        reading="reusable",
        complete=False,
    )
    assert trial["status"] == "completed", trial
    assert trial["extraction"]["preserved"] == 5
    assert "recall_certificate" not in trial
    with pytest.raises(ValueError, match="fresh workspace"):
        run_trial(
            fixture_provider(),
            tmp_path / "trial",
            load=2,
            reading="reusable",
            complete=False,
        )


def test_all_replicates_and_positions_must_satisfy_explicit_criterion():
    score = {
        "fraction": 0.9,
        "counterfacts": 0,
        "by_position": {
            "middle": {"preserved": 0, "total": 1},
            "end": {"preserved": 9, "total": 9},
        },
    }
    trial = {
        "provider_identity": "fixture",
        "reading": "task",
        "load": 5,
        "status": "completed",
        "extraction": score,
    }
    summary = summarize(
        [trial],
        minimum_fraction=0.8,
        maximum_counterfacts=0,
        required_stages=["extraction"],
    )
    assert not summary["observations"][0]["passed_all_observed_checks"]
    trial["extraction"]["by_position"]["middle"] = {"preserved": 1, "total": 1}
    trial["extraction"]["fraction"] = 1
    failed = {**trial, "status": "failed"}
    summary = summarize(
        [trial, failed],
        minimum_fraction=1,
        maximum_counterfacts=0,
        required_stages=["extraction"],
    )
    assert summary["largest_sampled_passing_load"] == {}


def test_known_number_substitution_and_table_chimera():
    canary = Canary(
        "table",
        "primary.md",
        "Panel Jade lane L",
        ("Panel Jade lane L", "6 mA", "below 4 C"),
        ("Panel Jade lane L uses 9 mA",),
        "table",
        "association",
    )
    source = (
        "Panel Jade lane L uses 6 mA below 4 C. Panel Jade lane M uses 9 mA above 4 C."
    )
    result = score_canaries(
        [canary],
        [row("Panel Jade lane L uses 9 mA above 4 C.", source)],
        {"correct": "primary.md"},
    )
    assert result["checks"][0]["status"] == "counterfact"
    changed = row("Panel Jade lane L uses 16 mA below 4 C.", source)
    result = score_canaries([canary], [changed], {"correct": "primary.md"})
    assert result["preserved"] == 0


def test_absent_fact_and_known_inserted_claim_are_visible():
    expected = fact()
    result = score_canaries(
        [expected], [row("The archive is available.")], {"correct": "primary.md"}
    )
    assert result["checks"][0]["status"] == "absent"
    expected = Canary(
        "inserted",
        "primary.md",
        "Rotor Umber",
        ("Rotor Umber", "does not reset"),
        ("Rotor Umber generates electricity from its red lamp",),
        "middle",
        "known-insertion",
    )
    result = score_canaries(
        [expected],
        [row(SOURCE + " Rotor Umber generates electricity from its red lamp.", SOURCE)],
        {"correct": "primary.md"},
    )
    assert result["counterfacts"] == 1


def test_experimental_limit_controls_actual_production_requests(tmp_path):
    from dataclasses import replace
    from lamina.store import canonical

    module = fixture_module()

    class CountedFixture(module.SilentOmissionProvider):
        def budget_for(self, stage):
            return replace(
                super().budget_for(stage),
                context_tokens=100_000,
                output_tokens=1_000,
                count_tokens=lambda request: len(canonical(request)),
                counting="fixture-character-counter",
            )

    base = CountedFixture(max_items=100)
    small = module.ExperimentalLimit(base, "production_read", 3000)
    trial = run_trial(
        small, tmp_path / "small", load=20, reading="task", complete=False
    )
    assert trial["status"] == "completed", trial
    reads = [row for row in trial["calls"] if row["stage"] == "production_read"]
    assert len(reads) > 2
    assert all(row["measurement"]["input_tokens"] <= 3000 for row in reads)
    assert (
        trial["stage_budgets"]["production_read"]["workload"]["max_input_tokens"]
        == 3000
    )


@pytest.mark.parametrize("separator", [". ", "; ", "\n"])
def test_crossed_table_values_cannot_borrow_neighboring_subject_phrases(separator):
    facts = [
        Canary(
            "lane-l",
            "primary.md",
            "Panel Jade lane L",
            ("Panel Jade lane L", "6 mA", "only below 4 C"),
            (),
            "table",
            "association",
        ),
        Canary(
            "lane-m",
            "primary.md",
            "Panel Jade lane M",
            ("Panel Jade lane M", "9 mA", "only at or above 4 C"),
            (),
            "table",
            "association",
        ),
    ]
    correct = "Panel Jade lane L current is 6 mA only below 4 C. Panel Jade lane M current is 9 mA only at or above 4 C."
    crossed = separator.join(
        [
            "Panel Jade lane L current is 9 mA only at or above 4 C",
            "Panel Jade lane M current is 6 mA only below 4 C",
        ]
    )
    score = score_canaries(facts, [row(crossed, correct)], {"correct": "primary.md"})
    assert score["preserved"] == 0
    score = score_canaries(facts, [row(correct)], {"correct": "primary.md"})
    assert score["preserved"] == 2
    # The quoted support is checked with the same local association rule.
    score = score_canaries(facts, [row(correct, crossed)], {"correct": "primary.md"})
    assert score["preserved"] == 0
