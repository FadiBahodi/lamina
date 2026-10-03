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

from .call_runtime import make_envelope
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
    "specific followup_queries; the engine may reopen original source units, including "
    "passages that no reader extracted. These passages are supporting context, not "
    "new owned ideas. Search is bounded; no hit does not establish absence. "
    "For supersession explain its direction explicitly in statement."
)
SHAPE = {
    "kind": "|".join(sorted(KINDS)),
    "statement": "source-grounded relationship",
    "evidence": [{"unit_id": "visible unit ID", "quote": "exact source substring"}],
    "followup_queries": ["missing evidence search query, or empty"],
}

MAX_COMPARISONS = 3
MAX_QUERIES = 3
SOURCE_HITS_PER_QUERY = 1


class OriginalSourceIndex:
    """Search the full permitted originals independently of extracted ideas.

    The caller supplies the project's selected units, not the workspace library.
    Local text retrieval makes no model calls and never promotes a retrieved
    passage to an owned idea. The snapshot covers even units that return no hit:
    negative search observations depend on that whole permitted collection.
    """

    def __init__(self, units, source_policy=None):
        policy = source_policy or {}
        self.units = {
            unit["id"]: unit
            for unit in units
            if unit.get("role") == "teaching"
            and (source_policy is None or unit["source_id"] in policy)
            and policy.get(unit["source_id"], "authority")
            in {"authority", "supplement", "historical"}
        }
        self.order = sorted(self.units)
        self.texts = [
            " ".join(
                str(self.units[uid].get(key, ""))
                for key in ("heading", "locator", "text")
            )
            for uid in self.order
        ]
        self.method, self.vectors = vectors_for(None, self.texts)
        self.permissions = {
            unit["source_id"]: policy.get(unit["source_id"], "authority")
            for unit in self.units.values()
        }
        self.scope = {
            "revision": "original-source-search-1",
            "digest": digest(
                {
                    "units": [self.units[uid] for uid in self.order],
                    "permissions": self.permissions,
                }
            ),
            "source_count": len(self.permissions),
            "unit_count": len(self.units),
            "method": self.method,
            "hits_per_query": SOURCE_HITS_PER_QUERY,
            "recall": "unmeasured",
        }

    def search(self, query, exclude=()):
        excluded = set(exclude)
        # Stable addresses and exact headings are useful even when lexical
        # tokenization drops short IDs or a provider has no embedding adapter.
        exact = [
            uid
            for uid in self.order
            if uid not in excluded
            and (
                query.strip() == uid
                or query.strip().casefold()
                == self.units[uid].get("heading", "").casefold()
            )
        ]
        scores = query_scores(query, self.vectors, self.method, texts=self.texts)
        ranked = sorted(
            (
                (score, uid)
                for uid, score in zip(self.order, scores)
                if uid not in excluded and score > 0
            ),
            key=lambda row: (-row[0], row[1]),
        )
        ranked = [(1.0, uid) for uid in exact] + [
            row for row in ranked if row[1] not in exact
        ]
        return [
            {
                "unit_id": uid,
                "source_id": self.units[uid]["source_id"],
                "locator": self.units[uid].get("locator", ""),
                "score": round(score, 6),
            }
            for score, uid in ranked[:SOURCE_HITS_PER_QUERY]
        ]

    def passage(self, uid):
        unit = self.units[uid]
        return {
            **{key: unit[key] for key in ("id", "source_id", "heading", "text")},
            **{
                key: unit[key]
                for key in ("locator", "ordinal", "structural_group")
                if key in unit
            },
            "role": unit["role"],
            "policy": self.permissions[unit["source_id"]],
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
                [
                    idea["title"],
                    idea["explanation"],
                    *[e["quote"] for e in idea["evidence"]],
                ]
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
                    self.lanes[
                        ("structure", unit["source_id"], unit["structural_group"])
                    ].add(iid)
            for e in idea["evidence"]:
                self.lanes[("support", e["unit_id"])].add(iid)
        # A lane shared by very many ideas is a page everyone cites, not a
        # relationship signal; its pairs are left to similarity.
        self.skipped_common_signals = sum(
            1 for members in self.lanes.values() if len(members) > 32
        )

    def nominate(self, limit, threshold=None):
        threshold = (
            DEFAULT_THRESHOLDS["nominate"][self.method]
            if threshold is None
            else threshold
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
    originals = OriginalSourceIndex(units, options.get("source_policy"))
    for idea in ideas:
        referenced = set(idea["unit_ids"]) | {e["unit_id"] for e in idea["evidence"]}
        if not referenced <= originals.units.keys():
            raise ProductionError(
                "comparison ideas must cite selected factual teaching units"
            )
    index = CandidateIndex(ideas, list(originals.units.values()), provider)
    candidates = index.nominate(
        options["relation_neighbors"], options.get("relation_threshold")
    )
    hook = getattr(provider, "nominate_relations", None)
    supplied = (
        hook(ideas, list(originals.units.values()), options["relation_neighbors"])
        if callable(hook)
        else []
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
        reopened = set()
        read_units = set()
        recovery = None
        unresolved_reason = None
        for expansion in range(MAX_COMPARISONS):
            selected = [index.ideas[i] for i in members]
            visible = {
                e["unit_id"]: index.units[e["unit_id"]]
                for idea in selected
                for e in idea["evidence"]
            }
            visible.update({uid: originals.units[uid] for uid in sorted(reopened)})
            data = {
                "brief": task,
                "ideas": selected,
                "passages": [originals.passage(uid) for uid in sorted(visible)],
                "source_search_scope": originals.scope,
                **({"recovery": recovery} if recovery else {}),
            }
            # A new original unit is a complete source structure. Never trim its
            # tail to fit: that can be the very qualifier this recovery needs.
            workload_items = len(selected) + len(
                reopened - {e["unit_id"] for idea in selected for e in idea["evidence"]}
            )
            if expansion and not budget.fits(
                make_envelope(
                    stage, INSTRUCTION, SHAPE, data, workload_items=workload_items
                )
            ):
                result = {**result, "kind": "unresolved"}
                unresolved_reason = "followup_request_budget"
                attempts[-1]["read_status"] = "budget_exceeded"
                break

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
                if not isinstance(queries, list) or len(queries) > MAX_QUERIES:
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
                workload_items=workload_items,
            )
            read_units.update(reopened)
            added = sorted(
                {
                    iid
                    for q in result["followup_queries"]
                    for iid in index.search(q, members)
                }
            )
            source_queries = [
                {
                    "query": q,
                    "hits": originals.search(q, visible),
                    "already_visible_hits": [
                        hit for hit in originals.search(q) if hit["unit_id"] in visible
                    ],
                }
                for q in result["followup_queries"]
            ]
            found_units = sorted(
                {hit["unit_id"] for row in source_queries for hit in row["hits"]}
            )
            attempts.append(
                {
                    "member_idea_ids": list(members),
                    "queries": result["followup_queries"],
                    "found": added,
                    "original_source_queries": source_queries,
                    "found_unit_ids": found_units,
                    "source_scope_digest": originals.scope["digest"],
                    "read_status": "not_requested",
                }
            )
            if expansion:
                attempts[-2]["read_status"] = "read"
            if not result["followup_queries"]:
                break
            visible_hits = sorted(
                {
                    hit["unit_id"]
                    for row in source_queries
                    for hit in row["already_visible_hits"]
                }
            )
            if (
                not added and not found_units and not visible_hits
            ) or expansion == MAX_COMPARISONS - 1:
                result = {**result, "kind": "unresolved"}
                unresolved_reason = (
                    "followup_limit"
                    if expansion == MAX_COMPARISONS - 1
                    else "no_new_evidence"
                )
                break
            members.extend(added)
            reopened.update(found_units)
            recovery = {
                "statement": result["statement"],
                "questions": result["followup_queries"],
                "new_idea_ids": added,
                "new_unit_ids": found_units,
                "already_visible_unit_ids": visible_hits,
            }
        return {
            **result,
            "id": "relation_" + digest(sorted(members))[:16],
            "member_idea_ids": members,
            "nomination_signals": candidate["signals"],
            "searches": attempts,
            "source_search_scope": originals.scope,
            "reopened_unit_ids": sorted(read_units),
            "pending_unit_ids": sorted(
                {uid for attempt in attempts for uid in attempt["found_unit_ids"]}
                - read_units
            ),
            **({"unresolved_reason": unresolved_reason} if unresolved_reason else {}),
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
        "source_search_scope": originals.scope,
        "unresolved_groups": sum(r["kind"] == "unresolved" for r in unique.values()),
        "scope": "Bounded retrieval plus source comparison; not exhaustive reconciliation.",
    }
