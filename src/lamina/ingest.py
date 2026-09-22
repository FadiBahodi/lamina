"""Mechanical source decomposition with stable identity and honest locators."""

from __future__ import annotations

import hashlib
import re
import subprocess
import tempfile
from pathlib import Path

from .store import Workspace

SUPPORTED = {".md", ".txt", ".pdf", ".pptx"}
MAX_CHARS = 12000


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
    """Use Markdown's parser so fenced code cannot become a section heading."""
    from markdown_it import MarkdownIt

    lines = text.splitlines()
    tokens = MarkdownIt("commonmark").parse(text)
    heading, start = title, 0
    for index, token in enumerate(tokens):
        if token.type != "heading_open" or token.level != 0:
            continue
        lo, hi = token.map
        body = "\n".join(lines[start:lo])
        if body.strip():
            yield heading, body, start + 1
        heading = tokens[index + 1].content
        start = hi
    body = "\n".join(lines[start:])
    if body.strip():
        yield heading, body, start + 1


def _structured_chunks(text):
    """Pack complete Markdown blocks. Never slice a list, table or code fence."""
    from markdown_it import MarkdownIt

    lines = text.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    tokens = MarkdownIt("commonmark").enable("table").parse(text)
    spans = [
        (offsets[t.map[0]], offsets[t.map[1]], t.type)
        for t in tokens
        if t.level == 0 and t.map and t.nesting != -1
    ]
    start = end = None
    previous = 0
    for index, (_, hi, kind) in enumerate(spans):
        lo, previous = previous, hi
        if index == len(spans) - 1:
            hi = len(text)
        if start is not None and hi - start > MAX_CHARS:
            yield start, end, text[start:end].strip()
            start = end = None
        if hi - lo > MAX_CHARS and kind == "paragraph_open":
            for a, b, value in _chunks(text[lo:hi]):
                yield lo + a, lo + b, value
        else:
            if start is None:
                start = lo
            end = hi
    if start is not None:
        yield start, end, text[start:end].strip()
    elif not spans and text.strip():
        yield from _chunks(text)


def _pptx_chunks(path):
    try:
        from pptx import Presentation
    except ImportError as exc:
        raise ValueError(
            'PowerPoint support requires: pip install "lamina-engine[slides]"'
        ) from exc
    from zipfile import ZipFile

    with ZipFile(path) as archive:
        if sum(info.file_size for info in archive.infolist()) > 100_000_000:
            raise ValueError("PPTX expanded contents exceed 100 MB; split the deck")
    for number, slide in enumerate(Presentation(path).slides, 1):
        heading = slide.shapes.title.text if slide.shapes.title else f"Slide {number}"
        found = False

        def walk(shapes):
            for shape in sorted(shapes, key=lambda s: (s.top, s.left)):
                if hasattr(shape, "shapes"):
                    yield from walk(shape.shapes)
                else:
                    yield shape

        for shape in walk(slide.shapes):
            if shape.has_table:
                # Row/column boundaries remain explicit; cells are not flattened.
                rows = [
                    [
                        cell.text.replace("\n", " / ").replace("|", "\\|")
                        for cell in row.cells
                    ]
                    for row in shape.table.rows
                ]
                value = "\n".join(" | ".join(row) for row in rows)
                kind = "table"
            elif shape.has_text_frame:
                value = "\n".join(
                    "  " * p.level + p.text for p in shape.text_frame.paragraphs
                )
                kind = "text"
            else:
                continue
            if value.strip():
                found = True
                yield heading, value.strip(), f"slide {number}, {kind} {shape.shape_id}"
        if slide.has_notes_slide:
            frame = slide.notes_slide.notes_text_frame
            if frame is not None and frame.text.strip():
                found = True
                yield heading, frame.text.strip(), f"slide {number}, speaker notes"
        if not found:
            raise ValueError(
                f"{path.name}, slide {number}: no extractable text; inspect visuals or convert and OCR first"
            )


