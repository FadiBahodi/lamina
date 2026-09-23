"""Read complete source structures, retaining successful work across failures."""

from __future__ import annotations

from dataclasses import replace
from .context_budget import RequestBudget, pack_units, OversizedUnit
from .execution import bounded_collect
from .production_contract import (
    REVISION,
    _BASE,
    _SHAPES,
    _read_check,
    ProductionError,
    ProductionValidationError,
    validated,
)
from .store import digest

TASK_INSTRUCTION = (
    "Read the owned source structures completely. Select distinct useful ideas for the brief. "
    "Preserve qualifications, numbers, exceptions, disagreements and uncertainty. Each idea "
    "needs exact evidence from owned core units. Neighboring material only explains context. "
    "Respect source policies: historical claims remain historical; supplements do not silently override authority. "
)
COMPILE_INSTRUCTION = (
    "Compile a reusable inventory of the source's substantive claims, relationships and procedures. "
    "Preserve conditions, exceptions, quantities, uncertainty, conflicts, table associations and sequences. "
    "Keep claims from the source distinct from your interpretation. Each idea needs exact quotes from "
    "owned core units. Do not select for a particular audience or future output format. "
    "This inventory remains an interpretation; the original source will accompany later writing. "
)
CONTEXT_INSTRUCTION = (
    "If a boundary makes the core uninterpretable, you may instead return "
    "{context_request:{direction:'before'|'after',reason:'specific missing dependency'}}. "
    "Request this only when additional adjacent source text is necessary, and never fabricate it."
)


from .call_runtime import make_envelope as envelope


def request_budget(provider, stage, options):
    cap = options.get("max_input_bytes") or options["max_request_bytes"]
    cap = min(cap, options["max_request_bytes"])
    budget = getattr(provider, "budget_for", lambda _: None)(stage)
    if budget is None:
        return RequestBudget(cap)
    return replace(budget, max_request_bytes=min(cap, budget.max_request_bytes))


def reader_input(window, source, task, options):
    core, before, after = window["core"], window["before"], window["after"]
    visible = before + core + after
    aliases = (
        {u["id"]: f"u{n}" for n, u in enumerate(visible)}
        if all("content_id" in u for u in visible)
        else None
    )

    def local(rows):
        if aliases is None:
            return rows
        return [
            {
                "id": aliases[u["id"]],
                "heading": u["heading"],
                "text": u["text"],
                "role": u["role"],
                **{
                    k: u[k]
                    for k in ("heading_path", "kind", "reference_context")
                    if k in u
                },
            }
            for u in rows
        ]

    source = (
        {k: v for k, v in source.items() if k not in {"id", "sha256"}}
        if aliases
        else source
    )
    data = {
        "source": source,
        "window_id": "local" if aliases else window["id"],
        "core": local(core),
        "before": local(before),
        "after": local(after),
        "reading": options["reading"],
        "ownership": "Only core units may originate ideas. Adjacent units provide context.",
    }
    if options["reading"] == "task":
        data.update(brief=task, format=options["format"])
    else:
        # Authority is a later project decision. Reusable reading preserves what
        # a source says without treating that source as an instruction or truth.
        data["source"] = {k: v for k, v in source.items() if k != "policy"}
    return data, aliases


