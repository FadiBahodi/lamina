"""Sweep route mechanics: read → local dedup → sampled audit → cards.

Deterministic fixtures establish the dependency shape and the accounting,
not card quality.
"""

import json
import re

import pytest

from lamina.production import ProductionError, build_production, plan_production, run_production
from lamina.production_contract import _options
from lamina.production_export import export_production
from lamina.sweep import cards_tsv, sampled
from lamina.store import Workspace
from test_production import FixtureProvider


def workspace(tmp_path, repeat_last=False):
    ws = Workspace(tmp_path)
    for sid, title in (("s1", "Operations"), ("s2", "Reliability")):
        ws.put_source(
            {"id": sid, "title": title, "filename": sid + ".md", "sha256": sid, "role": "teaching"}
        )
    units = [
        ("u1", "s1", "Expiry", "A lease expires after thirty seconds. The clock starts at grant time."),
        ("u2", "s1", "Stale work", "The old worker may still run after expiry. It must not write."),
        ("u3", "s2", "Fencing", "A fencing token rejects stale writes. Tokens increase monotonically."),
        (
            "u4",
            "s2",
            "Expiry again",
            "A lease expires after thirty seconds. The clock starts at grant time."
            if repeat_last
            else "A retry uses the current token. Old tokens are refused.",
        ),
    ]
    for ordinal, (uid, sid, heading, body) in enumerate(units):
        ws.put_units(
            [
                {
                    "id": uid,
                    "source_id": sid,
                    "role": "teaching",
                    "ordinal": ordinal,
                    "heading": heading,
                    "locator": f"page {ordinal + 1}",
                    "text": body,
                    "content_id": "content-" + uid,
                }
            ]
        )
    return ws


