"""Schedule geometry of one run, computed from its own call records.

Every tracked call carries its start and end (milliseconds after the
tracker's origin), the model attempts inside it, and the calls it declared it
waited for. From those this module reconstructs the dependency graph, finds
the critical path, and compares the run's wall time with the bound that
``docs/flow-geometry.md`` states for any schedule:

    T  >=  max( W / P ,  D )

where ``W`` is total model time, ``P`` the worker limit and ``D`` the
duration of the longest dependency chain. The receipt reports the bound, the
measured ``T``, their ratio, where the run was serial, and the context
amplification (bytes sent / distinct source bytes). None of this is a model
quality claim; it says how the work was scheduled, with numbers a reader can
check against the records beside them.

Edges come from two sources. Calls that know their inputs declare them
(``after`` on the tracker: which reads fed a grouping batch, which batches
fed the outline, which outline an assignment batch waited for). Calls whose
dependency is structural follow the stage rules in :func:`implied_after`:
a section's review follows its write, a repair follows its review, a
section's first write follows the end of planning, a sampled audit follows
its window's read, and a whole-document consistency check follows every
section call. Those rules are written down here so they can be disputed.
"""

from __future__ import annotations

from collections import defaultdict
from statistics import median

PLANNING = ("production_group", "production_route", "production_assign", "production_targets")
SECTION = ("production_write", "production_review", "production_repair")


def implied_after(record: dict, earlier: list[dict]) -> list[tuple[str, str]]:
    """Predecessors of a call that declared none, by stage rule.

    ``earlier`` holds the records that started before this one, in start
    order; the latest matching one wins where several could.
    """
    stage, item = record["stage"], record["item"]
    if stage == "production_review":
        for prior in reversed(earlier):
            if prior["item"] == item and prior["stage"] in ("production_write", "production_repair"):
                return [(prior["stage"], item)]
        return []
    if stage == "production_repair":
        for prior in reversed(earlier):
            if prior["item"] == item and prior["stage"] == "production_review":
                return [("production_review", item)]
        return []
    if stage == "production_write":
        planning = [prior for prior in earlier if prior["stage"] in PLANNING]
        if planning:
            last = max(planning, key=lambda prior: prior["ended_ms"])
            return [(last["stage"], last["item"])]
        return []
    if stage == "sweep_audit":
        if any(prior["stage"] == "production_read" and prior["item"] == item for prior in earlier):
            return [("production_read", item)]
        return []
    if stage in ("production_consistency", "production_document_review"):
        return sorted({(prior["stage"], prior["item"]) for prior in earlier if prior["stage"] in SECTION})
    if stage == "assessment_judge":
        for prior in reversed(earlier):
            if prior["item"] == item and prior["stage"] == "assessment_blind_solve":
                return [("assessment_blind_solve", item)]
        return []
    return []


def _nodes(records: list[dict], offset_ms: float = 0.0) -> list[dict]:
    nodes = []
    for index, record in enumerate(records):
        if "started_ms" not in record or "ended_ms" not in record:
            continue
        attempts = [
            {
                "start": attempt["started_ms"] + offset_ms,
                "end": attempt["started_ms"] + attempt.get("wall_ms", 0.0) + offset_ms,
                "status": attempt.get("status"),
            }
            for attempt in record.get("attempts", [])
            if "started_ms" in attempt
        ]
        nodes.append(
            {
                "id": index,
                "stage": record["stage"],
                "item": record["item"],
                "start": record["started_ms"] + offset_ms,
                "end": record["ended_ms"] + offset_ms,
                "cache": record.get("cache"),
                "status": record.get("status"),
                "declared_after": [tuple(key) for key in record.get("after", [])],
                "attempts": attempts,
                "request_bytes": record.get("request_bytes", 0),
            }
        )
    nodes.sort(key=lambda node: (node["start"], node["id"]))
    return nodes


