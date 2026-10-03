"""Podcast episode planning: outline numbering, writer targets, per-episode delivery."""

import json

import pytest

from lamina.production import ProductionError, build_production, run_production, plan_production
from lamina.production_contract import _options, episode_check, podcast_plan
from lamina.production_delivery import deliver_production
from lamina.production_export import export_production
from test_audio_delivery import AudioProvider
from test_production import FixtureProvider, workspace


class EpisodePlanner(FixtureProvider):
    """Numbers the outline's sections into two episodes and records what writers see."""

    def __init__(self, *, skip_episodes=False, **kwargs):
        super().__init__(**kwargs)
        self.skip_episodes = skip_episodes
        self.writer_instructions = []

    def call(self, stage, payload):
        result = super().call(stage, payload)
        if stage == "production_route" and not self.skip_episodes:
            assert "podcast" in payload["input"]
            assert payload["input"]["podcast"]["words_per_episode"] == 150 * payload["input"]["podcast"]["episode_minutes"]
            assert "episode" in payload["expected_shape"]["sections"][0]
            count = len(result["sections"])
            for n, section in enumerate(result["sections"]):
                section["episode"] = 1 if n < count // 2 else 2
                if n == 0:
                    section["target_words"] = 120
        if stage == "production_write":
            self.writer_instructions.append(payload["instruction"])
        return result


def test_outline_episodes_reach_writers_scripts_and_audio(tmp_path):
    provider = EpisodePlanner()
    ws = workspace(tmp_path / "ws")
    options = {"format": "podcast-script", "workflow": "planned", "episode_minutes": 5}
    plan = plan_production(ws, provider, "Two short episodes on lease safety", ["s1", "s2"], options)
    sections = plan["route"]["sections"]
    assert [s["episode"] for s in sections] == [1, 1, 2, 2]
    # The explicit target survives; the rest of the episode budget is shared by idea count.
    assert sections[0]["target_words"] == 120
    assert sections[1]["target_words"] == 750 - 120
    assert sections[2]["target_words"] + sections[3]["target_words"] == 750
    speech = AudioProvider()
    speech.audio_resource, speech.audio_concurrency = "fixture-tts", 2
    out = tmp_path / "out"
    receipt = run_production(ws, provider, plan, audio_provider=speech, audio_output=out)
    assert all("spoken words" in text for text in provider.writer_instructions)
    assert any("episode 2" in text for text in provider.writer_instructions)
    assert any("episode 1" in text for text in provider.writer_instructions)
    assert [row["episode"] for row in receipt["sections"]] == [1, 1, 2, 2]
    assert [row["number"] for row in receipt["episodes"]] == [1, 2]
    assert receipt["episodes"][0]["section_ids"] == [sections[0]["id"], sections[1]["id"]]
    assert "## Episode 2" in receipt["markdown"]
    links = deliver_production(ws, receipt, plan, out, audio_provider=speech)
    assert links["episodes"] == ["episode-01.html", "episode-02.html"]
    assert (out / "episode-02.md").read_text().startswith("# Lease safety — Episode 2")
    manifest = json.loads((out / "audio.json").read_text())
    assert [row["number"] for row in manifest["episodes"]] == [1, 2]
    assert (out / "episode-01.wav").exists() and (out / "episode-02.wav").exists()
    assert manifest["audio"]["frames"] == sum(row["frames"] for row in manifest["episodes"])
    assert manifest["episodes"][0]["section_ids"] == receipt["episodes"][0]["section_ids"]


def test_single_episode_when_the_outline_does_not_number(tmp_path):
    provider = EpisodePlanner(skip_episodes=True)
    receipt = build_production(
        workspace(tmp_path / "ws"),
        provider,
        "A podcast on lease safety",
        ["s1", "s2"],
        {"format": "podcast-script", "workflow": "planned"},
    )
    assert [row["episode"] for row in receipt["sections"]] == [1, 1, 1, 1]
    assert len(receipt["episodes"]) == 1
    assert "## Episode" not in receipt["markdown"]
    assert sum(s["target_words"] for s in receipt["plan"]["route"]["sections"]) == 20 * 150


def test_requested_episode_count_is_enforced_and_forces_planning(tmp_path):
    provider = EpisodePlanner(skip_episodes=True)
    with pytest.raises(ProductionError, match="asks for 3 episodes"):
        build_production(
            workspace(tmp_path / "ws"),
            provider,
            "Three episodes",
            ["s1", "s2"],
            {"format": "podcast-script", "episodes": 3},
        )
    decision = plan_production(
        workspace(tmp_path / "ws2"),
        EpisodePlanner(),
        "Two episodes",
        ["s1", "s2"],
        {"format": "podcast-script", "episodes": 2},
    )["workflow_decision"]
    assert decision["selected"] == "planned"


def test_episode_check_normalizes_order_and_rejects_interleaving():
    plan = podcast_plan(_options({"format": "podcast-script", "episode_minutes": 4}))
    assert plan["words_per_episode"] == 600
    route = {
        "sections": [
            {"id": "a", "idea_ids": ["1"], "episode": 2},
            {"id": "b", "idea_ids": ["2", "3"], "episode": 2},
            {"id": "c", "idea_ids": ["4"], "episode": 5},
        ]
    }
    checked = episode_check(route, plan)
    assert [s["episode"] for s in checked["sections"]] == [1, 1, 2]
    assert [s["target_words"] for s in checked["sections"]] == [200, 400, 600]
    with pytest.raises(ProductionError, match="listening order"):
        episode_check(
            {"sections": [{"id": "a", "idea_ids": ["1"], "episode": 2}, {"id": "b", "idea_ids": ["2"], "episode": 1}]},
            plan,
        )
    assert episode_check({"sections": [{"id": "a", "idea_ids": ["1"]}]}, None) == {
        "sections": [{"id": "a", "idea_ids": ["1"]}]
    }
    with pytest.raises(ProductionError, match="episodes must be auto"):
        _options({"format": "podcast-script", "episodes": 0})
    with pytest.raises(ProductionError, match="episode_minutes"):
        _options({"format": "podcast-script", "episode_minutes": 1})
