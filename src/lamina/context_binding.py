"""Separate a section's content identity from exact source-revision pointers."""

from __future__ import annotations

import copy

_REF_LISTS = {
    "unit_ids",
    "context_unit_ids",
    "source_ids",
    "used_unit_ids",
    "idea_ids",
    "used_idea_ids",
    "target_ids",
    "used_target_ids",
    "supports_idea_ids",
    "member_idea_ids",
}


def _references(value, mapping):
    if isinstance(value, list):
        return [_references(row, mapping) for row in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for key, item in value.items():
        if key in {
            "unit_id",
            "source_id",
            "target_id",
            "from_target_id",
            "to_target_id",
        }:
            result[key] = mapping.get(item, item) if isinstance(item, str) else item
        elif key in _REF_LISTS and isinstance(item, list):
            result[key] = [mapping.get(x, x) if isinstance(x, str) else x for x in item]
        elif (
            key == "id"
            and isinstance(item, str)
            and (
                ("source_id" in value and "text" in value)
                or "explanation" in value
                or "member_idea_ids" in value
                or "filename" in value
                or ("prompt" in value and "context" in value)
            )
        ):
            result[key] = mapping.get(item, item)
        else:
            result[key] = _references(item, mapping)
    return result


def bind_context(data, units):
    """Canonical local references for caching; source text and policy stay exact.

    Only provenance locations and whole-file revision hashes are omitted from
    model input. The caller restores current unit references after validation.
    Every semantic field the model receives remains in the cache key.
    """
    aliases = {uid: f"unit:{n}" for n, uid in enumerate(units)}
    source_ids = list(dict.fromkeys(u["source_id"] for u in units.values()))
    aliases.update({sid: f"source:{n}" for n, sid in enumerate(source_ids)})
    ideas = data.get("assigned_ideas", []) + data.get("earlier_planned_ideas", [])
    aliases.update({row["id"]: f"idea:{n}" for n, row in enumerate(ideas)})
    aliases.update(
        {
            row["id"]: f"target:{n}"
            for n, row in enumerate(
                data.get("assigned_targets", []) + data.get("related_targets", [])
            )
        }
    )
    result = copy.deepcopy(data)
    source_fields = {"id", "title", "filename", "role", "policy"}
    result["factual_sources"] = [
        {k: v for k, v in row.items() if k in source_fields}
        for row in result.get("factual_sources", [])
    ]
    semantic_fields = {
        "id",
        "source_id",
        "heading",
        "heading_path",
        "kind",
        "text",
        "role",
        "reference_context",
    }
    for key in ("assigned_units", "earlier_evidence_units", "shared_evidence_units"):
        result[key] = [
            {k: v for k, v in row.items() if k in semantic_fields}
            for row in result.get(key, [])
        ]
    result = _references(result, aliases)
    normalized_units = {
        aliases[uid]: {**u, "id": aliases[uid]} for uid, u in units.items()
    }
    return (
        result,
        normalized_units,
        {local: original for original, local in aliases.items()},
    )


def restore_references(value, reverse):
    return _references(value, reverse)
