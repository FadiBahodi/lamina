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