class CardReader(FixtureProvider):
    """Writes one question card per owned span and audits one window."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.audit_windows = []

    def call(self, stage, payload):
        data = payload["input"]
        if stage == "production_read":
            with self.lock:
                self.requests.append((stage, payload))
            assert "flashcards" in payload["instruction"]
            ideas = []
            for unit in data["core"]:
                for span in unit["spans"]:
                    ideas.append(
                        {
                            "title": f"What does the source say: {span['text'].strip()[:-1]}?",
                            "explanation": span["text"].strip(),
                            "evidence_refs": [{"span_id": span["id"]}],
                        }
                    )
            return {"ideas": ideas}
        if stage == "sweep_audit":
            with self.lock:
                self.requests.append((stage, payload))
            self.audit_windows.append(data["window_id"])
            core = data["core"][0]
            return {
                "findings": [
                    {
                        "kind": "omission",
                        "issue": "The grant-time detail is not tested as a separate card.",
                        "card_ids": [],
                        "evidence": [{"unit_id": core["id"], "quote": core["spans"][-1]["text"].strip()}],
                    }
                ]
            }
        return super().call(stage, payload)


def test_cards_format_selects_the_sweep_route_and_publishes_cards(tmp_path):
    provider = CardReader()
    result = build_production(
        workspace(tmp_path),
        provider,
        "Make flashcards about lease safety",
        ["s1", "s2"],
        {"format": "cards", "audit_rate": 1.0},
    )
    plan = result["plan"]
    assert plan["workflow_decision"]["selected"] == "sweep"
    assert plan["options"]["workflow"] == "sweep"
    stages = [stage for stage, _ in provider.requests]
    # The fixture budget packs each source into one window. Exactly one read
    # and one audit per window; no planner, no writer, no reviewer.
    windows = len(plan["windows"])
    assert windows == 2
    assert stages.count("production_read") == windows
    assert stages.count("sweep_audit") == windows
    assert set(stages) == {"production_read", "sweep_audit"}
    # The fixture auditor reports one omission per window: the deck is
    # available and downloadable, and its status says it needs review.
    assert result["status"] == "review"
    assert result["coverage"]["sweep"]["windows_with_findings"]
    assert result["format"] == "cards"
    assert len(result["cards"]) == 8
    assert all(card["kind"] == "basic" for card in result["cards"])
    assert {card["source"] for card in result["cards"]} == {"Operations", "Reliability"}
    assert result["metrics"]["cards"] == 8
    assert result["metrics"]["audited_windows"] == windows
    assert result["metrics"]["audit_findings"] == windows
    # Audit findings are attached per window and never remove a card.
    assert len(result["audit_findings"]) == windows
    assert all(row[0]["kind"] == "omission" for row in result["audit_findings"].values())
    assert "**Q:**" in result["markdown"] and "<sub>page 1</sub>" in result["markdown"]
    # Coverage reports the reading boundary for the sweep.
    assert result["coverage"]["reading"]["applicable"] is True
    assert result["coverage"]["reading"]["unconsidered_unit_ids"] == []
    assert result["coverage"]["assignment"]["unaccounted_unit_ids"] == []


def test_sweep_suppresses_duplicates_locally_and_records_them(tmp_path):
    provider = CardReader()
    result = build_production(
        workspace(tmp_path, repeat_last=True),
        provider,
        "Make flashcards about lease safety",
        ["s1", "s2"],
        {"format": "cards", "audit_rate": 0.0},
    )
    plan = result["plan"]
    duplicates = plan["duplicates"]
    assert len(duplicates) == 2
    for iid, row in duplicates.items():
        assert iid.startswith(plan["windows"][1]["id"])  # the repeated u4 text
        assert row["duplicate_of"].startswith(plan["windows"][0]["id"])  # kept u1 card
        assert row["score"] >= plan["planning"]["dedup"]["threshold"]
    assert plan["planning"]["dedup"]["method"] == "tfidf"
    assert plan["metrics"]["suppressed_duplicates"] == 2
    # The duplicates stay in the plan as explicit omissions and leave the output.
    assert {row["idea_id"] for row in plan["route"]["omitted"]} == set(duplicates)
    assert len(result["cards"]) == 6
    assert not any(stage == "sweep_audit" for stage, _ in provider.requests)
    assert result["metrics"]["audited_windows"] == 0


def test_sweep_continues_past_failed_windows_and_reports_review(tmp_path):
    from lamina.providers import ProviderError

    class FailsOne(CardReader):
        def call(self, stage, payload):
            if stage == "production_read" and payload["input"]["source"]["title"] == "Reliability":
                if payload["input"]["core"][0]["spans"][0]["text"].startswith("A fencing"):
                    raise ProviderError("adapter failed", code="adapter")
            return super().call(stage, payload)

    result = build_production(
        workspace(tmp_path),
        FailsOne(),
        "Make flashcards",
        ["s1", "s2"],
        {"format": "cards", "audit_rate": 0.0},
    )
    # The deck is available, but one window was never read: that is review,
    # not ready, and the coverage object says which window.
    assert result["status"] == "review"
    assert len(result["unresolved_reads"]) == 1
    assert result["unresolved_reads"][0]["core"] == ["u3", "u4"]
    assert result["coverage"]["sweep"]["windows_read"] == result["coverage"]["sweep"]["windows"] - 1
    assert result["coverage"]["sweep"]["unresolved_windows"] == [result["unresolved_reads"][0]["id"]]
    assert result["metrics"]["unresolved_reader_windows"] == 1
    assert len(result["cards"]) == 4
    # A failed window's units were never read, and the coverage report says so.
    assert result["coverage"]["reading"]["unconsidered_unit_ids"] == ["u3", "u4"]
    assert result["coverage"]["reading"]["uncited_unit_ids"] == ["u3", "u4"]
    with pytest.raises(ProductionError, match="reading batch.*unresolved"):
        build_production(
            workspace(tmp_path / "abort"),
            FailsOne(),
            "Make flashcards",
            ["s1", "s2"],
            {"format": "cards", "audit_rate": 0.0, "reading_failures": "abort"},
        )


def test_sweep_export_writes_anki_tsv_and_card_json(tmp_path):
    result = build_production(
        workspace(tmp_path / "ws"),
        CardReader(),
        "Make flashcards",
        ["s1", "s2"],
        {"format": "cards", "audit_rate": 0.0},
    )
    links = export_production(result, result["plan"], tmp_path / "out")
    assert links["cards_tsv"] == "cards.tsv" and links["cards_json"] == "cards.json"
    tsv = (tmp_path / "out" / "cards.tsv").read_text()
    lines = tsv.strip().split("\n")
    headers = [line for line in lines if line.startswith("#")]
    assert headers[:5] == [
        "#separator:tab", "#html:true", "#notetype column:1", "#guid column:2", "#tags column:5",
    ]
    rows = [line.split("\t") for line in lines if not line.startswith("#")]
    assert len(rows) == 8 and all(len(row) == 5 for row in rows)
    assert {row[0] for row in rows} <= {"Basic", "Cloze"}
    assert all(len(row[1]) == 20 for row in rows)
    assert rows[0][2].startswith("What does the source say")
    assert "Operations" in rows[0][4]
    # GUIDs are stable across runs of the same material, so a re-import updates.
    again = build_production(
        workspace(tmp_path / "ws2"), CardReader(), "Make flashcards", ["s1", "s2"],
        {"format": "cards", "audit_rate": 0.0},
    )
    assert [c["guid"] for c in again["cards"]] == [c["guid"] for c in result["cards"]]
    cards = json.loads((tmp_path / "out" / "cards.json").read_text())
    assert cards == result["cards"]
    assert (tmp_path / "out" / "document.md").read_text().startswith("# Make flashcards")


def test_sweep_plan_runs_again_without_model_calls(tmp_path):
    provider = CardReader()
    ws = workspace(tmp_path)
    plan = plan_production(ws, provider, "Make flashcards", ["s1", "s2"], {"format": "cards", "audit_rate": 0.5})
    before = len(provider.requests)
    receipt = run_production(ws, provider, plan)
    assert len(provider.requests) == before
    assert receipt["status"] == "review" and receipt["plan_digest"] == plan["plan_digest"]
    # Deterministic sampling: the same windows are audited on a restart.
    again = plan_production(ws, provider, "Make flashcards", ["s1", "s2"], {"format": "cards", "audit_rate": 0.5})
    assert again["planning"]["audit"]["sampled_windows"] == plan["planning"]["audit"]["sampled_windows"]
    assert len(provider.requests) == before  # every call was a cache hit


def test_sampling_is_deterministic_and_rate_bounded():
    ids = [f"window_{n:04d}" for n in range(2000)]
    assert [sampled(i, 0.25) for i in ids] == [sampled(i, 0.25) for i in ids]
    share = sum(sampled(i, 0.25) for i in ids) / len(ids)
    assert 0.2 < share < 0.3
    assert not any(sampled(i, 0.0) for i in ids)
    assert all(sampled(i, 1.0) for i in ids)


def test_cards_tsv_escapes_fields():
    text = cards_tsv(
        [{"kind": "basic", "guid": "x" * 20, "prompt": "A\tB", "answer": "line1\nline2", "source": "Book One", "heading": "Ch 2"}]
    )
    assert text.endswith("Basic\t" + "x" * 20 + "\tA B\tline1<br>line2\tBook_One Ch_2\n")


def test_option_contract_for_sweep():
    assert _options({"format": "cards"})["workflow"] == "sweep"
    with pytest.raises(ProductionError, match="go together"):
        _options({"format": "cards", "workflow": "planned"})
    with pytest.raises(ProductionError, match="go together"):
        _options({"workflow": "sweep"})
    with pytest.raises(ProductionError, match="audit_rate"):
        _options({"format": "cards", "audit_rate": 2})
    with pytest.raises(ProductionError, match="dedup_threshold"):
        _options({"format": "cards", "dedup_threshold": 0})


def test_cards_tsv_escapes_html_and_types_cloze_notes():
    from lamina.sweep import cards_tsv

    rows = [
        {"kind": "basic", "guid": "g" * 20, "prompt": "Is 5 < 7 & 7 > 5?", "answer": "Yes\nboth.", "source": "Maths", "heading": "Order"},
        {"kind": "cloze", "guid": "h" * 20, "prompt": "The limit is {{c1::eight bar}}.", "answer": "", "source": "Manual", "heading": ""},
    ]
    text = cards_tsv(rows)
    body = [line.split("\t") for line in text.strip().split("\n") if not line.startswith("#")]
    assert body[0][0] == "Basic" and body[0][2] == "Is 5 &lt; 7 &amp; 7 &gt; 5?" and body[0][3] == "Yes<br>both."
    assert body[1][0] == "Cloze" and "{{c1::eight bar}}" in body[1][2]
    assert body[1][4] == "Manual"


def test_a_card_deck_cannot_be_revised_by_section(tmp_path):
    """The UI's section-revision control does not apply to decks: readers
    wrote the cards directly. The engine says so instead of republishing the
    same deck as if the note had been applied."""
    provider = CardReader()
    ws = workspace(tmp_path)
    plan = plan_production(ws, provider, "Make flashcards", ["s1", "s2"], {"format": "cards", "audit_rate": 0.0})
    with pytest.raises(ProductionError, match="no section writer"):
        run_production(ws, provider, plan, {"section_notes": {plan["route"]["sections"][0]["id"]: "Add dosing."}})
