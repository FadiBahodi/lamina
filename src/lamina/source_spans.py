"""Deterministic addresses into unchanged source text.

Spans follow blank-line paragraph boundaries. Tables, list blocks and other
parser-owned structures stay intact. These are text addresses, not sentences,
claims, or an estimate of how much meaning an extraction preserved.
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
    "fence",
    "html_block",
}


def source_spans(unit_id: str, text: str, kind: str | None = None) -> list[dict]:
    """Address complete paragraphs, retaining every original character once.

    Separating whitespace belongs to the preceding paragraph. A reference to a
    contiguous range therefore reconstructs the original source byte-for-byte
    after UTF-8 encoding. Offsets themselves count Python Unicode characters.
    """
    if not text:
        return []
    ends = (
        []
        if kind in _ATOMIC_KINDS
        else [match.end() for match in _PARAGRAPH_BREAK.finditer(text)]
    )
    if not ends or ends[-1] != len(text):
        ends.append(len(text))
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
