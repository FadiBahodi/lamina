"""Local similarity without model calls: term vectors or provider embeddings.

Similarity nominates candidates. It never establishes equivalence, and a
threshold relation is not transitive, so nothing here merges by connected
components. Duplicate suppression compares each candidate against the kept
set only, which prevents a chain of progressively different claims from
collapsing into one.

A provider may expose ``embed(texts) -> list[list[float]]``. When it does, the
dense vectors are used; otherwise TF-IDF term vectors over the same texts are
used. Both are reported by name so a receipt says which similarity it relied on.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict

_TOKEN = re.compile(r"\w+")

DEFAULT_THRESHOLDS = {
    # Nomination thresholds: pairs at or above go to a model comparison.
    "nominate": {"embedding": 0.72, "tfidf": 0.20},
    # Duplicate suppression thresholds: conservative by design.
    "duplicate": {"embedding": 0.92, "tfidf": 0.80},
}


def tokenize(text: str) -> list[str]:
    return [
        token
        for token in _TOKEN.findall(text.casefold())
        if len(token) > 2 or any(c.isdigit() for c in token)
    ]


def term_vectors(texts: list[str]) -> list[dict[str, float]]:
    """L2-normalised TF-IDF vectors. Terms in more than max(32, N/5) texts are
    dropped: they carry no discrimination and would dominate pair work."""
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


def _dense_scores(vectors):
    """All-pairs dot products for unit vectors, with numpy when available."""
    try:
        import numpy  # type: ignore

        matrix = numpy.asarray(vectors, dtype=float)
        return (matrix @ matrix.T).tolist()
    except ImportError:  # pragma: no cover - exercised only without numpy
        n = len(vectors)
        return [
            [cosine(vectors[i], vectors[j]) if i != j else 1.0 for j in range(n)]
            for i in range(n)
        ]


def _sparse_scores(vectors):
    """Scores above zero for each row via an inverted index; O(Σ postings²)."""
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
    return rows


def nearest_pairs(vectors, k: int, threshold: float) -> list[dict]:
    """Up to ``k`` neighbours per item at or above ``threshold``, as unique pairs.

    Each pair is ``{"ids": (i, j), "score": s}`` with ``i < j``. A threshold
    bounds the model work that follows; it is a workload choice, not a claim
    that lower-scored pairs are unrelated.
    """
    if not vectors:
        return []
    dense = not isinstance(vectors[0], dict)
    scores = _dense_scores(vectors) if dense else _sparse_scores(vectors)
    pairs = {}
    for index, row in enumerate(scores):
        candidates = (
            [(j, s) for j, s in enumerate(row) if j != index and s >= threshold]
            if dense
            else [(j, s) for j, s in row.items() if s >= threshold]
        )
        candidates.sort(key=lambda item: (-item[1], item[0]))
        for other, score in candidates[:k]:
            key = (min(index, other), max(index, other))
            if key not in pairs or pairs[key] < score:
                pairs[key] = score
    return [
        {"ids": key, "score": round(score, 6)} for key, score in sorted(pairs.items())
    ]


def suppress_duplicates(vectors, threshold: float) -> tuple[list[int], dict]:
    """Keep the first of each near-duplicate run in the given order.

    Returns ``(kept_indexes, suppressed)`` where ``suppressed`` maps a dropped
    index to ``{"duplicate_of": kept_index, "score": s}``. An item is dropped
    only when its similarity to an already kept item reaches ``threshold``, so
    a→b and b→c cannot drop c through b when a and c are distinct.
    """
    if not vectors:
        return [], {}
    dense = not isinstance(vectors[0], dict)
    scores = _dense_scores(vectors) if dense else _sparse_scores(vectors)
    kept, suppressed = [], {}
    for index in range(len(vectors)):
        row = scores[index]
        best, best_score = None, 0.0
        for earlier in kept:
            score = row[earlier] if dense else row.get(earlier, 0.0)
            if score > best_score:
                best, best_score = earlier, score
        if best is not None and best_score >= threshold:
            suppressed[index] = {"duplicate_of": best, "score": round(best_score, 6)}
        else:
            kept.append(index)
    return kept, suppressed


def query_scores(query: str, vectors, method: str, texts=None, provider=None):
    """Score a text query against stored vectors with the same method."""
    if method == "embedding":
        query_vector = vectors_for(provider, [query])[1][0]
        return [cosine(query_vector, vector) for vector in vectors]
    # Rebuild the IDF over the stored texts so the query shares its weighting.
    combined = term_vectors(list(texts) + [query])
    query_vector = combined[-1]
    return [cosine(query_vector, vector) for vector in combined[:-1]]
