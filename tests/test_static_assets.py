import re
from lamina.static_assets import fingerprint_page_assets


def test_changed_styles_get_new_urls_while_unchanged_script_is_reused(tmp_path):
    original='<link href="styles.css"><script src="app.js"></script><a href="https://example.com/a.js">external</a>'
    (tmp_path/'index.html').write_text(original)
    (tmp_path/'styles.css').write_text('body{color:black}')
    (tmp_path/'app.js').write_text('const v=1;')
    fingerprint_page_assets(tmp_path)
    first=(tmp_path/'index.html').read_text()
    paths=re.findall(r'(?:src|href)="([^\"]+)"',first)
    assert all((tmp_path/p).is_file() for p in paths[:2])
    (tmp_path/'index.html').write_text(original)
    (tmp_path/'styles.css').write_text('body{color:blue}')
    fingerprint_page_assets(tmp_path)
    second=(tmp_path/'index.html').read_text()
    revised=re.findall(r'(?:src|href)="([^\"]+)"',second)
    assert paths[0]!=revised[0]
    assert paths[1]==revised[1]
    assert revised[2]=='https://example.com/a.js'


def test_public_site_is_static_and_retires_only_known_old_app_outputs(tmp_path):
    from lamina.studio_site import prepare_website

    (tmp_path / "examples/production").mkdir(parents=True)
    (tmp_path / "examples/production/index.html").write_text("old fixture")
    (tmp_path / "workbench").mkdir()
    (tmp_path / "workbench/index.html").write_text("old fixture")
    (tmp_path / "production-example.json").write_text("{}")
    (tmp_path / "app.js").write_text("old local application")
    (tmp_path / "app.012345abcdef.js").write_text("old fingerprinted app")
    (tmp_path / "method-trace.012345abcdef.js").write_text("old trace")
    (tmp_path / "notes.txt").write_text("operator-owned file")

    prepare_website(tmp_path)
    prepare_website(tmp_path)
    page = (tmp_path / "index.html").read_text()
    assert "Generation requires an LLM connection" in page
    assert not re.search(r"<(script|form|button)\b", page)
    assert not (tmp_path / "examples/production").exists()
    assert not (tmp_path / "workbench").exists()
    assert not (tmp_path / "production-example.json").exists()
    assert not (tmp_path / "app.js").exists()
    assert not (tmp_path / "app.012345abcdef.js").exists()
    assert not (tmp_path / "method-trace.012345abcdef.js").exists()
    assert (tmp_path / "notes.txt").read_text() == "operator-owned file"
    assert (tmp_path / "assets/lamina-technical-paper.pdf").is_file()
    for relative in re.findall(r'(?:src|href)="([^\"]+)"', page):
        if relative.startswith(("https:", "#", "./")):
            continue
        assert (tmp_path / relative).is_file(), relative


def test_local_asset_preparation_does_not_run_example_generators(tmp_path, monkeypatch):
    from lamina import method_example, pipeline, production_example
    from lamina.studio_site import prepare_studio

    def forbidden(*args, **kwargs):
        raise AssertionError("application startup must not generate example content")

    monkeypatch.setattr(pipeline, "build", forbidden)
    monkeypatch.setattr(method_example, "method_demo", forbidden)
    monkeypatch.setattr(production_example, "production_demo", forbidden)
    (tmp_path / "inspector.js").write_text("old showcase")
    prepare_studio(tmp_path, with_pdf=True)
    assert (tmp_path / "index.html").is_file()
    assert (tmp_path / "procedures.json").is_file()
    assert not (tmp_path / "production-example.json").exists()
    assert not (tmp_path / "method-example.json").exists()
    assert not (tmp_path / "workbench").exists()
    assert not (tmp_path / "examples").exists()
    assert not (tmp_path / "inspector.js").exists()
