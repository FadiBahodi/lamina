"""Declarative, data-only instructions for one local learning run.

Procedures select outputs and guide semantic stages. They cannot name a command,
file, URL, model, or executable; the operator configures an adapter separately.
"""
from __future__ import annotations

import hashlib
import json
import re

OUTPUTS = frozenset({"study-guide", "samp", "oral-case", "audio-script"})
FIELDS = frozenset({"schema_version", "id", "name", "description", "audience", "instructions", "outputs", "workers"})
ID_PATTERN = re.compile(r"[a-z][a-z0-9-]{0,47}\Z")


def validate_procedure(value: object) -> dict:
    """Return a canonical v1 procedure or reject unsupported/active fields."""
    if not isinstance(value, dict):
        raise ValueError("procedure must be a JSON object")
    if set(value) != FIELDS:
        missing, extra = FIELDS - set(value), set(value) - FIELDS
        raise ValueError(f"procedure fields mismatch: missing {sorted(missing)}, unknown {sorted(extra)}")
    if value["schema_version"] != "1":
        raise ValueError("procedure.schema_version must be '1'")
    if not isinstance(value["id"], str) or not ID_PATTERN.fullmatch(value["id"]):
        raise ValueError("procedure.id must be a short lowercase slug")
    for field, limit in (("name", 100), ("description", 500), ("audience", 300), ("instructions", 4000)):
        text = value[field]
        if not isinstance(text, str) or not text.strip() or len(text) > limit or "\x00" in text:
            raise ValueError(f"procedure.{field} must contain 1–{limit} characters")
    outputs = value["outputs"]
    if not isinstance(outputs, list) or not outputs or len(outputs) > len(OUTPUTS):
        raise ValueError("procedure.outputs must be a nonempty list")
    if any(not isinstance(item, str) or item not in OUTPUTS for item in outputs) or len(set(outputs)) != len(outputs):
        raise ValueError("procedure.outputs contains an unknown or repeated output")
    workers = value["workers"]
    if type(workers) is not int or not 1 <= workers <= 16:
        raise ValueError("procedure.workers must be an integer from 1 to 16")
    ordered = ("schema_version", "id", "name", "description", "audience", "instructions", "outputs", "workers")
    return {key: value[key].strip() if key in {"name", "description", "audience", "instructions"} else
            list(value[key]) if key == "outputs" else value[key] for key in ordered}


def procedure_context(value: dict) -> dict:
    """The bounded instruction context included in every stage and cache key."""
    procedure = validate_procedure(value)
    revision = hashlib.sha256(json.dumps(procedure, sort_keys=True, separators=(",", ":"),
                                         ensure_ascii=False).encode()).hexdigest()[:20]
    return {"id": procedure["id"], "revision": revision,
            "audience": procedure["audience"], "instructions": procedure["instructions"],
            "outputs": procedure["outputs"]}


BUILTINS = [
    {"schema_version": "1", "id": "study-guide", "name": "Source-grounded study guide",
     "description": "Connected lessons with evidence, recall, contrasts, application, and a reviewed study site.",
     "audience": "A learner who needs to explain and apply the supplied source material.",
     "instructions": "Make the global plan coherent. Give each lesson a clear objective and use the source evidence for answerable recall and application. Explicitly defer concepts that cannot fit.",
     "outputs": ["study-guide"], "workers": 4},
    {"schema_version": "1", "id": "samp", "name": "Progressive short-answer problems",
     "description": "Source-grounded problems with staged information and a separate examiner answer sheet.",
     "audience": "A learner practicing decisions as information arrives.",
     "instructions": "Prioritize causal decisions and evidence-backed change points in the lesson plan. Preserve concise, answerable objectives that can support progressive short-answer problems.",
     "outputs": ["samp"], "workers": 4},
    {"schema_version": "1", "id": "oral-case", "name": "Oral case practice",
     "description": "Connected lessons with examiner-reveal cases, reassessment, and debrief.",
     "audience": "A learner practicing spoken reasoning and reassessment.",
     "instructions": "Plan lessons around decisions, consequences, and reassessment. Author the required scenario with findings that can be revealed on request, a decision checklist, a second event, and a grounded debrief.",
     "outputs": ["oral-case"], "workers": 4},
    {"schema_version": "1", "id": "audio-script", "name": "Speakable teaching script",
     "description": "Connected lesson scripts intended to be read aloud; no synthesized audio is claimed.",
     "audience": "An audio learner who needs deliberate retrieval pauses.",
     "instructions": "Plan for an intelligible listening sequence. Author speakable explanations, purposeful pauses for recall, and clear verbal transitions without relying on visual layout.",
     "outputs": ["audio-script"], "workers": 4},
]
BUILTINS = [validate_procedure(item) for item in BUILTINS]
