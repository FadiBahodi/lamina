"""Schedule geometry: the bound T ≥ max(W/P, D) computed from a run's own records."""

import xml.etree.ElementTree as ET

import pytest

from lamina.geometry import analyse, combine, implied_after, timeline_svg


def record(stage, item, start, end, after=(), cache="miss", status="completed"):
    return {
        "stage": stage,
        "item": item,
        "started_ms": start,
        "ended_ms": end,
        "cache": cache,
        "status": status,
        "after": [list(key) for key in after],
        "attempts": [] if cache == "hit" else [{"started_ms": start, "wall_ms": end - start, "status": status}],
        "request_bytes": 100,
    }


def test_declared_dependencies_give_the_critical_path_and_the_bound():
    # A → B → C is a 3-deep chain of 1 s calls; D runs alongside for 2.5 s.
    records = [
        record("production_read", "w1", 0, 1000),
        record("production_read", "w2", 0, 2500),
        record("production_group", "level_0_batch_0", 1000, 2000, after=[("production_read", "w1")]),
        record("production_route", "outline", 2000, 3000, after=[("production_group", "level_0_batch_0")]),
    ]
    g = analyse(records, workers=4, wall_ms=3000, source_bytes=1000)
    assert [(row["stage"], row["item"]) for row in g["critical_path"]] == [
        ("production_read", "w1"), ("production_group", "level_0_batch_0"), ("production_route", "outline"),
    ]
    assert g["critical_path_depth"] == 3 and g["critical_path_ms"] == 3000
    assert g["model_ms"] == 5500 and g["bound_ms"] == max(5500 / 4, 3000) == 3000
    assert g["bound_binding"] == "critical_path" and g["wall_over_bound"] == 1.0
    assert g["peak_in_flight"] == 2 and g["edges"] == {"declared": 2, "implied": 0, "roots": 2}
    assert g["amplification_bytes"] == 0.4


def test_work_over_workers_binds_when_many_independent_calls_share_few_workers():
    records = [record("production_read", f"w{i}", 0, 1000) for i in range(8)]
    g = analyse(records, workers=2, wall_ms=4000)
    assert g["bound_binding"] == "work_over_workers" and g["bound_ms"] == 4000
    assert g["critical_path_depth"] == 1
    assert g["wall_over_bound"] == 1.0


def test_section_chains_audits_and_consistency_follow_stage_rules():
    earlier = [
        {"stage": "production_read", "item": "w1", "ended_ms": 10},
        {"stage": "production_route", "item": "outline", "ended_ms": 20},
        {"stage": "production_assign", "item": "batch_0", "ended_ms": 30},
        {"stage": "production_write", "item": "s1", "ended_ms": 40},
        {"stage": "production_review", "item": "s1", "ended_ms": 50},
        {"stage": "production_repair", "item": "s1", "ended_ms": 60},
    ]
    assert implied_after({"stage": "production_write", "item": "s2"}, earlier) == [("production_assign", "batch_0")]
    assert implied_after({"stage": "production_review", "item": "s1"}, earlier) == [("production_repair", "s1")]
    assert implied_after({"stage": "production_repair", "item": "s1"}, earlier) == [("production_review", "s1")]
    assert implied_after({"stage": "sweep_audit", "item": "w1"}, earlier) == [("production_read", "w1")]
    assert implied_after({"stage": "sweep_audit", "item": "w9"}, earlier) == []
    assert implied_after({"stage": "production_consistency", "item": "global"}, earlier) == [
        ("production_repair", "s1"), ("production_review", "s1"), ("production_write", "s1"),
    ]
    assert implied_after({"stage": "production_group", "item": "x"}, earlier) == []


def test_combine_places_the_run_after_planning_and_keeps_declared_edges():
    plan = analyse(
        [
            record("production_read", "w1", 0, 1000),
            record("production_route", "outline", 1000, 2000, after=[("production_read", "w1")]),
        ],
        workers=4,
        wall_ms=2100,
    )
    run = [
        record("production_write", "s1", 0, 500),
        record("production_review", "s1", 500, 800),
    ]
    g = combine(plan, run, workers=4, wall_ms=900, source_bytes=None)
    chain = [(row["stage"], row["item"]) for row in g["critical_path"]]
    assert chain == [
        ("production_read", "w1"), ("production_route", "outline"),
        ("production_write", "s1"), ("production_review", "s1"),
    ]
    assert g["critical_path_ms"] == 2800 and g["phases"] == {"plan_ms": 2100, "run_ms": 900}
    assert g["edges"]["declared"] == 1 and g["edges"]["implied"] == 2


def test_fixture_run_with_synthetic_latency_respects_the_bound():
    from lamina.production_example import DEMO_LATENCY, production_demo

    latency = {stage: value / 10 for stage, value in DEMO_LATENCY.items()}
    receipt = production_demo(latency=latency)["runs"][0]["receipt"]
    g = receipt["geometry"]
    assert g["timing"].startswith("synthetic")
    assert g["wall_ms"] >= g["bound_ms"] > 0 and g["wall_over_bound"] >= 1.0
    assert g["bound_binding"] == "critical_path"
    stages = [row["stage"] for row in g["critical_path"]]
    assert stages == [
        "production_read", "production_route", "production_write",
        "production_review", "production_repair", "production_review",
    ]
    # Reads ran together; the fixture has one window per source.
    assert g["stages"]["production_read"]["peak_in_flight"] == 2
    assert g["peak_in_flight"] >= 2


def test_timeline_svg_is_well_formed_and_marks_the_critical_path():
    records = [
        record("production_read", "w1", 0, 1000),
        record("production_read", "w2", 0, 1500, cache="hit"),
        record("production_route", "outline", 1500, 2500, after=[("production_read", "w2")]),
    ]
    g = analyse(records, workers=4)
    svg = timeline_svg(g)
    root = ET.fromstring(svg)
    rects = [el for el in root.iter("{http://www.w3.org/2000/svg}rect")]
    assert len(rects) == 3
    classes = [el.get("class") for el in rects]
    assert sum("critical" in c for c in classes) == g["critical_path_depth"] == 2
    assert any("hit" in c for c in classes)
    assert "<script" not in svg
