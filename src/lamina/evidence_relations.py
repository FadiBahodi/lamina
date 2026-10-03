"""Nominate evidence relationships, then compare the actual source passages.

Retrieval proposes work, never establishes equivalence. Candidate recall and
comparison accuracy remain separately unmeasured. Caller nomination can add
entity resolution, dense retrieval, or multi-source groups without changing
ownership or replacing the comparison contract.

Nomination uses local similarity (provider embeddings when the provider offers
``embed``, otherwise TF-IDF) with a threshold, plus two structural lanes:
ideas that cite the same source unit and ideas from the same parser structure.
Only nominated pairs reach a model call, so the model work is bounded by the
threshold and ``relation_neighbors`` rather than by every lexical overlap.
"""

from collections import defaultdict

from .execution import bounded_map
from .production_contract import ProductionError, _evidence, _str, validated
from .similarity import DEFAULT_THRESHOLDS, nearest_pairs, query_scores, vectors_for
from .source_reading import request_budget
from .store import digest

KINDS = {
    "repetition",
    "complement",
    "different_conditions",
    "contradiction",
    "supersession",
    "unrelated",
    "unresolved",
}
INSTRUCTION = (
    "Compare the actual passages for the supplied ideas. Determine whether they "
    "repeat, complement, differ in conditions/populations, contradict, or explicitly "
    "supersede each other, or remain unrelated/unresolved. Similar words or answers "
    "do not establish equivalence; a later date alone does not establish supersession. "
    "Preserve time, population, definitions, quantities, units, exceptions and uncertainty. "
    "Do not merge or reassign idea ownership. Cite exact visible evidence from each "
    "participating idea. If interpretation needs another passage, request up to three "
    "specific followup_queries; the engine may reopen additional evidence. "
    "For supersession explain its direction explicitly in statement."
)
SHAPE = {
    "kind": "|".join(sorted(KINDS)),
    "statement": "source-grounded relationship",
    "evidence": [{"unit_id": "visible unit ID", "quote": "exact source substring"}],
    "followup_queries": ["missing evidence search query, or empty"],
}


class CandidateIndex:
    """Similarity vectors over each idea's title, explanation and quotes, plus
    structural lanes. Pair scores are nominations for a model comparison."""

    def __init__(self, ideas, units, provider=None):
        self.ideas = {i["id"]: i for i in ideas}
        self.units = {u["id"]: u for u in units}
        self.order = [idea["id"] for idea in ideas]
        self.texts = [
            " ".join(
                [idea["title"], idea["explanation"], *[e["quote"] for e in idea["evidence"]]]
            )
            for idea in ideas
        ]
        self.provider = provider
        self.method, self.vectors = vectors_for(provider, self.texts)
        self.lanes = defaultdict(set)
        for iid, idea in self.ideas.items():
            for uid in idea["unit_ids"]:
                unit = self.units[uid]
                if unit.get("structural_group"):
                    self.lanes[("structure", unit["source_id"], unit["structural_group"])].add(iid)
            for e in idea["evidence"]:
                self.lanes[("support", e["unit_id"])].add(iid)
        # A lane shared by very many ideas is a page everyone cites, not a
        # relationship signal; its pairs are left to similarity.
        self.skipped_common_signals = sum(
            1 for members in self.lanes.values() if len(members) > 32
        )

    def nominate(self, limit, threshold=None):
        threshold = (
            DEFAULT_THRESHOLDS["nominate"][self.method] if threshold is None else threshold
        )
        self.threshold = threshold
        pairs = {}
        for row in nearest_pairs(self.vectors, limit, threshold):
            i, j = row["ids"]
            key = tuple(sorted((self.order[i], self.order[j])))
            pairs.setdefault(key, {"signals": set(), "score": None})
            pairs[key]["signals"].add(f"similarity:{self.method}")
            pairs[key]["score"] = row["score"]
        for lane, members in self.lanes.items():
            if len(members) > 32 or len(members) < 2:
                continue
            ordered = sorted(members)
            for a in range(len(ordered)):
                for b in range(a + 1, len(ordered)):
                    key = (ordered[a], ordered[b])
                    pairs.setdefault(key, {"signals": set(), "score": None})
                    pairs[key]["signals"].add(lane[0])
        return [
            {
                "idea_ids": list(key),
                "signals": sorted(value["signals"]),
                **({"score": value["score"]} if value["score"] is not None else {}),
            }
            for key, value in sorted(pairs.items())
        ]

    def search(self, query, exclude):
        scores = query_scores(
            query, self.vectors, self.method, texts=self.texts, provider=self.provider
        )
        ranked = sorted(
            (
                (score, self.order[index])
                for index, score in enumerate(scores)
                if self.order[index] not in exclude and score > 0
            ),
            key=lambda item: (-item[0], item[1]),
        )
        return [iid for _, iid in ranked[:1]]


