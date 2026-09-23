"""Conservative quote recovery with offsets into the unchanged source text."""

from __future__ import annotations

from dataclasses import dataclass
import unicodedata


class ValidationFailure(ValueError):
    """An explicit model-contract failure that may be repaired by another call.

    ``partial`` retains already validated material for diagnosis. The runtime
    never turns it into a successful result or silently removes invalid rows.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str = "invalid_result",
        path: str = "",
        retryable: bool = True,
        partial: dict | list | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.path = path
        self.retryable = retryable
        self.partial = partial

    def feedback(self) -> dict:
        return {
            "code": self.code,
            "path": self.path,
            "message": str(self),
            "instruction": "Return a complete corrected result satisfying the original contract. Preserve valid material. Do not omit required material to avoid the error.",
        }


class QuoteMatchError(ValidationFailure):
    """The requested quote has no unique, conservative source match."""


@dataclass(frozen=True)
class QuoteMatch:
    quote: str
    start: int
    end: int
    method: str


_QUOTES = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"'})


def _normalized(text: str) -> tuple[str, list[tuple[int, int]]]:
    """Canonical decomposition, quote typography and collapsed whitespace.

    Every expanded character keeps the complete original combining sequence's
    span. Case, compatibility characters, units and numerical signs survive.
    """
    clusters: list[list[tuple[str, int, int]]] = []
    for offset, character in enumerate(text):
        for part in unicodedata.normalize("NFD", character):
            if not clusters or unicodedata.combining(part) == 0:
                clusters.append([])
            clusters[-1].append((part, offset, offset + 1))

    result: list[str] = []
    offsets: list[tuple[int, int]] = []
    for cluster in clusters:
        start = min(row[1] for row in cluster)
        end = max(row[2] for row in cluster)
        # Canonical ordering is stable for marks with the same combining class.
        ordered = sorted(cluster, key=lambda row: unicodedata.combining(row[0]))
        for character, _, _ in ordered:
            character = character.translate(_QUOTES)
            if character.isspace():
                if result and result[-1] == " ":
                    offsets[-1] = (offsets[-1][0], end)
                    continue
                character = " "
            result.append(character)
            offsets.append((start, end))
    return "".join(result), offsets


def resolve_quote(
    quote: str, text: str, *, allow_typography: bool = True
) -> QuoteMatch:
    """Return an exact source span, allowing only unambiguous typography repair.

    An exact quote wins immediately. Otherwise the normalized match must be
    unique and cover complete original characters. This does not establish that
    the quote supports a claim; it establishes where those words occurred.
    """
    if not isinstance(quote, str) or not quote.strip():
        raise QuoteMatchError("quote must be nonempty text", code="empty_quote")
    if not isinstance(text, str):
        raise TypeError("source text must be a string")
    start = text.find(quote)
    if start >= 0:
        return QuoteMatch(quote, start, start + len(quote), "exact")
    if not allow_typography:
        raise QuoteMatchError(
            "quote is not an exact source substring", code="quote_not_found"
        )

    normalized_text, offsets = _normalized(text)
    normalized_quote = _normalized(quote)[0].strip()
    spans = set()
    position = normalized_text.find(normalized_quote)
    while position >= 0:
        after = position + len(normalized_quote)
        start, end = offsets[position][0], offsets[after - 1][1]
        # Never match half of a decomposed original character or accent group.
        left_complete = position == 0 or offsets[position - 1][1] <= start
        right_complete = after == len(offsets) or offsets[after][0] >= end
        if left_complete and right_complete:
            spans.add((start, end))
            if len(spans) > 1:
                raise QuoteMatchError(
                    "normalized quote matches several source spans; quote an exact, distinguishing passage",
                    code="ambiguous_quote",
                )
        position = normalized_text.find(normalized_quote, position + 1)
    if not spans:
        raise QuoteMatchError(
            "quote is not an exact source substring or a unique typography match",
            code="quote_not_found",
        )
    start, end = spans.pop()
    return QuoteMatch(text[start:end], start, end, "typography")
