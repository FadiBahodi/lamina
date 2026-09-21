"""Transparent rank fusion: body BM25, heading matches, optional caller vectors."""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict


def tokenize(text: str) -> list[str]:
    return re.findall(r"\w+", text.casefold())


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or len(a) != len(b):
        raise ValueError("Query and source vectors must have the same non-zero dimension")
    if not all(isinstance(x, (float, int)) and math.isfinite(x) for x in [*a, *b]):
        raise ValueError("Vectors must contain finite numbers")
    denom = math.sqrt(sum(x*x for x in a) * sum(x*x for x in b))
    return sum(x*y for x, y in zip(a, b)) / denom if denom else 0.0


def search(units: list[dict], query: str, limit: int = 8, query_vector: list[float] | None = None,
           vectors: dict[str, list[float]] | None = None) -> list[dict]:
    if limit < 1:
        raise ValueError("limit must be positive")
    # Search is a teaching-source interface. Assessment units never silently
    # become generation context even if a caller hands us an unfiltered list.
    units = [u for u in units if u.get("role") == "teaching"]
    if not units:
        return []
    terms = sorted(set(tokenize(query)))
    bodies = [Counter(tokenize(u["text"])) for u in units]
    lengths = [sum(b.values()) for b in bodies]
    average = sum(lengths) / len(lengths) or 1
    frequencies = Counter(term for b in bodies for term in b)
    body_scores = {}
    heading_scores = {}
    for u, bag, length in zip(units, bodies, lengths):
        score = 0.0
        for term in terms:
            freq = bag[term]
            if freq:
                idf = math.log(1 + (len(units) - frequencies[term] + .5) / (frequencies[term] + .5))
                score += idf * freq * 2.2 / (freq + 1.2 * (0.25 + 0.75 * length / average))
        body_scores[u["id"]] = score
        heading_scores[u["id"]] = len(set(terms).intersection(tokenize(u["heading"])))
    lanes = {"body": body_scores, "heading": heading_scores}
    if query_vector is not None:
        if vectors is None:
            raise ValueError("Supply unit vectors together with a query vector")
        lanes["vector"] = {u["id"]: _cosine(query_vector, vectors[u["id"]]) for u in units if u["id"] in vectors}
    fused = defaultdict(float)
    evidence = defaultdict(dict)
    for lane, scores in lanes.items():
        ranked = sorted(((key, value) for key, value in scores.items() if value > 0), key=lambda x: (-x[1], x[0]))
        for rank, (key, score) in enumerate(ranked, 1):
            fused[key] += 1 / (60 + rank)
            evidence[key][lane] = {"rank": rank, "raw_score": round(score, 6)}
    lookup = {u["id"]: u for u in units}
    ordered = sorted(fused, key=lambda key: (-fused[key], key))[:limit]
    return [{**lookup[key], "score": round(fused[key], 8), "lanes": evidence[key]} for key in ordered]