def compare_relations(workspace, provider, ideas, units, task, options, tracker):
    stage = "production_compare"
    budget = request_budget(provider, stage, options)
    if budget.workload is None:
        raise ProductionError("production_compare needs an explicit workload profile")
    index = CandidateIndex(ideas, units, provider)
    candidates = index.nominate(
        options["relation_neighbors"], options.get("relation_threshold")
    )
    hook = getattr(provider, "nominate_relations", None)
    supplied = (
        hook(ideas, units, options["relation_neighbors"]) if callable(hook) else []
    )
    seen = {tuple(c["idea_ids"]) for c in candidates}
    for ids in supplied:
        if (
            not isinstance(ids, list)
            or not 2 <= len(ids) <= 32
            or any(not isinstance(i, str) or i not in index.ideas for i in ids)
            or len(set(ids)) != len(ids)
        ):
            raise ProductionError(
                "relation nominations must name 2–32 unique known ideas"
            )
        group = tuple(sorted(ids))
        if group not in seen:
            candidates.append({"idea_ids": list(group), "signals": ["caller"]})
            seen.add(group)

    def compare(candidate):
        members = list(candidate["idea_ids"])
        attempts = []
        for expansion in range(3):
            selected = [index.ideas[i] for i in members]
            visible = {
                e["unit_id"]: index.units[e["unit_id"]]
                for idea in selected
                for e in idea["evidence"]
            }
            data = {
                "brief": task,
                "ideas": selected,
                "passages": [
                    {k: u[k] for k in ("id", "source_id", "heading", "text")}
                    for u in visible.values()
                ],
            }

            def check(raw):
                if not isinstance(raw, dict) or raw.get("kind") not in KINDS:
                    raise ProductionError("comparison needs a known relationship kind")
                evidence = _evidence(
                    raw.get("evidence"),
                    visible,
                    "comparison",
                    required=raw["kind"] not in {"unrelated", "unresolved"},
                )
                if raw["kind"] not in {"unrelated", "unresolved"}:
                    cited = {e["unit_id"] for e in evidence}
                    if any(
                        not cited.intersection({e["unit_id"] for e in idea["evidence"]})
                        for idea in selected
                    ):
                        raise ProductionError(
                            "comparison must cite evidence for every participating idea"
                        )
                queries = raw.get("followup_queries", [])
                if not isinstance(queries, list) or len(queries) > 3:
                    raise ProductionError(
                        "comparison permits at most three followup queries"
                    )
                return {
                    "kind": raw["kind"],
                    "statement": _str(raw.get("statement"), "relationship", 5000),
                    "evidence": evidence,
                    "followup_queries": [
                        _str(q, "followup query", 500) for q in queries
                    ],
                }

            result = tracker.call(
                workspace,
                provider,
                stage,
                "relation_" + digest(members)[:16],
                INSTRUCTION,
                SHAPE,
                data,
                lambda raw: validated(check, raw),
                budget.max_request_bytes,
                workload_items=len(selected),
            )
            added = sorted(
                {
                    iid
                    for q in result["followup_queries"]
                    for iid in index.search(q, members)
                }
            )
            attempts.append(
                {
                    "member_idea_ids": list(members),
                    "queries": result["followup_queries"],
                    "found": added,
                }
            )
            if not result["followup_queries"]:
                break
            if not added or expansion == 2:
                result = {**result, "kind": "unresolved"}
                break
            members.extend(added)
        return {
            **result,
            "id": "relation_" + digest(sorted(members))[:16],
            "member_idea_ids": members,
            "nomination_signals": candidate["signals"],
            "searches": attempts,
        }

    relations = bounded_map(
        compare, candidates, min(options["workers"], options["reader_workers"])
    )
    unique = {}
    for relation in relations:
        unique.setdefault(relation["id"], relation)
    return list(unique.values()), {
        "nominated_groups": len(candidates),
        "compared_groups": len(relations),
        "nomination_method": index.method,
        "nomination_threshold": index.threshold,
        "skipped_common_signals": index.skipped_common_signals,
        "nomination_recall": "unmeasured",
        "comparison_accuracy": "unmeasured",
        "unresolved_groups": sum(r["kind"] == "unresolved" for r in unique.values()),
        "scope": "Bounded retrieval plus source comparison; not exhaustive reconciliation.",
    }
