"""Canonical, source-backed retrieval targets for opt-in production.

The model decides whether source ideas describe one task, related variants, or
different presentations. Code checks identity, ownership and exact evidence;
it cannot verify clinical or educational equivalence by string similarity.
"""

from __future__ import annotations

import re

TARGET_REVISION = "lamina-retrieval-targets-1"
_ID = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,99}\Z")

TARGET_SHAPE = {
    "targets": [
        {
            "id": "unique target id",
            "title": "str",
            "prompt": "self-contained retrieval prompt",
            "context": "presentation or use context",
            "member_idea_ids": ["idea id"],
            "membership_relation": "unique|equivalent|variant",
            "answer_groups": [
                {
                    "label": "str",
                    "items": [
                        {
                            "text": "exact substring of cited source quote",
                            "supports_idea_ids": ["member idea id"],
                            "evidence": [
                                {"unit_id": "str", "quote": "exact source substring"}
                            ],
                        }
                    ],
                }
            ],
        }
    ],
    "relations": [
        {
            "from_target_id": "str",
            "to_target_id": "str",
            "kind": "variant|different_context",
            "reason": "str",
        }
    ],
}


class RetrievalTargetError(ValueError):
    pass


def _text(value: object, label: str, limit: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise RetrievalTargetError(
            f"{label} must be nonempty text of at most {limit} characters"
        )
    return value.strip()


def validate_retrieval_targets(raw: dict, ideas: list[dict], units: list[dict]) -> dict:
    """Validate exact idea partition and answer support without choosing meaning."""
    if not isinstance(raw, dict) or set(raw) != {"targets", "relations"}:
        raise RetrievalTargetError("retrieval stage needs targets and relations")
    rows, links = raw["targets"], raw["relations"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= 512:
        raise RetrievalTargetError("targets must be a nonempty bounded list")
    if not isinstance(links, list) or len(links) > 1024:
        raise RetrievalTargetError("relations must be a bounded list")
    idea_by_id = {idea["id"]: idea for idea in ideas}
    unit_by_id = {unit["id"]: unit for unit in units}
    claimed: set[str] = set()
    target_ids: set[str] = set()
    targets = []
    for raw_target in rows:
        if not isinstance(raw_target, dict) or set(raw_target) != {
            "id",
            "title",
            "prompt",
            "context",
            "member_idea_ids",
            "membership_relation",
            "answer_groups",
        }:
            raise RetrievalTargetError("target has invalid fields")
        tid = raw_target["id"]
        if not isinstance(tid, str) or not _ID.fullmatch(tid) or tid in target_ids:
            raise RetrievalTargetError("target IDs must be unique short identifiers")
        target_ids.add(tid)
        members = raw_target["member_idea_ids"]
        if (
            not isinstance(members, list)
            or not members
            or len(members) > 100
            or any(not isinstance(i, str) for i in members)
            or len(members) != len(set(members))
            or any(i not in idea_by_id or i in claimed for i in members)
        ):
            raise RetrievalTargetError(
                "each idea must have exactly one known target owner"
            )
        relation = raw_target["membership_relation"]
        if relation not in {"unique", "equivalent", "variant"}:
            raise RetrievalTargetError(
                "membership_relation must be unique, equivalent, or variant"
            )
        if (len(members) == 1) != (relation == "unique"):
            raise RetrievalTargetError(
                "unique targets need one idea; equivalent/variant targets need multiple"
            )
        claimed.update(members)
        groups = raw_target["answer_groups"]
        if not isinstance(groups, list) or not 1 <= len(groups) <= 50:
            raise RetrievalTargetError("target needs bounded answer groups")
        checked_groups = []
        supported: set[str] = set()
        for group in groups:
            if not isinstance(group, dict) or set(group) != {"label", "items"}:
                raise RetrievalTargetError("answer group needs label and items")
            items = group["items"]
            if not isinstance(items, list) or not 1 <= len(items) <= 100:
                raise RetrievalTargetError(
                    "answer group items must be nonempty and bounded"
                )
            checked_items = []
            for item in items:
                if not isinstance(item, dict) or set(item) != {
                    "text",
                    "supports_idea_ids",
                    "evidence",
                }:
                    raise RetrievalTargetError(
                        "answer item needs text, idea support and evidence"
                    )
                text = _text(item["text"], "answer item", 4000)
                supports = item["supports_idea_ids"]
                if (
                    not isinstance(supports, list)
                    or not supports
                    or any(not isinstance(i, str) for i in supports)
                    or len(supports) != len(set(supports))
                    or any(i not in members for i in supports)
                ):
                    raise RetrievalTargetError(
                        "answer item must name member ideas it supports"
                    )
                evidence = item["evidence"]
                if not isinstance(evidence, list) or not 1 <= len(evidence) <= 30:
                    raise RetrievalTargetError(
                        "answer item needs bounded exact evidence"
                    )
                checked_evidence = []
                seen_evidence = set()
                for citation in evidence:
                    if not isinstance(citation, dict) or set(citation) != {
                        "unit_id",
                        "quote",
                    }:
                        raise RetrievalTargetError(
                            "answer citation needs unit_id and quote"
                        )
                    uid = citation["unit_id"]
                    quote = _text(citation["quote"], "answer quote", 4000)
                    if (
                        not isinstance(uid, str)
                        or uid not in unit_by_id
                        or quote not in unit_by_id[uid]["text"]
                    ):
                        raise RetrievalTargetError(
                            "answer quote is not exact source text"
                        )
                    if uid not in {
                        u for mid in members for u in idea_by_id[mid]["unit_ids"]
                    }:
                        raise RetrievalTargetError(
                            "answer quote is outside target member ideas"
                        )
                    if (uid, quote) not in seen_evidence:
                        checked_evidence.append({"unit_id": uid, "quote": quote})
                        seen_evidence.add((uid, quote))
                if not any(text in e["quote"] for e in checked_evidence):
                    raise RetrievalTargetError(
                        "answer item text must be an exact substring of its cited quote"
                    )
                for mid in supports:
                    if not any(
                        e["unit_id"] in idea_by_id[mid]["unit_ids"]
                        for e in checked_evidence
                    ):
                        raise RetrievalTargetError(
                            "each claimed idea needs its own cited unit"
                        )
                supported.update(supports)
                checked_items.append(
                    {
                        "text": text,
                        "supports_idea_ids": supports,
                        "evidence": checked_evidence,
                    }
                )
            checked_groups.append(
                {
                    "label": _text(group["label"], "answer group label", 300),
                    "items": checked_items,
                }
            )
        if supported != set(members):
            raise RetrievalTargetError(
                "every member idea needs a preserved answer item"
            )
        targets.append(
            {
                "id": tid,
                "title": _text(raw_target["title"], "target title", 300),
                "prompt": _text(raw_target["prompt"], "target prompt", 3000),
                "context": _text(raw_target["context"], "target context", 3000),
                "member_idea_ids": members,
                "membership_relation": relation,
                "answer_groups": checked_groups,
            }
        )
    if claimed != set(idea_by_id):
        raise RetrievalTargetError(
            "target ownership must partition every extracted idea"
        )
    checked_links = []
    seen_pairs = set()
    for link in links:
        if not isinstance(link, dict) or set(link) != {
            "from_target_id",
            "to_target_id",
            "kind",
            "reason",
        }:
            raise RetrievalTargetError("target relation has invalid fields")
        left, right = link["from_target_id"], link["to_target_id"]
        if (
            not isinstance(left, str)
            or not isinstance(right, str)
            or left not in target_ids
            or right not in target_ids
            or left == right
        ):
            raise RetrievalTargetError(
                "target relation must link two distinct known targets"
            )
        pair = tuple(sorted((left, right)))
        if pair in seen_pairs:
            raise RetrievalTargetError("one relation per target pair")
        seen_pairs.add(pair)
        if link["kind"] not in {"variant", "different_context"}:
            raise RetrievalTargetError(
                "equivalent targets must be merged; cross-target links are variant or different_context"
            )
        checked_links.append(
            {
                "from_target_id": left,
                "to_target_id": right,
                "kind": link["kind"],
                "reason": _text(link["reason"], "target relation reason", 1000),
            }
        )
    return {"revision": TARGET_REVISION, "targets": targets, "relations": checked_links}


def render_retrieval_targets(catalog: dict) -> str:
    """Mechanically preserve prompts and exact answer items in an artifact."""
    lines = ["# Retrieval targets and answer groups"]
    for target in catalog["targets"]:
        lines.extend(["", "## " + target["title"], "", target["prompt"], ""])
        for group in target["answer_groups"]:
            lines.append("### " + group["label"])
            for item in group["items"]:
                lines.append("- " + item["text"].replace("\n", " "))
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"