def _resolve(nodes: list[dict]) -> None:
    """Attach ``after`` (node ids) to every node from declared or implied keys.

    A predecessor must have ended by the time its dependent started; a call
    that was still running cannot have been waited for, whatever a key says.
    """
    for node in nodes:
        finished = [
            {"stage": prior["stage"], "item": prior["item"], "ended_ms": prior["end"]}
            for prior in nodes
            if prior["id"] != node["id"] and prior["end"] <= node["start"]
        ]
        finished.sort(key=lambda prior: prior["ended_ms"])
        keys = node["declared_after"] or implied_after(
            {"stage": node["stage"], "item": node["item"]}, finished
        )
        node["after"] = []
        for key in keys:
            candidates = [
                prior for prior in nodes
                if (prior["stage"], prior["item"]) == tuple(key)
                and prior["id"] != node["id"] and prior["end"] <= node["start"]
            ]
            if candidates:
                node["after"].append(max(candidates, key=lambda prior: (prior["end"], prior["id"]))["id"])
        node["after_source"] = (
            "declared" if node["declared_after"] and node["after"]
            else ("implied" if node["after"] else "root")
        )


def _critical_path(nodes: list[dict]) -> list[dict]:
    by_id = {node["id"]: node for node in nodes}
    best: dict[int, float] = {}
    back: dict[int, int | None] = {}
    for node in nodes:  # start order; predecessors start earlier
        duration = node["end"] - node["start"]
        candidates = [(best[p], p) for p in node["after"] if p in best]
        if candidates:
            length, parent = max(candidates)
            best[node["id"]], back[node["id"]] = length + duration, parent
        else:
            best[node["id"]], back[node["id"]] = duration, None
    if not best:
        return []
    tail = max(best, key=lambda i: (best[i], -i))
    path = []
    while tail is not None:
        path.append(by_id[tail])
        tail = back[tail]
    return list(reversed(path))


def _concurrency(intervals: list[tuple[float, float]], horizon: tuple[float, float]):
    """Sweep the in-flight count over time. Returns (max, busy_ms_by_level)."""
    events = sorted([(start, 1) for start, _ in intervals] + [(end, -1) for _, end in intervals])
    level, peak, previous = 0, 0, horizon[0]
    busy: dict[int, float] = defaultdict(float)
    for time_point, delta in events:
        if time_point > previous:
            busy[level] += time_point - previous
            previous = time_point
        level += delta
        peak = max(peak, level)
    if horizon[1] > previous:
        busy[level] += horizon[1] - previous
    return peak, dict(busy)


