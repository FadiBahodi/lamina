"""Local similarity without model calls: term vectors or provider embeddings.

Similarity nominates candidates. It never establishes equivalence, so it is
never sufficient authority to delete an output on its own. Duplicate
suppression has two lanes: an exact-identity lane (normalised text identical)
and a near-duplicate lane that requires the similarity threshold *and* a
meaning guard. The guard compares the tokens a vector representation is blind
to: numbers and units, negations, short abbreviations, and word order. Two
cards that differ in any of those are kept, and the pair is reported as
related instead of merged.

Suppression compares each candidate against the kept set only, so a chain of
progressively different claims cannot collapse into one, and pair work is
bounded by an inverted index (sparse) or per-candidate products (dense)
instead of an all-pairs matrix.

A provider may expose ``embed(texts) -> list[list[float]]``. When it does, the
dense vectors are used; otherwise TF-IDF term vectors over the same texts are
used. Both are reported by name so a receipt says which similarity it relied on.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict

_TOKEN = re.compile(r"\w+")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
_ABBREVIATION = re.compile(r"\b[A-Z][A-Z0-9]{0,5}\b")
_UNITS = frozenset(
    {
        "mg", "mcg", "ug", "g", "kg", "ml", "l", "dl", "mmol", "mol", "meq", "iu", "u",
        "mmhg", "kpa", "bpm", "min", "h", "hr", "hrs", "s", "sec", "d", "wk", "mo", "yr",
        "ms", "cm", "mm", "m", "km", "lb", "oz", "pct",
    }
)
_NEGATION = frozenset(
    {
        "no", "not", "never", "none", "nor", "neither", "without", "non", "cannot",
        "unless", "except", "absent", "avoid", "lack", "lacks", "lacking",
        "contraindicated", "contraindication", "false", "incorrect", "unlikely",
    }
)

DEFAULT_THRESHOLDS = {
    # Nomination thresholds: pairs at or above go to a model comparison.
    "nominate": {"embedding": 0.72, "tfidf": 0.20},
    # Duplicate suppression thresholds: conservative by design.
    "duplicate": {"embedding": 0.92, "tfidf": 0.80},
}


def tokenize(text: str) -> list[str]:
    """Every word token, case-folded. Short tokens stay: "MI", "GI", "no" and
    "IV" are exactly the tokens that distinguish otherwise identical cards."""
    return _TOKEN.findall(text.casefold())


def normalised(text: str) -> str:
    """Identity key for the exact lane: tokens joined by single spaces."""
    return " ".join(tokenize(text))


def discriminators(text: str) -> dict:
    """The parts of a text that similarity cannot see but meaning depends on.

    ``numbers`` are the numeric literals in order (so 0.1 and 1 differ),
    ``negations`` the negation tokens, ``short`` the capitalised abbreviations
    (MI, GI, IV, ECG) and unit tokens, and ``bigrams`` the ordered token pairs
    used for the word-order check. Lower-case function words ("a", "of") are
    not discriminators; two phrasings of one fact may differ in those.
    """
    tokens = tokenize(text)
    abbreviations = [match.casefold() for match in _ABBREVIATION.findall(text)]
    return {
        "numbers": tuple(_NUMBER.findall(text.casefold())),
        "negations": Counter(token for token in tokens if token in _NEGATION),
        "short": Counter(abbreviations)
        + Counter(token for token in tokens if token in _UNITS),
        "bigrams": set(zip(tokens, tokens[1:])),
    }


def same_meaning_guard(a: str, b: str) -> str | None:
    """Return ``None`` when nothing the vectors are blind to differs between
    ``a`` and ``b``; otherwise the name of the first difference found."""
    da, db = discriminators(a), discriminators(b)
    if da["numbers"] != db["numbers"]:
        return "numbers"
    if da["negations"] != db["negations"]:
        return "negation"
    if da["short"] != db["short"]:
        return "abbreviation or unit"
    union = da["bigrams"] | db["bigrams"]
    if union and len(da["bigrams"] & db["bigrams"]) / len(union) < 0.5:
        return "word order"
    return None


def term_vectors(texts: list[str]) -> list[dict[str, float]]:
    """L2-normalised TF-IDF vectors. Terms in more than max(32, N/5) texts are
    dropped from the *vector* because they carry no discrimination and would
    dominate pair work; the exact lane and the meaning guard do not depend on
    the vector, so a corpus of identical texts still collapses to one."""
    counts = [Counter(tokenize(text)) for text in texts]
    document_frequency = Counter()
    for count in counts:
        document_frequency.update(count.keys())
    n = len(texts)
    cutoff = max(32, n // 5)
    idf = {
        term: math.log((1 + n) / (1 + df)) + 1.0
        for term, df in document_frequency.items()
        if df <= cutoff
    }
    vectors = []
    for count in counts:
        vector = {
            term: (1 + math.log(tf)) * idf[term]
            for term, tf in count.items()
            if term in idf
        }
        norm = math.sqrt(sum(value * value for value in vector.values()))
        vectors.append(
            {term: value / norm for term, value in vector.items()} if norm else {}
        )
    return vectors


def _normalise_dense(vector):
    norm = math.sqrt(sum(value * value for value in vector))
    return [value / norm for value in vector] if norm else list(vector)


def vectors_for(provider, texts: list[str]) -> tuple[str, list]:
    """Return ``(method, vectors)``: provider embeddings when offered, else TF-IDF."""
    embed = getattr(provider, "embed", None)
    if callable(embed) and texts:
        dense = embed(list(texts))
        if (
            not isinstance(dense, list)
            or len(dense) != len(texts)
            or any(
                not isinstance(row, list)
                or not row
                or any(type(value) not in (int, float) for value in row)
                for row in dense
            )
            or len({len(row) for row in dense}) != 1
        ):
            raise ValueError(
                "provider.embed must return one equal-length numeric vector per text"
            )
        return "embedding", [_normalise_dense(row) for row in dense]
    return "tfidf", term_vectors(texts)


def cosine(a, b) -> float:
    if isinstance(a, dict):
        if len(a) > len(b):
            a, b = b, a
        return sum(value * b.get(term, 0.0) for term, value in a.items())
    return sum(x * y for x, y in zip(a, b))


_BLOCK = 1024


def _dense_rows(vectors, threshold: float):
    """Yield ``(index, [(other, score), ...])`` with ``score >= threshold`` for
    unit vectors, in blocks of rows so memory is O(block × N), never O(N²)."""
    try:
        import numpy  # type: ignore
    except ImportError:  # pragma: no cover - exercised only without numpy
        n = len(vectors)
        for i in range(n):
            yield i, [
                (j, cosine(vectors[i], vectors[j]))
                for j in range(n)
                if j != i and cosine(vectors[i], vectors[j]) >= threshold
            ]
        return
    matrix = numpy.asarray(vectors, dtype=float)
    n = len(vectors)
    for start in range(0, n, _BLOCK):
        block = matrix[start : start + _BLOCK] @ matrix.T
        for offset, row in enumerate(block):
            index = start + offset
            hits = numpy.nonzero(row >= threshold)[0]
            yield index, [(int(j), float(row[j])) for j in hits if j != index]


def _sparse_rows(vectors, threshold: float):
    """Scores at or above ``threshold`` for each row via an inverted index;
    O(Σ postings²) over the terms that survive the document-frequency cutoff."""
    postings = defaultdict(list)
    for index, vector in enumerate(vectors):
        for term, value in vector.items():
            postings[term].append((index, value))
    rows = [defaultdict(float) for _ in vectors]
    for members in postings.values():
        for index, value in members:
            row = rows[index]
            for other, other_value in members:
                if other != index:
                    row[other] += value * other_value
    for index, row in enumerate(rows):
        yield index, [(j, s) for j, s in row.items() if s >= threshold]


def nearest_pairs(vectors, k: int, threshold: float) -> list[dict]:
    """Up to ``k`` neighbours per item at or above ``threshold``, as unique pairs.

    Each pair is ``{"ids": (i, j), "score": s}`` with ``i < j``. A threshold
    bounds the model work that follows; it is a workload choice, not a claim
    that lower-scored pairs are unrelated.
    """
    if not vectors:
        return []
    dense = not isinstance(vectors[0], dict)
    rows = _dense_rows(vectors, threshold) if dense else _sparse_rows(vectors, threshold)
    pairs = {}
    for index, candidates in rows:
        candidates = sorted(candidates, key=lambda item: (-item[1], item[0]))
        for other, score in candidates[:k]:
            key = (min(index, other), max(index, other))
            if key not in pairs or pairs[key] < score:
                pairs[key] = score
    return [
        {"ids": key, "score": round(score, 6)} for key, score in sorted(pairs.items())
    ]


class _KeptIndex:
    """Scores of one candidate against the kept set only, without all-pairs work."""

    def __init__(self, dense: bool):
        self.dense = dense
        self.kept: list[int] = []
        self.postings: dict = defaultdict(list)
        self.matrix = None
        self.rows: list = []

    def scores(self, index, vector) -> list[tuple[int, float]]:
        if not self.kept:
            return []
        if self.dense:
            try:
                import numpy  # type: ignore

                if self.matrix is None or len(self.matrix) != len(self.kept):
                    self.matrix = numpy.asarray(self.rows, dtype=float)
                products = self.matrix @ numpy.asarray(vector, dtype=float)
                return [(k, float(s)) for k, s in zip(self.kept, products)]
            except ImportError:  # pragma: no cover
                return [(k, cosine(vector, row)) for k, row in zip(self.kept, self.rows)]
        accumulated = defaultdict(float)
        for term, value in vector.items():
            for kept_index, kept_value in self.postings.get(term, ()):
                accumulated[kept_index] += value * kept_value
        return list(accumulated.items())

    def add(self, index, vector) -> None:
        self.kept.append(index)
        if self.dense:
            self.rows.append(vector)
            self.matrix = None
        else:
            for term, value in vector.items():
                self.postings[term].append((index, value))


def suppress_duplicates(
    vectors, threshold: float, texts: list[str] | None = None
) -> tuple[list[int], dict, dict]:
    """Keep the first of each duplicate run in the given order.

    Returns ``(kept, suppressed, related)``. ``suppressed`` maps a dropped index
    to ``{"duplicate_of", "score", "kind"}`` where ``kind`` is ``"exact"`` for
    identical normalised text or ``"near"`` for a pair at or above
    ``threshold`` that also passes :func:`same_meaning_guard`. ``related`` maps
    an index that reached the threshold but failed the guard to
    ``{"related_to", "score", "kept_because"}``; such an item is kept.

    Without ``texts`` there is no exact lane and no guard: the threshold alone
    decides, which is appropriate only for callers that nominate rather than
    delete. An item is compared only with already kept items, so a→b and b→c
    cannot drop c through b when a and c are distinct.
    """
    if not vectors:
        return [], {}, {}
    dense = not isinstance(vectors[0], dict)
    index = _KeptIndex(dense)
    kept, suppressed, related = [], {}, {}
    identity: dict[str, int] = {}
    for position, vector in enumerate(vectors):
        if texts is not None:
            key = normalised(texts[position])
            if key in identity:
                suppressed[position] = {
                    "duplicate_of": identity[key], "score": 1.0, "kind": "exact",
                }
                continue
        candidates = [(k, s) for k, s in index.scores(position, vector) if s >= threshold]
        candidates.sort(key=lambda item: (-item[1], item[0]))
        decision = None
        for other, score in candidates:
            reason = (
                None if texts is None else same_meaning_guard(texts[position], texts[other])
            )
            if reason is None:
                decision = {"duplicate_of": other, "score": round(score, 6), "kind": "near"}
                break
            if position not in related:
                related[position] = {
                    "related_to": other, "score": round(score, 6), "kept_because": reason,
                }
        if decision is not None:
            suppressed[position] = decision
            continue
        kept.append(position)
        index.add(position, vector)
        if texts is not None:
            identity[normalised(texts[position])] = position
    return kept, suppressed, related


def query_scores(query: str, vectors, method: str, texts=None, provider=None):
    """Score a text query against stored vectors with the same method."""
    if method == "embedding":
        query_vector = vectors_for(provider, [query])[1][0]
        return [cosine(query_vector, vector) for vector in vectors]
    # Rebuild the IDF over the stored texts so the query shares its weighting.
    combined = term_vectors(list(texts) + [query])
    query_vector = combined[-1]
    return [cosine(query_vector, vector) for vector in combined[:-1]]
