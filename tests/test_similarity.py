"""Local similarity mechanics: nomination and duplicate suppression without model calls."""

from lamina.similarity import (
    DEFAULT_THRESHOLDS,
    nearest_pairs,
    suppress_duplicates,
    term_vectors,
    vectors_for,
)


def test_term_vectors_are_unit_length_and_drop_ubiquitous_terms():
    texts = ["the pump stops below ten kpa"] * 40 + ["an unrelated valve note"]
    vectors = term_vectors(texts)
    assert all(abs(sum(v * v for v in vec.values()) - 1) < 1e-9 for vec in vectors if vec)
    # "pump", "stops", "below", "ten", "kpa" appear in 40 of 41 texts: dropped.
    assert vectors[0] == {}
    assert set(vectors[-1]) == {"unrelated", "valve", "note"}


def test_nearest_pairs_respects_threshold_and_k():
    vectors = [
        {"a": 1.0},
        {"a": 0.8, "b": 0.6},
        {"b": 1.0},
        {"c": 1.0},
    ]
    pairs = nearest_pairs(vectors, k=5, threshold=0.5)
    assert [(p["ids"], p["score"]) for p in pairs] == [((0, 1), 0.8), ((1, 2), 0.6)]
    assert nearest_pairs(vectors, k=1, threshold=0.5)[0]["ids"] == (0, 1)
    assert nearest_pairs([], 3, 0.1) == []


def test_duplicate_suppression_never_merges_through_a_chain():
    # a~b and b~c at the threshold, but a and c are distinct. Connected
    # components would collapse all three; the kept-set rule keeps a and c.
    vectors = [
        {"x": 1.0},
        {"x": 0.9, "y": 0.436},
        {"y": 1.0},
    ]
    kept, suppressed = suppress_duplicates(vectors, threshold=0.85)
    assert kept == [0, 2]
    assert suppressed[1]["duplicate_of"] == 0
    assert 2 not in suppressed


def test_provider_embeddings_are_normalised_and_validated():
    class Embedding:
        def embed(self, texts):
            return [[3.0, 4.0] for _ in texts]

    method, vectors = vectors_for(Embedding(), ["a", "b"])
    assert method == "embedding"
    assert vectors == [[0.6, 0.8], [0.6, 0.8]]
    kept, suppressed = suppress_duplicates(vectors, DEFAULT_THRESHOLDS["duplicate"]["embedding"])
    assert kept == [0] and suppressed[1]["duplicate_of"] == 0

    class Ragged:
        def embed(self, texts):
            return [[1.0], [1.0, 2.0]]

    try:
        vectors_for(Ragged(), ["a", "b"])
    except ValueError as exc:
        assert "equal-length" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("ragged embeddings must be rejected")
    assert vectors_for(object(), ["only tfidf"])[0] == "tfidf"
