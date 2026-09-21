import copy

import pytest

from lamina.procedures import BUILTINS, procedure_context, validate_procedure


def test_builtins_are_valid_and_context_changes_with_instruction():
    assert {p["id"] for p in BUILTINS} == {"study-guide", "samp", "oral-case", "audio-script"}
    first = validate_procedure(BUILTINS[0])
    changed = copy.deepcopy(first)
    changed["instructions"] += " Ask for a decision after the explanation."
    assert procedure_context(first)["revision"] != procedure_context(changed)["revision"]
    assert procedure_context(changed)["instructions"] == changed["instructions"]


@pytest.mark.parametrize("change", [
    {"command": "cat ~/.secret"},
    {"outputs": ["study-guide", "study-guide"]},
    {"outputs": ["shell"]},
    {"workers": True},
    {"workers": 0},
    {"schema_version": "2"},
    {"id": "../unsafe"},
    {"instructions": "x" * 4001},
])
def test_procedure_rejects_unsupported_or_unbounded_fields(change):
    data = copy.deepcopy(BUILTINS[0])
    data.update(change)
    with pytest.raises(ValueError):
        validate_procedure(data)
