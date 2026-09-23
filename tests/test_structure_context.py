from lamina.production import build_production
from test_source_workflows import SourceWriter, assignments, workspace


def test_slide_parts_accompany_writing_as_context_without_extra_ownership(tmp_path):
    ws, provider = workspace(tmp_path), SourceWriter()
    units = ws.units("teaching")
    for unit in units:
        if unit["id"] in {"u1", "u2"}:
            unit["structural_group"] = "slide:1"
    ws.import_sources(
        [
            (source, [u for u in units if u["source_id"] == source["id"]])
            for source in ws.sources()
        ]
    )
    ownership = assignments()
    ownership["sections"][0]["unit_ids"] = ["u1"]
    ownership["sections"][1]["unit_ids"] = ["u2", "u3", "u4"]
    result = build_production(
        ws,
        provider,
        "Explain",
        ["s1", "s2"],
        {"workflow": "assigned", "assignments": ownership},
    )
    request = next(
        p["input"]
        for stage, p in provider.requests
        if stage == "production_write" and p["input"]["section"]["id"] == "expiry"
    )
    assert len(request["assigned_units"]) == 1
    assert len(request["shared_evidence_units"]) == 1
    assert len(request["source_structures"][0]["unit_ids"]) == 2
    first = result["sections"][0]
    assert first["used_unit_ids"] == ["u1"]
