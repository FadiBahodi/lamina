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


def test_public_site_is_static_and_leaves_other_files_alone(tmp_path):
    from lamina.studio_site import prepare_website

    (tmp_path / "notes.txt").write_text("operator-owned file")
    prepare_website(tmp_path)
    prepare_website(tmp_path)
    page = (tmp_path / "index.html").read_text()
    assert "Generation requires an LLM connection" in page
    assert not re.search(r"<(script|form|button)\b", page)
    assert (tmp_path / "notes.txt").read_text() == "operator-owned file"
    assert (tmp_path / "assets/lamina-technical-paper.pdf").is_file()
    for relative in re.findall(r'(?:src|href)="([^\"]+)"', page):
        if relative.startswith(("https:", "#", "./")):
            continue
        assert (tmp_path / relative).is_file(), relative


def test_local_app_assets_replace_the_previous_copy_without_running_examples(tmp_path, monkeypatch):
    from lamina import method_example, production_example
    from lamina.studio_site import prepare_studio

    def forbidden(*args, **kwargs):
        raise AssertionError("application startup must not generate example content")

    monkeypatch.setattr(method_example, "method_demo", forbidden)
    monkeypatch.setattr(production_example, "production_demo", forbidden)
    target = tmp_path / "studio-static"
    target.mkdir()
    (target / "inspector.js").write_text("old showcase")
    prepare_studio(target)
    page = (target / "index.html").read_text()
    assert not (target / "inspector.js").exists()
    assert "production-workbench" in page
    for relative in re.findall(r'(?:src|href)="([^\"]+)"', page):
        if relative.startswith(("https:", "#", "./")):
            continue
        assert (target / relative).is_file(), relative
