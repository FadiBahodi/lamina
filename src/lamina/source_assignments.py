"""Use original passages directly, with no intermediate extraction call."""

from .store import canonical


def source_route(task, units, options):
    """Validate an outer agent's assignments using the same ownership checks.

    Source IDs in this temporary index are references, not model-written ideas.
    No meaning is inferred by code. Every selected unit has an owner or an
    explicit omission, and context may be shared without acquiring ownership.
    """
    from .production_contract import ProductionError, _route_check, _str

    refs = [
        {
            "id": u["id"],
            "title": u["heading"],
            "unit_ids": [u["id"]],
            "kind": "source_reference",
            "evidence": [],
        }
        for u in units
    ]
    assignment = options["assignments"]
    if options["workflow"] == "direct":
        assignment = {
            "title": task["goal"][:100],
            "summary": task["goal"][:3000],
            "sections": [
                {
                    "id": "document",
                    "title": "Document",
                    "purpose": task["goal"][:3000],
                    "unit_ids": [u["id"] for u in units],
                    "context_section_ids": [],
                    "representation": {
                        "kind": "document",
                        "rationale": "Write directly from selected sources.",
                        "requirements": [],
                    },
                }
            ],
            "omitted": [],
            "shared_context": [],
        }
    if not isinstance(assignment, dict):
        raise ProductionError("assigned workflow requires an assignments object")
    if not isinstance(assignment.get("sections"), list) or not isinstance(
        assignment.get("omitted", []), list
    ):
        raise ProductionError("assignments sections and omitted must be lists")
    raw = {**assignment, "sections": [], "omitted": []}
    context = {}
    for row in assignment.get("sections", []):
        if not isinstance(row, dict):
            raise ProductionError("each assignment must be an object")
        copied = dict(row)
        copied["idea_ids"] = copied.pop("unit_ids", None)
        extra = copied.pop("context_unit_ids", [])
        if (
            not isinstance(extra, list)
            or any(not isinstance(uid, str) for uid in extra)
            or len(extra) != len(set(extra))
            or set(extra) - {u["id"] for u in units}
        ):
            raise ProductionError(
                "context_unit_ids must name unique selected source units"
            )
        copied["id"] = _str(copied.get("id"), "assignment id", 120)
        context[copied["id"]] = extra
        raw["sections"].append(copied)
    for row in assignment.get("omitted", []):
        if not isinstance(row, dict):
            raise ProductionError("omitted assignments must be objects")
        raw["omitted"].append(
            {"idea_id": row.get("unit_id"), "reason": row.get("reason")}
        )
    route = _route_check(raw, {u["id"] for u in units}, {u["id"]: u for u in units})
    for section in route["sections"]:
        section["unit_ids"] = section["idea_ids"]
        section["context_unit_ids"] = context[section["id"]]
    return refs, route


def choose_workflow(options, units, task, sources, exemplars):
    """Auto chooses direct only for a small complete input; never truncate."""
    if options["workflow"] != "auto":
        return options
    size = len(
        canonical(
            {
                "units": units,
                "brief": task,
                "sources": sources,
                "form_exemplars": exemplars,
            }
        ).encode()
    )
    # Reserve space for the request contract and, in review, the finished draft.
    # This is a transport threshold, not a prediction of semantic difficulty.
    direct = not options["retrieval_targets"] and size <= min(
        24_000, options["max_input_bytes"] // 3
    )
    return {**options, "workflow": "direct" if direct else "planned"}
