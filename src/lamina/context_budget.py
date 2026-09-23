"""Fit complete source structures to an explicitly measured request budget.

The caller supplies the complete request builder and, when available, the
adapter's token counter. Byte limits protect transport; they do not estimate
tokens, task difficulty, or extraction quality.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .store import canonical


class ContextBudgetError(ValueError):
    """A complete request cannot fit its configured resource allowance."""


class OversizedUnit(ContextBudgetError):
    """A source structure needs an explicit decomposition or a larger budget."""


@dataclass(frozen=True)
class BudgetMeasurement:
    request_bytes: int
    input_tokens: int | None
    available_input_tokens: int | None
    counting: str


@dataclass(frozen=True)
class RequestBudget:
    max_request_bytes: int
    context_tokens: int | None = None
    output_tokens: int = 0
    count_tokens: Callable[[dict], int] | None = None
    counting: str = "bytes"

    def __post_init__(self):
        if type(self.max_request_bytes) is not int or self.max_request_bytes < 1:
            raise ValueError("max_request_bytes must be a positive integer")
        if type(self.output_tokens) is not int or self.output_tokens < 0:
            raise ValueError("output_tokens must be a nonnegative integer")
        if self.context_tokens is not None:
            if type(self.context_tokens) is not int or self.context_tokens < 1:
                raise ValueError("context_tokens must be a positive integer")
            if self.output_tokens >= self.context_tokens:
                raise ValueError("output reserve must be smaller than context_tokens")
            if not callable(self.count_tokens):
                raise ValueError(
                    "a token context limit requires an adapter token counter"
                )
            if self.counting == "bytes":
                object.__setattr__(self, "counting", "adapter-token-counter")
        elif self.output_tokens:
            raise ValueError("output_tokens requires context_tokens")

    def measure(self, request: dict) -> BudgetMeasurement:
        tokens = self.count_tokens(request) if self.count_tokens is not None else None
        if tokens is not None and (type(tokens) is not int or tokens < 0):
            raise ValueError("adapter token counter must return a nonnegative integer")
        return BudgetMeasurement(
            request_bytes=len(canonical(request).encode("utf-8")),
            input_tokens=tokens,
            available_input_tokens=(
                self.context_tokens - self.output_tokens
                if self.context_tokens is not None
                else None
            ),
            counting=self.counting,
        )

    def accepts(self, measurement: BudgetMeasurement) -> bool:
        return measurement.request_bytes <= self.max_request_bytes and (
            measurement.available_input_tokens is None
            or measurement.input_tokens <= measurement.available_input_tokens
        )

    def fits(self, request: dict) -> bool:
        return self.accepts(self.measure(request))

    def check(self, request: dict) -> BudgetMeasurement:
        measurement = self.measure(request)
        if measurement.request_bytes > self.max_request_bytes:
            raise ContextBudgetError(
                f"request exceeds the transport budget: {measurement.request_bytes} "
                f"> {self.max_request_bytes} bytes"
            )
        if not self.accepts(measurement):
            raise ContextBudgetError(
                f"request exceeds the model input budget: {measurement.input_tokens} "
                f"> {measurement.available_input_tokens} tokens "
                f"({self.output_tokens} reserved for output)"
            )
        return measurement


@dataclass(frozen=True)
class PackedBatch:
    units: list[dict]
    measurement: BudgetMeasurement


def pack_units(
    units: list[dict],
    make_request: Callable[[list[dict]], dict],
    budget: RequestBudget,
) -> list[PackedBatch]:
    """Pack ordered, complete source structures within full request limits.

    Headings remain metadata and do not force a new call. Sources do. A declared
    ``structural_group`` keeps related components together, such as slide text,
    tables and speaker notes. Group members must be contiguous in source order.
    Exponential probes followed by binary refinement avoid serializing every
    growing prefix. Every returned batch is measured in its complete envelope.
    """
    if not units:
        return []
    budget.check(make_request([]))
    bundles: list[list[dict]] = []
    seen_groups = set()
    previous_key = None
    for unit in units:
        group = unit.get("structural_group")
        key = (unit["source_id"], group) if group is not None else None
        if key is not None and key == previous_key:
            bundles[-1].append(unit)
        else:
            if key is not None:
                if key in seen_groups:
                    raise ValueError(f"structural group {group!r} is not contiguous")
                seen_groups.add(key)
            bundles.append([unit])
        previous_key = key

    result = []
    start = 0
    while start < len(bundles):
        source_id = bundles[start][0]["source_id"]
        stop = start + 1
        while stop < len(bundles) and bundles[stop][0]["source_id"] == source_id:
            stop += 1
        while start < stop:
            measurements = {}

            def candidate(end):
                if end not in measurements:
                    selected = [u for bundle in bundles[start:end] for u in bundle]
                    measurements[end] = (
                        selected,
                        budget.measure(make_request(selected)),
                    )
                return measurements[end]

            first, usage = candidate(start + 1)
            if not budget.accepts(usage):
                names = ", ".join(u.get("locator", u["id"]) for u in first)
                try:
                    budget.check(make_request(first))
                except ContextBudgetError as exc:
                    raise OversizedUnit(
                        f"Source structure at {names} cannot fit intact: {exc}. "
                        "Use a provider with more input capacity or explicitly "
                        "decompose this structure while retaining its relationships."
                    ) from exc
            best = start + 1
            upper = min(stop, start + 2)
            while upper > best:
                _, usage = candidate(upper)
                if not budget.accepts(usage):
                    break
                best = upper
                upper = min(stop, start + 2 * (upper - start))
            lo, hi = best + 1, upper - 1
            while lo <= hi:
                middle = (lo + hi) // 2
                _, usage = candidate(middle)
                if budget.accepts(usage):
                    best, lo = middle, middle + 1
                else:
                    hi = middle - 1
            selected, usage = candidate(best)
            result.append(PackedBatch(selected, usage))
            start = best
    return result
