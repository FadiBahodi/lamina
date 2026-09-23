"""Regression checks for source replacement and concurrent index migration."""

from concurrent.futures import ThreadPoolExecutor

from lamina.ingest import ingest_paths
from lamina.store import Workspace


def test_concurrent_legacy_index_migration_is_idempotent(tmp_path):
    path = tmp_path / "wind.md"
    path.write_text("# Wind\n\nWind turns blades.")
    root = tmp_path / "db"
    ws = Workspace(root)
    ingest_paths([path], ws)
    with ws.connection() as db:
        db.executescript(
            "DROP TRIGGER units_search_insert; DROP TRIGGER units_search_delete; DROP TABLE units_fts; PRAGMA user_version=0;"
        )
    with ThreadPoolExecutor(max_workers=16) as pool:
        workspaces = list(pool.map(lambda _: Workspace(root), range(16)))
    for current in workspaces:
        assert len(current.search_units("Wind")) == 1


def test_reimport_replaces_parser_units_and_fts_atomically(tmp_path):
    path = tmp_path / "wind.md"
    path.write_text("# Wind\n\nWind turns blades.")
    ws = Workspace(tmp_path / "db")
    ingest_paths([path], ws)
    source, unit = ws.sources()[0], ws.units()[0]
    replacement = {
        **unit,
        "id": "new-parser-unit",
        "text": "Rotation reaches the shaft.",
    }
    ws.import_sources([(source, [replacement])])
    assert [u["id"] for u in ws.units()] == ["new-parser-unit"]
    assert ws.search_units("blades") == []
    assert ws.search_units("shaft")[0]["id"] == "new-parser-unit"
