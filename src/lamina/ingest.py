"""Mechanical source decomposition with stable identity and honest locators."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .store import Workspace

SUPPORTED = {".md", ".txt", ".pdf"}
MAX_CHARS = 1800


def _chunks(text: str, maximum: int = MAX_CHARS):
    """Keep paragraph boundaries when possible; never drop an oversized span."""
    start = 0
    while start < len(text):
        end = min(start + maximum, len(text))
        if end < len(text):
            boundary = text.rfind("\n\n", start, end)
            if boundary <= start + maximum // 3:
                boundary = text.rfind(" ", start, end)
            if boundary > start:
                end = boundary
        value = text[start:end].strip()
        if value:
            yield start, end, value
        start = end
        while start < len(text) and text[start].isspace():
            start += 1


def _text_sections(text: str, title: str):
    heading = title
    body = []
    start_line = 1
    for number, line in enumerate(text.splitlines(), 1):
        match = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", line)
        if match:
            if "\n".join(body).strip():
                yield heading, "\n".join(body), start_line
            heading = match.group(1)
            body = []
            start_line = number + 1
        else:
            body.append(line)
    if "\n".join(body).strip():
        yield heading, "\n".join(body), start_line


def read_source(path: Path, role: str = "teaching") -> tuple[dict, list[dict]]:
    if role not in {"teaching", "assessment"}:
        raise ValueError("role must be teaching or assessment")
    if path.suffix.lower() not in SUPPORTED:
        raise ValueError(f"Unsupported input: {path.name}; use Markdown, text, or PDF")
    raw = path.read_bytes()
    checksum = hashlib.sha256(raw).hexdigest()
    source_id = "src_" + checksum[:20]
    title = path.stem.replace("_", " ").replace("-", " ").strip()
    chunks = []
    if path.suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ValueError('PDF support requires: pip install "lamina-engine[pdf]"') from exc
        reader = PdfReader(path)
        for page_number, page in enumerate(reader.pages, 1):
            text = page.extract_text() or ""
            if not text.strip():
                raise ValueError(f"{path.name}, page {page_number}: no extractable text; OCR first (image-only pages are not silently skipped)")
            for _, _, value in _chunks(text):
                chunks.append((title, value, f"page {page_number}"))
    else:
        text = raw.decode("utf-8-sig")
        first_title = re.search(r"^#\s+(.+)$", text, re.M)
        if first_title:
            title = first_title.group(1).strip()
        for heading, body, first_line in _text_sections(text, title):
            for start, end, value in _chunks(body):
                lo = first_line + body[:start].count("\n")
                hi = first_line + body[:end].count("\n")
                chunks.append((heading, value, f"lines {lo}–{hi}"))
    if not chunks:
        raise ValueError(f"{path.name} has no readable content")
    source = {"id": source_id, "title": title, "filename": path.name, "sha256": checksum, "role": role}
    units = []
    for ordinal, (heading, text, locator) in enumerate(chunks):
        unit_id = "unit_" + hashlib.sha256(f"{source_id}:{ordinal}:{text}".encode()).hexdigest()[:20]
        units.append({"id": unit_id, "source_id": source_id, "heading": heading, "text": text,
                      "locator": locator, "ordinal": ordinal, "role": role})
    return source, units


def ingest_paths(paths: list[Path], workspace: Workspace, role: str = "teaching") -> dict:
    discovered = []
    for input_path in paths:
        path = Path(input_path)
        if not path.exists():
            raise ValueError(f"Input does not exist: {path}")
        if path.is_dir():
            discovered.extend(p for p in sorted(path.rglob("*")) if p.is_file() and p.suffix.lower() in SUPPORTED)
        else:
            discovered.append(path)
    if not discovered:
        raise ValueError("No supported files found")
    # Parse the entire batch before storing anything, so extraction failures
    # cannot leave a deceptively complete partial import.
    parsed = [read_source(p, role) for p in discovered]
    existing = {s["id"]: s for s in workspace.sources()}
    for source, _ in parsed:
        if source["id"] in existing and existing[source["id"]]["role"] != role:
            raise ValueError("Identical content already exists under another source role")
    new_sources = 0
    for source, units in parsed:
        if source["id"] not in existing:
            new_sources += 1
            existing[source["id"]] = source
        workspace.put_source(source)
        workspace.put_units(units)
    return {"files_read": len(parsed), "new_sources": new_sources, "duplicates": len(parsed) - new_sources,
            **workspace.stats()}
