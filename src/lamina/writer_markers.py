"""Resolve compact writer markers into exact source and output links."""

from __future__ import annotations

import re

from .evidence import ValidationFailure

_MARKER = re.compile(
    r"\[\s*(s\d+(?:\s*[-–]\s*s\d+)?(?:\s*,\s*s\d+(?:\s*[-–]\s*s\d+)?)*)\s*\]"
)
_MARKER_LIKE = re.compile(r"\[\s*s\d+[^\]\n]*\]")
_NAMED_REFERENCE = re.compile(
    r"\[\s*(?:idea|unit|source|target)\s*:[^\]\n]*\]", re.IGNORECASE
)
_MARKER_SUFFIX_PUNCTUATION = frozenset(".,;:!?)]}\"'”’")


def _link_ranges(value: str) -> list[tuple[int, int]]:
    """Return inline Markdown link/image extents, including nested labels."""
    ranges = []
    position = 0
    while position < len(value):
        label_start = value.find("[", position)
        if label_start < 0:
            break
        depth, cursor = 1, label_start + 1
        while cursor < len(value) and depth:
            if value[cursor] == "\\":
                cursor += 2
                continue
            if value[cursor] == "[":
                depth += 1
            elif value[cursor] == "]":
                depth -= 1
            cursor += 1
        if depth or cursor >= len(value) or value[cursor] not in "([":
            position = label_start + 1
            continue
        opener = value[cursor]
        closer = ")" if opener == "(" else "]"
        destination_depth, end = 1, cursor + 1
        while end < len(value) and destination_depth:
            if value[end] == "\\":
                end += 2
                continue
            if value[end] == opener:
                destination_depth += 1
            elif value[end] == closer:
                destination_depth -= 1
            end += 1
        if not destination_depth:
            start = label_start - 1 if label_start and value[label_start - 1] == "!" else label_start
            ranges.append((start, end))
            position = end
        else:
            position = label_start + 1
    return ranges


def _protected_ranges(value: str) -> list[tuple[int, int]]:
    """Locate Markdown regions where marker-looking text is authored content.

    Removing a marker from code or a link destination would silently change the
    artifact. The writer must move that citation outside the construct instead.
    This is deliberately conservative; it is validation, not a Markdown parser.
    """
    from markdown_it import MarkdownIt

    lines = value.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    if not lines or offsets[-1] < len(value):
        offsets.append(len(value))
    tokens = MarkdownIt("commonmark").parse(value)
    ranges: list[tuple[int, int]] = [
        (offsets[token.map[0]], offsets[token.map[1]])
        for token in tokens
        if token.type in {"code_block", "fence", "html_block"} and token.map
    ]
    for token in tokens:
        if token.type != "inline" or not token.map:
            continue
        start, end = offsets[token.map[0]], offsets[token.map[1]]
        cursor = start
        for child in token.children or []:
            if child.type != "html_inline":
                continue
            position = value.find(child.content, cursor, end)
            if position >= 0:
                ranges.append((position, position + len(child.content)))
                cursor = position + len(child.content)
    for match in re.finditer(r"(?s)(`+)(?!`).*?\1", value):
        ranges.append(match.span())
    for match in re.finditer(r"(?m)^[ ]{0,3}\[[^\]\n]+\]:[^\n]*$", value):
        ranges.append(match.span())
    for match in re.finditer(
        r"<(?:[A-Za-z][A-Za-z0-9+.-]{1,31}:[^<>\s]*|"
        r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+)>",
        value,
    ):
        ranges.append(match.span())
    ranges.extend(_link_ranges(value))
    return ranges


def _validate_marker_location(value: str, match: re.Match, protected) -> None:
    if any(start <= match.start() < end for start, end in protected):
        raise ValidationFailure(
            "source markers must follow prose, outside code and link destinations",
            code="protected_writer_marker",
            path="body_marked",
        )
    if match.end() < len(value) and value[match.end()].isalnum():
        raise ValidationFailure(
            "source markers need a separator before following prose",
            code="adjacent_writer_marker_text",
            path="body_marked",
        )


def _is_escaped(value: str, position: int) -> bool:
    """Return whether Markdown backslash escaping makes this bracket literal."""
    slashes = 0
    position -= 1
    while position >= 0 and value[position] == "\\":
        slashes += 1
        position -= 1
    return slashes % 2 == 1


def _inside(position: int, ranges: list[tuple[int, int]]) -> bool:
    return any(start <= position < end for start, end in ranges)


def _span_index(units: dict[str, dict]) -> dict[str, tuple[str, int, dict]]:
    return {
        span["id"]: (unit_id, position, span)
        for unit_id, unit in units.items()
        for position, span in enumerate(unit.get("spans", []))
    }