def read_source(
    path: Path, role: str = "teaching", *, ocr: bool = False
) -> tuple[dict, list[dict]]:
    if role not in {"teaching", "assessment"}:
        raise ValueError("role must be teaching or assessment")
    if path.suffix.lower() not in SUPPORTED:
        raise ValueError(
            f"Unsupported input: {path.name}; use Markdown, text, PDF, or PPTX (convert legacy .ppt first)"
        )
    raw = path.read_bytes()
    checksum = hashlib.sha256(raw).hexdigest()
    source_id = "src_" + checksum[:20]
    title = path.stem.replace("_", " ").replace("-", " ").strip()
    chunks = []
    if path.suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ValueError(
                'PDF support requires: pip install "lamina-engine[pdf]"'
            ) from exc
        # Explicit local preprocessing. Native text pages remain untouched.
        # The source checksum always identifies the original input file.
        if ocr:
            with tempfile.TemporaryDirectory(prefix="lamina-ocr-") as temporary:
                output = Path(temporary) / "searchable.pdf"
                try:
                    subprocess.run(
                        [
                            "ocrmypdf",
                            "--skip-text",
                            "--",
                            str(path.resolve()),
                            str(output),
                        ],
                        check=True,
                        capture_output=True,
                        timeout=1800,
                    )
                except FileNotFoundError as exc:
                    raise ValueError(
                        "Install OCRmyPDF and its Tesseract dependency to use --ocr"
                    ) from exc
                except (
                    subprocess.CalledProcessError,
                    subprocess.TimeoutExpired,
                ) as exc:
                    raise ValueError(
                        f"OCR failed for {path.name}; original input was not changed"
                    ) from exc
                from io import BytesIO

                reader = PdfReader(BytesIO(output.read_bytes()))
        else:
            reader = PdfReader(path)
        for page_number, page in enumerate(reader.pages, 1):
            text = page.extract_text() or ""
            if not text.strip():
                raise ValueError(
                    f"{path.name}, page {page_number}: no extractable text; OCR first (image-only pages are not silently skipped)"
                )
            for _, _, value in _chunks(text):
                chunks.append((title, value, f"page {page_number}"))
    elif path.suffix.lower() == ".pptx":
        chunks.extend(_pptx_chunks(path))
    else:
        text = raw.decode("utf-8-sig")
        first_title = re.search(r"^#\s+(.+)$", text, re.M)
        if first_title:
            title = first_title.group(1).strip()
        for heading, body, first_line in _text_sections(text, title):
            for start, end, value in (
                _structured_chunks(body)
                if path.suffix.lower() == ".md"
                else _chunks(body)
            ):
                lo = first_line + body[:start].count("\n")
                hi = first_line + body[:end].count("\n")
                chunks.append((heading, value, f"lines {lo}–{hi}"))
    if not chunks:
        raise ValueError(f"{path.name} has no readable content")
    source = {
        "id": source_id,
        "title": title,
        "filename": path.name,
        "sha256": checksum,
        "role": role,
        "parser": "structured-text-2",
        "ocr": bool(ocr and path.suffix.lower() == ".pdf"),
        "limits": "Text extraction does not interpret diagrams, charts, or image meaning.",
    }
    units = []
    for ordinal, (heading, text, locator) in enumerate(chunks):
        unit_id = (
            "unit_"
            + hashlib.sha256(f"{source_id}:{ordinal}:{text}".encode()).hexdigest()[:20]
        )
        units.append(
            {
                "id": unit_id,
                "source_id": source_id,
                "heading": heading,
                "text": text,
                "locator": locator,
                "ordinal": ordinal,
                "role": role,
                "content_id": hashlib.sha256(f"{heading}\n{text}".encode()).hexdigest(),
            }
        )
    return source, units


def ingest_paths(
    paths: list[Path],
    workspace: Workspace,
    role: str = "teaching",
    *,
    ocr: bool = False,
) -> dict:
    discovered = []
    for input_path in paths:
        path = Path(input_path)
        if not path.exists():
            raise ValueError(f"Input does not exist: {path}")
        if path.is_dir():
            discovered.extend(
                p
                for p in sorted(path.rglob("*"))
                if p.is_file() and p.suffix.lower() in SUPPORTED
            )
        else:
            discovered.append(path)
    if not discovered:
        raise ValueError("No supported files found")
    # Parse the entire batch before storing anything, so extraction failures
    # cannot leave a deceptively complete partial import.
    parsed = [read_source(p, role, ocr=ocr) for p in discovered]
    existing = {s["id"]: s for s in workspace.sources()}
    for source, _ in parsed:
        if source["id"] in existing and existing[source["id"]]["role"] != role:
            raise ValueError(
                "Identical content already exists under another source role"
            )
    new_sources = 0
    for source, units in parsed:
        if source["id"] not in existing:
            new_sources += 1
            existing[source["id"]] = source
    workspace.import_sources(parsed)
    return {
        "files_read": len(parsed),
        "new_sources": new_sources,
        "duplicates": len(parsed) - new_sources,
        **workspace.stats(),
    }
