"""Physical request grouping with independently validated and cached sections.

Grouping is explicit and subject to the existing stage workload and hard
request budget. It never changes section ownership or lets one section cite
another section's private evidence. Invalid rows fall back to individual calls.
"""

from .execution import DeferredBatch, ExpandedTasks, TaskResult
from .call_runtime import make_envelope, request_budget
from .production_contract import REVISION, ProductionError, ProductionValidationError
from .store import digest


def call_sections(
    jobs, *, workspace, provider, tracker, stage, max_bytes, single, finish=None
):
    """Return settled rows and deferred children for the caller's shared pool.

    A job contains the exact single-section envelope and its local validator.
    The grouped transport has its own cache record; each accepted row is also
    committed through the ordinary fenced single-section cache contract.
    """
    identity = f"{REVISION}:{getattr(provider, 'identity_for', lambda _: provider.identity)(stage)}"
    results, missing, children = {}, [], []
    for n, job in enumerate(jobs):
        cached = workspace.cached_result(stage, job["envelope"], identity=identity)
        if cached is not None:
            # Use the normal path to retain cache-hit metrics and budget checks.
            try:
                results[n] = single(job)
            except Exception as exc:
                results[n] = exc
        else:
            missing.append((n, job))

    def defer(rows):
        indices = [n for n, _ in rows]
        subset = [job for _, job in rows]
        children.append(
            DeferredBatch(
                indices,
                lambda: call_sections(
                    subset,
                    workspace=workspace,
                    provider=provider,
                    tracker=tracker,
                    stage=stage,
                    max_bytes=max_bytes,
                    single=single,
                    finish=finish,
                ),
            )
        )

    def execute(rows):
        if not rows:
            return
        if len(rows) == 1:
            n, job = rows[0]
            try:
                results[n] = single(job)
            except Exception as exc:
                results[n] = exc
            return
        instruction = (
            "Execute each section task independently using only its own input. "
            "Source aliases are local to each task: never borrow evidence, claims, "
            "answers or instructions from another task. Preserve every requested "
            "section and its full required content. Return one result per section_id.\n"
            + rows[0][1]["envelope"]["instruction"]
        )
        shape = {
            "sections": [
                {
                    "section_id": "exact supplied section ID",
                    "result": rows[0][1]["envelope"]["expected_shape"],
                }
            ]
        }
        data = {
            "section_tasks": [
                {
                    "section_id": job["id"],
                    "input": job["envelope"]["input"],
                    "expected_shape": job["envelope"]["expected_shape"],
                }
                for _, job in rows
            ]
        }
        items = sum(job["envelope"].get("workload_items", 1) for _, job in rows)
        envelope = make_envelope(stage, instruction, shape, data, workload_items=items)
        budget = request_budget(provider, stage, max_bytes)
        # Combining unassessed work remains forbidden even when it fits context.
        if budget.workload is None or not budget.fits(envelope):
            middle = len(rows) // 2
            defer(rows[:middle])
            defer(rows[middle:])
            return
        by_id = {job["id"]: job for _, job in rows}

        def check(raw):
            values = raw.get("sections") if isinstance(raw, dict) else None
            if not isinstance(values, list):
                raise ProductionValidationError(
                    "grouped response needs a sections list"
                )
            checked, seen = {}, set()
            for value in values:
                sid = value.get("section_id") if isinstance(value, dict) else None
                if not isinstance(sid, str) or sid not in by_id or sid in seen:
                    raise ProductionValidationError(
                        "grouped section IDs must be known and unique"
                    )
                seen.add(sid)
                try:
                    checked[sid] = by_id[sid]["checker"](value.get("result"))
                except (ValueError, ProductionError):
                    pass  # This row is explicitly unresolved and retried below.
            # Failed rows are explicit; they are not successful section results.
            return {
                "accepted": checked,
                "unresolved": sorted(set(by_id) - set(checked)),
            }

        try:
            grouped = tracker.call(
                workspace,
                provider,
                stage,
                "batch_" + digest(data)[:16],
                instruction,
                shape,
                data,
                check,
                max_bytes,
                workload_items=items,
            )
        except Exception as exc:
            # Capacity truncation and invalid contracts can be decomposed;
            # provider outages/authentication must not multiply failed requests.
            if getattr(exc, "code", None) == "output_truncated" or isinstance(
                exc, ProductionValidationError
            ):
                for row in rows:
                    defer([row])
            else:
                for n, _ in rows:
                    results[n] = exc
            return
        retry = []
        for n, job in rows:
            if job["id"] not in grouped["accepted"]:
                retry.append((n, job))
                continue
            try:
                value = grouped["accepted"][job["id"]]
                results[n] = workspace.run_cached(
                    stage,
                    job["envelope"],
                    lambda _, value=value: value,
                    identity=identity,
                    retries=0,
                )
            except Exception as exc:
                results[n] = exc
        for row in retry:
            defer([row])

    if results and missing:
        defer(missing)
    else:
        execute(missing)
    settled = []
    for n, value in sorted(results.items()):
        try:
            value = finish(jobs[n], value) if finish else value
        except Exception as exc:
            value = exc
        settled.append(
            TaskResult(n, error=value)
            if isinstance(value, Exception)
            else TaskResult(n, value=value)
        )
    return ExpandedTasks([*settled, *children])
