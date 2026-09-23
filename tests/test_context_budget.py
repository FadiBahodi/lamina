"""Request capacity checks preserve source ownership and known structure."""

import pytest

from lamina.context_budget import (
    ContextBudgetError,
    OversizedUnit,
    RequestBudget,
    pack_units,
)
from lamina.store import canonical


def envelope(units):
    return {
        "instruction": "Read the supplied source structures and retain qualifications.",
        "expected_shape": {"ideas": [{"text": "string", "evidence": "exact quote"}]},
        "input": {"brief": "Explain how wind turbines work.", "units": units},
    }


def unit(index, text="Wind rotates the blades.", **metadata):
    return {
        "id": f"u{index}",
        "source_id": "wind",
        "text": text,
        "heading": f"Heading {index}",
        **metadata,
    }


def test_complete_envelope_and_output_reserve_determine_fit():
    # This adapter's toy counter is deliberately explicit, not a production
    # bytes-to-tokens estimate. Prompt/schema overhead counts with source text.
    count = lambda request: len(canonical(request))
    single = envelope([unit(0)])
    needed = count(single)
    exact = RequestBudget(100_000, needed + 40, 40, count)
    assert exact.fits(single)
    assert exact.check(single).available_input_tokens == needed
    smaller = RequestBudget(100_000, needed + 39, 40, count)
    with pytest.raises(ContextBudgetError, match="reserved for output"):
        smaller.check(single)
    assert not smaller.fits(single)


def test_unknown_model_reports_bytes_without_invented_tokens():
    measured = RequestBudget(4096).check(envelope([unit(0, "风使叶片旋转。")]))
    assert measured.input_tokens is None
    assert measured.available_input_tokens is None
    assert measured.counting == "bytes"
    with pytest.raises(ValueError, match="requires an adapter token counter"):
        RequestBudget(4096, context_tokens=1000)


def test_heading_heavy_document_packs_across_heading_boundaries():
    units = [unit(i) for i in range(1000)]
    calls = []

    def make_request(selected):
        calls.append(len(selected))
        return envelope(selected)

    batches = pack_units(units, make_request, RequestBudget(1_000_000))
    assert len(batches) == 1
    assert batches[0].units == units
    assert len(calls) < 20  # No complete-prefix recount on every append.


def test_ownership_is_complete_unique_and_sources_stay_separate():
    units = [unit(i, "The rotor transfers force. " * 10) for i in range(12)]
    units.extend([unit(12, source_id="second"), unit(13, source_id="second")])
    budget = RequestBudget(1800)
    batches = pack_units(units, envelope, budget)
    assert [u for batch in batches for u in batch.units] == units
    assert all(len({u["source_id"] for u in b.units}) == 1 for b in batches)
    assert all(budget.fits(envelope(b.units)) for b in batches)
    assert len(batches) > 2


def test_slide_text_table_and_notes_remain_together():
    slide = [
        unit(0, kind="text", structural_group="slide:1"),
        unit(
            1,
            "Design | Wind\nWide blade | Low",
            kind="table",
            structural_group="slide:1",
        ),
        unit(
            2,
            "This applies only below the rated wind speed.",
            kind="speaker_notes",
            structural_group="slide:1",
        ),
    ]
    other = unit(3, structural_group="slide:2")
    limit = len(canonical(envelope(slide)).encode())
    batches = pack_units(slide + [other], envelope, RequestBudget(limit))
    assert [b.units for b in batches] == [slide, [other]]
    with pytest.raises(OversizedUnit, match="cannot fit intact"):
        pack_units(slide, envelope, RequestBudget(limit - 1))


def test_oversized_table_is_reported_without_slicing_or_omission():
    table = unit(0, "| Blade | Low wind |\n" * 500, kind="table", locator="lines 4–504")
    with pytest.raises(OversizedUnit, match="lines 4–504.*explicitly decompose"):
        pack_units([table], envelope, RequestBudget(1000))


def test_oversized_prompt_is_reported_before_blame_is_assigned_to_source():
    with pytest.raises(ContextBudgetError, match="transport budget") as result:
        pack_units([unit(0)], envelope, RequestBudget(10))
    assert not isinstance(result.value, OversizedUnit)


def test_noncontiguous_structural_group_is_rejected():
    units = [
        unit(0, structural_group="slide:1"),
        unit(1),
        unit(2, structural_group="slide:1"),
    ]
    with pytest.raises(ValueError, match="not contiguous"):
        pack_units(units, envelope, RequestBudget(10_000))


def test_real_tokenizer_counts_multilingual_no_whitespace_material():
    tiktoken = pytest.importorskip("tiktoken")
    encoding = tiktoken.get_encoding("cl100k_base")
    count = lambda request: len(encoding.encode(canonical(request)))
    units = [
        unit(0, "Wind turns the blades. " * 50),
        unit(1, "风使叶片旋转并带动发电机。" * 50),
        unit(2, "تدير الرياح الشفرات المتصلة بالمولد. " * 50),
    ]
    capacity = max(count(envelope([u])) for u in units)
    budget = RequestBudget(1_000_000, capacity + 100, 100, count)
    batches = pack_units(units, envelope, budget)
    assert [u for b in batches for u in b.units] == units
    assert all(b.measurement.input_tokens <= capacity for b in batches)
    assert len(batches) >= 2