def _evidence(marker: str, units: dict[str, dict], index: dict) -> list[dict]:
    evidence, seen = [], set()
    for item in marker.split(","):
        parts = re.split(r"\s*[-–]\s*", item.strip(), maxsplit=1)
        first, last = (parts[0], parts[0]) if len(parts) == 1 else parts
        if first not in index or last not in index:
            raise ValidationFailure(
                "writer marker names source text outside this section's context",
                code="foreign_writer_span",
                path="body_marked",
                retryable=False,
            )
        unit_id, first_position, start = index[first]
        last_unit, last_position, end = index[last]
        if unit_id != last_unit or first_position > last_position:
            raise ValidationFailure(
                "writer marker range must follow source order within one unit",
                code="invalid_writer_span_range",
                path="body_marked",
            )
        quote = units[unit_id]["text"][start["start"] : end["end"]]
        key = (unit_id, quote)
        if key not in seen:
            evidence.append({"unit_id": unit_id, "quote": quote})
            seen.add(key)
    return evidence


def materialize_marked_body(
    value, units: dict[str, dict], *, body_field: str = "body", claim_prefix: str = "claim"
) -> dict:
    """Strip valid markers and derive exact authored claims and source evidence.

    The claim attached to a marker begins after the previous marker or blank-line
    block boundary. This is an addressability rule, not an entailment judgment.
    """
    if not isinstance(value, str) or not value.strip() or len(value) > 200000:
        raise ValidationFailure("marked body must be nonempty text")
    protected = _protected_ranges(value)
    foreign = next(
        (
            match
            for match in _NAMED_REFERENCE.finditer(value)
            if not _is_escaped(value, match.start())
            and not _inside(match.start(), protected)
        ),
        None,
    )
    if foreign:
        raise ValidationFailure(
            "writer markers may name only supplied compact source spans",
            code="foreign_writer_span",
            path="body_marked",
            retryable=False,
        )
    index = _span_index(units)
    all_matches = list(_MARKER.finditer(value))
    matches = [
        match
        for match in all_matches
        if not _is_escaped(value, match.start())
    ]
    if not matches:
        raise ValidationFailure(
            "marked body needs at least one source marker such as [s0]",
            code="missing_writer_marker",
            path="body_marked",
        )
    for match in matches:
        _validate_marker_location(value, match, protected)
    clean_parts, claims, all_evidence = [], [], []
    source_cursor = 0
    clean_length = 0
    previous_claim_end = 0
    seen_evidence = set()
    for number, match in enumerate(matches, 1):
        before = value[source_cursor : match.start()]
        suffix_end = match.end()
        while (
            suffix_end < len(value)
            and value[suffix_end] in _MARKER_SUFFIX_PUNCTUATION
        ):
            suffix_end += 1
        suffix = value[match.end() : suffix_end]
        if suffix:
            # A model may place the marker between the sentence and its punctuation.
            # Remove only the horizontal seam it introduced; all other whitespace is
            # authored content. Moving the punctuation into this clean segment also
            # keeps it with this claim instead of the following one.
            before = before.rstrip(" \t")
        clean_parts.append(before)
        clean_parts.append(suffix)
        clean_length += len(before) + len(suffix)
        current = "".join(clean_parts)
        block_start = current.rfind("\n\n", previous_claim_end, clean_length)
        claim_start = max(previous_claim_end, block_start + 2 if block_start >= 0 else 0)
        while claim_start < clean_length and current[claim_start].isspace():
            claim_start += 1
        claim_end = clean_length
        while claim_end > claim_start and current[claim_end - 1].isspace():
            claim_end -= 1
        if claim_end <= claim_start:
            raise ValidationFailure(
                "each writer marker must follow supported authored text",
                code="empty_marked_claim",
                path="body_marked",
            )
        evidence = _evidence(match.group(1), units, index)
        for row in evidence:
            key = (row["unit_id"], row["quote"])
            if key not in seen_evidence:
                all_evidence.append(row)
                seen_evidence.add(key)
        claims.append(
            {
                "id": f"{claim_prefix}_{number}",
                "text": current[claim_start:claim_end],
                "body_field": body_field,
                "evidence": evidence,
            }
        )
        previous_claim_end = clean_length
        source_cursor = suffix_end
    clean_parts.append(value[source_cursor:])
    body = "".join(clean_parts).strip()
    if any(
        not _is_escaped(body, match.start())
        for match in _MARKER_LIKE.finditer(body)
    ):
        raise ValidationFailure(
            "writer body contains a malformed or unresolved source marker",
            code="invalid_writer_marker",
            path="body_marked",
        )
    return {"body": body, "evidence": all_evidence, "claims": claims}
