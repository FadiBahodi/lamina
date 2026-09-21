"""Give page assets content-derived URLs so a cached release cannot mix styles."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path


def fingerprint_page_assets(root: Path) -> None:
    page = root / 'index.html'
    body = page.read_text(encoding='utf-8')
    def replace(match: re.Match) -> str:
        attribute, relative = match.groups()
        if relative.startswith(('/', '//')) or ':' in relative or '?' in relative or '#' in relative:
            return match.group(0)
        source = (root / relative).resolve()
        if not source.is_relative_to(root.resolve()) or not source.is_file() or source.suffix not in {'.js', '.css', '.svg'}:
            return match.group(0)
        data = source.read_bytes()
        name = source.with_name(f'{source.stem}.{hashlib.sha256(data).hexdigest()[:12]}{source.suffix}')
        name.write_bytes(data)
        return f'{attribute}="{name.relative_to(root.resolve()).as_posix()}"'
    page.write_text(re.sub(r'(src|href)="([^"]+)"', replace, body), encoding='utf-8')