def read_sources(
    workspace, provider, task, options, sources, units, tracker, legacy_windows=None
):
    stage = "production_read"
    instruction = (
        COMPILE_INSTRUCTION if options["reading"] == "reusable" else TASK_INSTRUCTION
    ) + CONTEXT_INSTRUCTION
    budget = request_budget(provider, stage, options)
    source_map = {s["id"]: s for s in sources}

    def window(core, before=(), after=()):
        return {
            "id": "window_" + digest([u["id"] for u in core])[:12],
            "source_id": core[0]["source_id"],
            "core": core,
            "before": list(before),
            "after": list(after),
        }

    def request(core):
        if not core:
            data = {"core": [], "before": [], "after": []}
        else:
            data, _ = reader_input(
                window(core), source_map[core[0]["source_id"]], task, options
            )
        return envelope(stage, instruction, _SHAPES[stage], data)

    if legacy_windows is not None:
        windows = legacy_windows
    else:
        windows = [window(batch.units) for batch in pack_units(units, request, budget)]
    by_source, positions = {}, {}
    for unit in units:
        local = by_source.setdefault(unit["source_id"], [])
        positions[unit["id"]] = len(local)
        local.append(unit)

    def read(original):
        current = {
            **original,
            "before": list(original["before"]),
            "after": list(original["after"]),
        }
        extensions = []
        while True:
            data, aliases = reader_input(
                current, source_map[current["source_id"]], task, options
            )

            def check(raw):
                if isinstance(raw, dict) and "context_request" in raw:
                    row = raw["context_request"]
                    if (
                        not isinstance(row, dict)
                        or row.get("direction") not in ("before", "after")
                        or not isinstance(row.get("reason"), str)
                        or not row["reason"].strip()
                    ):
                        raise ProductionValidationError(
                            "context_request needs before/after and a specific reason"
                        )
                    return {"context_request": row}
                return validated(_read_check, raw, data["core"], data["window_id"])

            try:
                reply = tracker.call(
                    workspace,
                    provider,
                    stage,
                    current["id"],
                    instruction,
                    _SHAPES[stage],
                    data,
                    check,
                    budget.max_request_bytes,
                )
                if "ideas" in reply:
                    result = reply["ideas"]
                    break
                request_more = reply["context_request"]
                local = by_source[current["source_id"]]
                visible = current["before"] + current["core"] + current["after"]
                index = (
                    positions[visible[0]["id"]] - 1
                    if request_more["direction"] == "before"
                    else positions[visible[-1]["id"]] + 1
                )
                if not 0 <= index < len(local):
                    raise ProductionError(
                        f"Reader needs unavailable {request_more['direction']} context: {request_more['reason']}"
                    )
                extra = [local[index]]
                group = local[index].get("structural_group")
                if group:
                    direction = -1 if request_more["direction"] == "before" else 1
                    j = index + direction
                    while (
                        0 <= j < len(local)
                        and local[j].get("structural_group") == group
                    ):
                        extra.append(local[j])
                        j += direction
                    extra.sort(key=lambda u: positions[u["id"]])
                if request_more["direction"] == "before":
                    current["before"] = extra + current["before"]
                else:
                    current["after"] += extra
                extensions.append(
                    {
                        "direction": request_more["direction"],
                        "reason": request_more["reason"],
                        "unit_ids": [u["id"] for u in extra],
                    }
                )
            except Exception as exc:
                # A truncated output is evidence that this read was too large.
                # Split only between complete structures; never retry the same
                # oversized output request indefinitely.
                if getattr(exc, "code", None) != "output_truncated":
                    if isinstance(getattr(exc, "partial_results", None), dict):
                        from .context_binding import restore_references

                        reverse = {alias: uid for uid, alias in (aliases or {}).items()}
                        partial = restore_references(exc.partial_results, reverse)
                        partial["core_unit_ids"] = [
                            reverse.get(uid, uid)
                            for uid in partial.get("core_unit_ids", [])
                        ]
                        partial["source_id"] = current["source_id"]
                        partial["window_id"] = current["id"]
                        if aliases:
                            for idea in partial.get("ideas", []):
                                idea["id"] = (
                                    f"{current['id']}:{idea['id'].split(':', 1)[1]}"
                                )
                        exc.partial_results = partial
                    raise
                bundles = []
                for unit in current["core"]:
                    if (
                        bundles
                        and unit.get("structural_group")
                        and unit.get("structural_group")
                        == bundles[-1][0].get("structural_group")
                    ):
                        bundles[-1].append(unit)
                    else:
                        bundles.append([unit])
                if len(bundles) < 2:
                    raise ProductionError(
                        "A single source structure exceeds the reader's output allowance; increase that allowance or explicitly decompose it"
                    ) from exc
                middle = len(bundles) // 2
                # Outer context stays on its adjacent child. Copying the outer
                # "after" onto the left child would skip its right sibling when
                # that child asks for the next contiguous source structure.
                children = [
                    window(
                        [u for group in bundles[:middle] for u in group],
                        before=current["before"],
                    ),
                    window(
                        [u for group in bundles[middle:] for u in group],
                        after=current["after"],
                    ),
                ]
                parts = [read(child) for child in children]
                return (
                    [w for part in parts for w in part[0]],
                    [i for part in parts for i in part[1]],
                )
        if aliases:
            reverse = {alias: uid for uid, alias in aliases.items()}
            result = [
                {
                    **idea,
                    "id": f"{current['id']}:idea_{n}",
                    "unit_ids": [reverse[uid] for uid in idea["unit_ids"]],
                    "evidence": [
                        {**e, "unit_id": reverse[e["unit_id"]]}
                        for e in idea["evidence"]
                    ],
                }
                for n, idea in enumerate(result, 1)
            ]
        # Store references once. The plan owns one complete unit dictionary.
        saved = {
            **current,
            **{k: [u["id"] for u in current[k]] for k in ("core", "before", "after")},
            "context_requests": extensions,
            "budget": budget.measure(
                envelope(stage, instruction, _SHAPES[stage], data)
            ).__dict__,
        }
        return [saved], result

    results = bounded_collect(
        read, windows, min(options["workers"], options["reader_workers"])
    )
    successful = [row.value for row in results if row.ok]
    failures = [row for row in results if not row.ok]
    if failures:
        error = ProductionError(
            f"{len(failures)} reading batch(es) unresolved; {len(successful)} completed batches are cached: {failures[0].error}"
        )
        error.metrics = tracker.metrics()
        error.partial_results = {
            "completed_windows": [w for part in successful for w in part[0]],
            "ideas": [idea for part in successful for idea in part[1]],
            "failed_windows": [
                {
                    "id": windows[row.index]["id"],
                    "error": str(row.error),
                    "partial": getattr(row.error, "partial_results", None),
                }
                for row in failures
            ],
        }
        raise error from failures[0].error
    return [w for part in successful for w in part[0]], [
        idea for part in successful for idea in part[1]
    ]