def analyse(
    records: list[dict],
    *,
    workers: int,
    wall_ms: float | None = None,
    source_bytes: int | None = None,
    offset_ms: float = 0.0,
    timing: str = "measured",
) -> dict:
    """The schedule geometry of one phase or one whole run.

    ``records`` are tracker request records (``metrics()["requests"]``).
    ``wall_ms`` is the phase's measured wall time; when omitted the span of
    the records is used. ``offset_ms`` shifts every record, so a run phase can
    be placed after its planning phase on one timeline.
    """
    nodes = _nodes(records, offset_ms)
    if not nodes:
        return {"calls": 0, "note": "no timed call records"}
    _resolve(nodes)
    path = _critical_path(nodes)
    start = min(node["start"] for node in nodes)
    end = max(node["end"] for node in nodes)
    span = end - start
    wall = float(wall_ms) if wall_ms is not None else span
    model_intervals = [
        (attempt["start"], attempt["end"]) for node in nodes for attempt in node["attempts"]
    ]
    model_ms = sum(b - a for a, b in model_intervals)
    peak, busy = _concurrency(model_intervals, (start, end))
    critical_ms = sum(node["end"] - node["start"] for node in path)
    bound_ms = max(model_ms / max(workers, 1), critical_ms)
    by_stage: dict[str, list[dict]] = defaultdict(list)
    for node in nodes:
        by_stage[node["stage"]].append(node)
    stages = {}
    for stage, members in by_stage.items():
        durations = sorted(node["end"] - node["start"] for node in members)
        stage_peak, _ = _concurrency(
            [(a["start"], a["end"]) for node in members for a in node["attempts"]],
            (start, end),
        )
        stages[stage] = {
            "calls": len(members),
            "cache_hits": sum(1 for node in members if node["cache"] == "hit"),
            "median_ms": round(median(durations), 3) if durations else 0.0,
            "p90_ms": round(durations[min(len(durations) - 1, int(0.9 * len(durations)))], 3) if durations else 0.0,
            "max_ms": round(durations[-1], 3) if durations else 0.0,
            "peak_in_flight": stage_peak,
        }
    chain = [
        {
            "stage": node["stage"],
            "item": node["item"],
            "start_ms": round(node["start"], 3),
            "duration_ms": round(node["end"] - node["start"], 3),
            "after": node["after_source"],
        }
        for node in path
    ]
    serial_ms = busy.get(0, 0.0) + busy.get(1, 0.0)
    result = {
        "timing": timing,
        "calls": len(nodes),
        "model_attempts": len(model_intervals),
        "workers": workers,
        "wall_ms": round(wall, 3),
        "span_ms": round(span, 3),
        "model_ms": round(model_ms, 3),
        "critical_path_ms": round(critical_ms, 3),
        "critical_path_depth": len(path),
        "critical_path": chain,
        "bound_ms": round(bound_ms, 3),
        "bound_binding": "critical_path" if critical_ms >= model_ms / max(workers, 1) else "work_over_workers",
        "wall_over_bound": round(wall / bound_ms, 3) if bound_ms > 0 else None,
        "peak_in_flight": peak,
        "mean_in_flight": round(model_ms / span, 3) if span > 0 else None,
        "serial_ms": round(serial_ms, 3),
        "serial_fraction": round(serial_ms / span, 3) if span > 0 else None,
        "idle_ms": round(busy.get(0, 0.0), 3),
        "stages": stages,
        "edges": {
            "declared": sum(1 for node in nodes if node["after_source"] == "declared"),
            "implied": sum(1 for node in nodes if node["after_source"] == "implied"),
            "roots": sum(1 for node in nodes if node["after_source"] == "root"),
        },
        "timeline": [
            {
                "id": node["id"],
                "stage": node["stage"],
                "item": node["item"],
                "start_ms": round(node["start"], 3),
                "end_ms": round(node["end"], 3),
                "cache": node["cache"],
                "status": node["status"],
                "after": node["after"],
                "attempts": [
                    {"start_ms": round(a["start"], 3), "end_ms": round(a["end"], 3), "status": a["status"]}
                    for a in node["attempts"]
                ],
            }
            for node in nodes
        ],
        "scope": (
            "Measured from this run's call records. The bound is max(model time / workers, "
            "critical path); wall_over_bound is 1.0 for a perfect schedule. Dependencies are "
            "declared by the planner where it knows them and implied by stage rules elsewhere; "
            "both are counted under edges."
        ),
    }
    context_bytes = sum(node["request_bytes"] for node in nodes)
    result["context_bytes"] = context_bytes
    if source_bytes:
        result["amplification_bytes"] = round(context_bytes / source_bytes, 3)
        result["source_bytes"] = source_bytes
    critical_ids = {node["id"] for node in path}
    for row in result["timeline"]:
        row["critical"] = row["id"] in critical_ids
    return result


