"""Deterministic addresses into unchanged source text.

Prose spans use conservative sentence boundaries inside parser-owned units.
Tables, list blocks and other atomic structures stay intact. Boundaries make
source pointers convenient; exact offsets and source text remain authoritative.
"""

from __future__ import annotations

import re

from .evidence import ValidationFailure

_PARAGRAPH_BREAK = re.compile(r"\r?\n[ \t]*\r?\n(?:[ \t]*\r?\n)*")
_ATOMIC_KINDS = {
    "table",
    "list",
    "bullet_list",
    "ordered_list",
    "code",
    "code_block",
    "fence",
    "html_block",
}

_ABBREVIATIONS = {
    "approx",
    "dept",
    "dr",
    "e.g",
    "etc",
    "fig",
    "i.e",
    "mr",
    "mrs",
    "ms",
    "no",
    "prof",
    "st",
    "vs",
}


def _sentence_boundaries(text: str, start: int, end: int) -> list[int]:
    """Return conservative ends, attaching whitespace to the prior sentence.

    This deliberately leaves uncertain abbreviations and lowercase continuations
    together. A missed boundary only produces a broader address; source offsets
    and materialized text do not change.
    """
    boundaries = []
    position = start
    while position < end:
        if text[position] not in ".!?":
            position += 1
            continue
        punctuation_start = position
        while position + 1 < end and text[position + 1] in ".!?":
            position += 1
        punctuation_end = position + 1
        while punctuation_end < end and text[punctuation_end] in '\"\'”’)]}':
            punctuation_end += 1
        if punctuation_end < end and not text[punctuation_end].isspace():
            position += 1
            continue
        prefix = text[start : position + 1]
        if text[position] == ".":
            word = re.search(r"([A-Za-z]+(?:\.[A-Za-z]+)*)\.$", prefix)
            token = word.group(1).lower() if word else ""
            if token in _ABBREVIATIONS or (len(token) == 1 and token.isalpha()):
                position += 1
                continue
            if (
                punctuation_start > start
                and punctuation_start + 1 < end
                and text[punctuation_start - 1].isdigit()
                and text[punctuation_start + 1].isdigit()
            ):
                position += 1
                continue
        next_start = punctuation_end
        while next_start < end and text[next_start].isspace():
            next_start += 1
        if next_start < end and text[next_start].islower():
            position += 1
            continue
        boundary = next_start if next_start < end else end
        if boundary > start and boundary not in boundaries:
            boundaries.append(boundary)
        position = max(position + 1, next_start)
    if not boundaries or boundaries[-1] != end:
        boundaries.append(end)
    return boundaries


def source_spans(unit_id: str, text: str, kind: str | None = None) -> list[dict]:
    """Address prose sentences, retaining every original character once.

    Separating whitespace belongs to the preceding paragraph. A reference to a
    contiguous range therefore reconstructs the original source byte-for-byte
    after UTF-8 encoding. Offsets themselves count Python Unicode characters.
    """
    if not text:
        return []
    if kind in _ATOMIC_KINDS:
        ends = [len(text)]
    else:
        paragraphs, paragraph_start = [], 0
        for match in _PARAGRAPH_BREAK.finditer(text):
            paragraphs.append((paragraph_start, match.end()))
            paragraph_start = match.end()
        if paragraph_start < len(text):
            paragraphs.append((paragraph_start, len(text)))
        ends = [
            boundary
            for paragraph_start, paragraph_end in paragraphs
            for boundary in _sentence_boundaries(text, paragraph_start, paragraph_end)
        ]
    result, start = [], 0
    for end in ends:
        if end > start:
            result.append(
                {"id": f"{unit_id}:s{len(result)}", "start": start, "end": end}
            )
        start = end
    return result


def index_source_spans(units: dict[str, dict]) -> dict:
    """Build the trusted index once for all references in a reader response."""
    return {
        span["id"]: (unit_id, position, span)
        for unit_id, unit in units.items()
        for position, span in enumerate(
            source_spans(unit_id, unit["text"], unit.get("kind"))
        )
    }


def materialize_references(
    references, units: dict[str, dict], *, index: dict | None = None
) -> list[dict]:
    """Resolve owned span IDs/ranges to canonical exact source quotations.

    The index is rebuilt from source text; model-supplied offsets or indexes are
    never trusted. A range must remain in one unit and follow source order.
    """
    if not isinstance(references, list) or not references:
        raise ValidationFailure("evidence_refs must be a nonempty list")
    if index is None:
        index = index_source_spans(units)
    evidence, seen = [], set()
    for n, reference in enumerate(references):
        path = f"evidence_refs[{n}]"
        if isinstance(reference, str):
            reference = {"span_id": reference}
        if (
            not isinstance(reference, dict)
            or not set(reference).issubset({"span_id", "end_span_id", "phrase"})
            or not isinstance(reference.get("span_id"), str)
        ):
            raise ValidationFailure(
                "a source reference needs span_id and optional end_span_id/phrase",
                path=path,
            )
        first = reference["span_id"]
        last = reference.get("end_span_id", first)
        if not isinstance(last, str) or first not in index or last not in index:
            raise ValidationFailure(
                "source references may name only owned core spans",
                code="foreign_span",
                path=path,
                retryable=False,
            )
        unit_id, first_position, start = index[first]
        last_unit, last_position, end = index[last]
        if unit_id != last_unit or first_position > last_position:
            raise ValidationFailure(
                "a source range must follow source order within one unit",
                code="invalid_span_range",
                path=path,
            )
        quote = units[unit_id]["text"][start["start"] : end["end"]]
        if "phrase" in reference:
            phrase = reference["phrase"]
            if not isinstance(phrase, str) or not phrase.strip():
                raise ValidationFailure("phrase must be nonempty text", path=path)
            position = quote.find(phrase)
            if position < 0 or quote.find(phrase, position + 1) >= 0:
                raise ValidationFailure(
                    "phrase must occur exactly once within the addressed range; "
                    "omit phrase to cite that complete range",
                    code="ambiguous_or_missing_phrase",
                    path=path,
                )
            quote = phrase
        key = (unit_id, quote)
        if key not in seen:
            evidence.append({"unit_id": unit_id, "quote": quote})
            seen.add(key)
    return evidence
