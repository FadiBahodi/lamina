"""Bounded work submission and per-item pipelines."""

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait


def bounded_map(function, items, workers):
    """Return input order; keep at most `workers` submitted jobs alive."""
    iterator = iter(enumerate(items))
    results = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending = {}

        def fill():
            while len(pending) < workers:
                try:
                    index, item = next(iterator)
                except StopIteration:
                    break
                pending[pool.submit(function, item)] = index

        fill()
        while pending:
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                results[pending.pop(future)] = future.result()
            fill()
    return [results[i] for i in range(len(results))]


def section_pipeline(sections, write, review, repair, *, writers, reviewers, workers):
    """Schedule write → review → optional repair → recheck per section.

    One shared capacity bounds all calls. Stage limits also apply. Finished
    work takes priority over new writing, so reviews do not build an unbounded
    queue behind a large document. Results retain the planned section order.
    """
    from collections import deque

    fresh = iter(enumerate(sections))
    ready = deque()
    pending, output, initial, remaining = {}, {}, {}, {}
    occupied = {"write": 0, "review": 0}
    exhausted = False
    with ThreadPoolExecutor(max_workers=workers) as pool:
        while pending or ready or not exhausted:
            while len(pending) < workers:
                job = None
                for _ in range(len(ready)):
                    candidate = ready.popleft()
                    lane = "write" if candidate[1] == "repair" else "review"
                    if occupied[lane] < (writers if lane == "write" else reviewers):
                        job = candidate
                        break
                    ready.append(candidate)
                if job is None and not exhausted and occupied["write"] < writers:
                    try:
                        index, section = next(fresh)
                        job = (index, "write", section, None, None)
                    except StopIteration:
                        exhausted = True
                if job is None:
                    break
                index, stage, section, draft, findings = job
                lane = "write" if stage in {"write", "repair"} else "review"
                fn, arg = (
                    (write, section)
                    if stage == "write"
                    else (
                        (repair, (section, draft, findings))
                        if stage == "repair"
                        else (review, (section, draft))
                    )
                )
                pending[pool.submit(fn, arg)] = job
                occupied[lane] += 1
            if not pending:
                if ready:
                    raise RuntimeError("section scheduler cannot advance")
                continue
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                index, stage, section, draft, findings = pending.pop(future)
                occupied["write" if stage in {"write", "repair"} else "review"] -= 1
                result = future.result()
                if stage in {"write", "repair"}:
                    ready.append(
                        (
                            index,
                            "review" if stage == "write" else "recheck",
                            section,
                            result,
                            None,
                        )
                    )
                elif stage == "review" and result["findings"]:
                    initial[section["id"]] = result["findings"]
                    ready.append((index, "repair", section, draft, result["findings"]))
                else:
                    output[index] = draft
                    if result["findings"]:
                        remaining[section["id"]] = result["findings"]
    return [output[i] for i in range(len(output))], initial, remaining