def combine(plan_geometry: dict | None, run_records: list[dict], *, workers: int, wall_ms: float, source_bytes: int | None, timing: str = "measured") -> dict:
    """Geometry of planning followed by the run, on one timeline.

    The run phase is placed after the planning phase's span. A run that was
    started later from a saved plan (a revision) is still shown this way; the
    receipt's own wall times keep the real clock.
    """
    if not plan_geometry or "timeline" not in plan_geometry:
        return analyse(run_records, workers=workers, wall_ms=wall_ms, source_bytes=source_bytes, timing=timing)
    # The run begins once planning has returned, so its records start after
    # the planning phase's wall time, which is at or past its last call.
    offset = max(
        plan_geometry.get("wall_ms") or 0.0,
        max((row["end_ms"] for row in plan_geometry["timeline"]), default=0.0),
    )
    plan_records = [
        {
            "stage": row["stage"],
            "item": row["item"],
            "started_ms": row["start_ms"],
            "ended_ms": row["end_ms"],
            "cache": row["cache"],
            "status": row["status"],
            "after": [],
            "attempts": [
                {"started_ms": a["start_ms"], "wall_ms": a["end_ms"] - a["start_ms"], "status": a["status"]}
                for a in row["attempts"]
            ],
            "request_bytes": 0,
        }
        for row in plan_geometry["timeline"]
    ]
    # Re-attach declared predecessors by key so the merged graph keeps them.
    for record, row in zip(plan_records, plan_geometry["timeline"]):
        record["after"] = [
            [plan_geometry["timeline"][p]["stage"], plan_geometry["timeline"][p]["item"]]
            for p in row.get("after", [])
            if p < len(plan_geometry["timeline"])
        ]
    shifted = [
        {**record, "started_ms": record["started_ms"] + offset, "ended_ms": record["ended_ms"] + offset,
         "attempts": [{**a, "started_ms": a["started_ms"] + offset} for a in record.get("attempts", []) if "started_ms" in a]}
        for record in run_records
        if "started_ms" in record
    ]
    merged = analyse(plan_records + shifted, workers=workers, wall_ms=plan_geometry["wall_ms"] + wall_ms, source_bytes=source_bytes, timing=timing)
    merged["context_bytes"] = plan_geometry.get("context_bytes", 0) + sum(r.get("request_bytes", 0) for r in run_records)
    if source_bytes:
        merged["amplification_bytes"] = round(merged["context_bytes"] / source_bytes, 3)
    merged["phases"] = {"plan_ms": plan_geometry["wall_ms"], "run_ms": round(wall_ms, 3)}
    return merged


_LANE_ORDER = [
    "production_read", "sweep_audit", "production_group", "production_route", "production_targets",
    "production_assign", "production_write", "production_review", "production_repair",
    "production_consistency", "production_compare", "assessment_blind_solve", "assessment_judge",
]
_LABELS = {
    "production_read": "read", "sweep_audit": "audit", "production_group": "group",
    "production_route": "outline", "production_targets": "targets", "production_assign": "assign",
    "production_write": "write", "production_review": "review", "production_repair": "repair",
    "production_consistency": "consistency", "production_compare": "compare",
    "assessment_blind_solve": "solve", "assessment_judge": "judge",
}


def timeline_svg(geometry: dict, *, width: int = 960) -> str:
    """One SVG: a lane per stage, a bar per call, the critical path in a second
    colour, a cache hit outlined, and the in-flight count along the bottom."""
    rows = geometry.get("timeline") or []
    if not rows:
        return '<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"></svg>'
    span = max(1.0, max(row["end_ms"] for row in rows) - min(row["start_ms"] for row in rows))
    origin = min(row["start_ms"] for row in rows)
    left, right, top = 92, 16, 18
    scale = (width - left - right) / span
    stages_present = [s for s in _LANE_ORDER if any(r["stage"] == s for r in rows)]
    stages_present += sorted({r["stage"] for r in rows} - set(stages_present))
    # Pack bars within a lane into sub-rows so overlapping calls stay visible.
    lane_rows: dict[str, list[list[dict]]] = {}
    for stage in stages_present:
        members = sorted((r for r in rows if r["stage"] == stage), key=lambda r: r["start_ms"])
        packed: list[list[dict]] = []
        for row in members:
            for sub in packed:
                if sub[-1]["end_ms"] <= row["start_ms"]:
                    sub.append(row)
                    break
            else:
                packed.append([row])
        lane_rows[stage] = packed[:24]  # a lane shows at most 24 sub-rows
    bar_h, gap = 6, 2
    y = top
    parts = []

    def esc(text):
        return str(text).replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")

    for stage in stages_present:
        packed = lane_rows[stage]
        lane_h = max(1, len(packed)) * (bar_h + gap) + 6
        parts.append(f'<text x="{left - 8}" y="{y + 11}" text-anchor="end" class="lane">{esc(_LABELS.get(stage, stage))}</text>')
        parts.append(f'<line x1="{left}" y1="{y + lane_h}" x2="{width - right}" y2="{y + lane_h}" class="rule"/>')
        for sub_index, sub in enumerate(packed):
            for row in sub:
                x = left + (row["start_ms"] - origin) * scale
                w = max(1.0, (row["end_ms"] - row["start_ms"]) * scale)
                cls = "critical" if row.get("critical") else "call"
                if row.get("cache") == "hit":
                    cls += " hit"
                if row.get("status") == "failed":
                    cls += " failed"
                title = f'{_LABELS.get(stage, stage)} {row["item"]}: {row["end_ms"] - row["start_ms"]:.0f} ms'
                parts.append(
                    f'<rect x="{x:.1f}" y="{y + 3 + sub_index * (bar_h + gap)}" width="{w:.1f}" height="{bar_h}" class="{cls}"><title>{esc(title)}</title></rect>'
                )
        y += lane_h
    # In-flight strip.
    attempts = [(a["start_ms"], a["end_ms"]) for r in rows for a in r.get("attempts", [])]
    strip_h = 28
    if attempts:
        events = sorted([(s, 1) for s, _ in attempts] + [(e, -1) for _, e in attempts])
        peak = max(1, geometry.get("peak_in_flight") or 1)
        level, previous = 0, origin
        points = [f"{left:.1f},{y + strip_h:.1f}"]
        for t, d in events:
            xa = left + (previous - origin) * scale
            xb = left + (t - origin) * scale
            ya = y + strip_h - (level / peak) * (strip_h - 4)
            points.append(f"{xa:.1f},{ya:.1f}")
            points.append(f"{xb:.1f},{ya:.1f}")
            level += d
            previous = t
        points.append(f"{left + (previous - origin) * scale:.1f},{y + strip_h:.1f}")
        parts.append(f'<polygon points="{" ".join(points)}" class="load"/>')
        parts.append(f'<text x="{left - 8}" y="{y + strip_h - 6}" text-anchor="end" class="lane">in flight ≤{peak}</text>')
        y += strip_h + 6
    # Axis.
    ticks = 6
    for i in range(ticks + 1):
        t = origin + span * i / ticks
        x = left + (t - origin) * scale
        label = f"{(t - origin) / 1000:.1f}s" if span >= 2000 else f"{t - origin:.0f}ms"
        parts.append(f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{y}" class="tick"/>')
        parts.append(f'<text x="{x:.1f}" y="{y + 14}" text-anchor="middle" class="axis">{label}</text>')
    y += 34
    caption = (
        f'{geometry.get("calls")} calls · critical path {geometry.get("critical_path_depth")} deep, '
        f'{(geometry.get("critical_path_ms") or 0) / 1000:.1f}s · bound {(geometry.get("bound_ms") or 0) / 1000:.1f}s '
        f'({geometry.get("bound_binding", "").replace("_", " ")}) · wall {(geometry.get("wall_ms") or 0) / 1000:.1f}s '
        f'· wall/bound {geometry.get("wall_over_bound")} · serial {int(100 * (geometry.get("serial_fraction") or 0))}%'
    )
    parts.append(f'<text x="{left}" y="{y}" class="caption">{esc(caption)}</text>')
    height = y + 12
    style = (
        "<style>text{font:11px ui-monospace,SFMono-Regular,Menlo,monospace;fill:#3b4a46}"
        ".lane{fill:#5a6b66}.axis{fill:#8a9792}.caption{fill:#243530;font-size:12px}"
        ".rule{stroke:#e1e6e2;stroke-width:1}.tick{stroke:#eef1ee;stroke-width:1}"
        ".call{fill:#9fb7ab}.critical{fill:#1f6e4e}.hit{fill:none;stroke:#9fb7ab;stroke-width:1}"
        ".critical.hit{stroke:#1f6e4e}.failed{fill:#c0392b}.load{fill:#dbe5df;stroke:#8aa397;stroke-width:1}</style>"
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        f'role="img" aria-label="Run timeline with the critical path highlighted">{style}{"".join(parts)}</svg>'
    )
