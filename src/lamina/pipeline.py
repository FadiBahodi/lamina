"""Source-grounded concept -> plan -> lesson -> review pipeline."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

from . import prompts, validation
from .procedures import procedure_context
from .providers import DemoProvider

if TYPE_CHECKING:
    from .store import Workspace


PIPELINE_REVISION = "lamina-pipeline-3"
HALO_CHARS = 450


def _public_unit(row: dict) -> dict:
    return {key: row[key] for key in ("id", "source_id", "heading", "text", "locator", "ordinal", "role")}


def _stage(workspace: Workspace, provider, name: str, payload: dict, checker) -> dict:
    envelope = prompts.request(name, payload)
    if name in {"plan", "author"} and payload.get("procedure"):
        procedure = payload["procedure"]
        envelope["instruction"] += (
            " Apply the operator's data-only teaching brief within the required output schema. "
            "Audience: " + procedure["audience"] + " Teaching brief: " + procedure["instructions"]
        )

    def handler(request: dict) -> dict:
        raw = provider.call(name, request)
        return checker(raw)

    return workspace.run_cached(name, envelope, handler,
                                identity=f"{PIPELINE_REVISION}:{provider.identity}:{prompts.REVISION}",
                                retries=1)


def build(workspace: Workspace, provider, workers: int = 4, procedure: dict | None = None) -> dict:
    """Build a validated bundle; assessment text never enters model requests.

    Stage results are cached by the workspace. A failed or revise review blocks
    the build, leaving earlier successful stages available for retry.
    """
    if workers < 1 or workers > 32:
        raise ValueError("workers must be between 1 and 32")
    guidance = procedure_context(procedure) if procedure is not None else None

    def stage(name: str, payload: dict, checker) -> dict:
        # The same bounded procedure context travels through every semantic
        # stage. It is part of the durable request key, so edited instructions
        # invalidate cached outputs without changing the source identity.
        if guidance is not None:
            payload = {**payload, "procedure": guidance}
        return _stage(workspace, provider, name, payload, checker)
    all_units = workspace.units()
    units = sorted((_public_unit(u) for u in all_units if u.get("role") == "teaching"),
                   key=lambda u: (u["source_id"], u["ordinal"]))
    if not units:
        raise ValueError("workspace has no teaching units")
    source_ids = {u["source_id"] for u in units}
    sources = [{key: s[key] for key in ("id", "title", "filename", "sha256", "role")}
               for s in workspace.sources() if s.get("role") == "teaching" and s["id"] in source_ids]
    sources.sort(key=lambda s: s["id"])
    source_manifest = [{"filename": s["filename"], "sha256": s["sha256"]} for s in sources]
    units_by_id = {u["id"]: u for u in units}
    if any(u["source_id"] not in {s["id"] for s in sources} for u in units):
        raise validation.ValidationError("teaching unit has no teaching source")
    positions = {u["id"]: i for i, u in enumerate(units)}

    def read(unit: dict) -> list[dict]:
        index = positions[unit["id"]]
        same_source = lambda other: other["source_id"] == unit["source_id"]
        before = units[index - 1] if index and same_source(units[index - 1]) else None
        after = units[index + 1] if index + 1 < len(units) and same_source(units[index + 1]) else None
        own_source = next(s for s in sources if s["id"] == unit["source_id"])
        payload = {"source_manifest": [{"filename": own_source["filename"],
                                         "sha256": own_source["sha256"]}],
                   "source": next(s for s in sources if s["id"] == unit["source_id"]),
                   "core": unit,
                   "before": {"id": before["id"], "text": before["text"][-HALO_CHARS:]}
                   if before else None,
                   "after": {"id": after["id"], "text": after["text"][:HALO_CHARS]}
                   if after else None}
        result = stage("extract", payload,
                        lambda raw: {"concepts": validation.validate_extraction(raw, unit, units_by_id)})
        return result["concepts"]

    with ThreadPoolExecutor(max_workers=workers) as pool:
        concept_groups = list(pool.map(read, units))
    raw_concepts = [concept for group in concept_groups for concept in group]
    if not raw_concepts:
        raise validation.ValidationError("extraction yielded no concepts")
    concepts_result = stage(
        "reconcile",
        {"source_manifest": source_manifest, "raw_concepts": raw_concepts},
        lambda raw: {"concepts": validation.validate_reconcile(raw, raw_concepts, units_by_id)},
    )
    concepts = concepts_result["concepts"]
    concept_by_id = {c["id"]: c for c in concepts}
    plan = stage("plan", {"source_manifest": source_manifest,
                                                 "concepts": concepts,
                                                 "source_titles": [s["title"] for s in sources]},
                  lambda raw: validation.validate_plan(raw, concepts))

    # A shared route is a specification, not a claim that parallel writers have
    # seen one another's completed prose. Restore exact prerequisite evidence
    # for callbacks instead of asking a writer to infer it from lesson titles.
    shared_route = [{"id": row["id"], "title": row["title"],
                     "prerequisite_ids": row["prerequisite_ids"],
                     "ideas": [{"id": cid, "title": concept_by_id[cid]["title"]}
                               for cid in row["concept_ids"]]}
                    for row in plan["lessons"]]

    def write(planned: dict) -> dict:
        assigned = [concept_by_id[cid] for cid in planned["concept_ids"]]
        unit_ids = {e["unit_id"] for c in assigned for e in c["evidence"]}
        evidence_units = [u for u in units if u["id"] in unit_ids]
        evidence_source_ids = {u["source_id"] for u in evidence_units}
        assigned_manifest = [{"filename": s["filename"], "sha256": s["sha256"]}
                             for s in sources if s["id"] in evidence_source_ids]
        prior_lessons = []
        for row in plan["lessons"]:
            if row["id"] not in planned["prerequisite_ids"]:
                continue
            prior_concepts = [concept_by_id[cid] for cid in row["concept_ids"]]
            prior_unit_ids = {e["unit_id"] for c in prior_concepts for e in c["evidence"]}
            prior_lessons.append({"id": row["id"], "title": row["title"],
                                  "concepts": prior_concepts,
                                  "units": [u for u in units if u["id"] in prior_unit_ids]})
        payload = {"source_manifest": assigned_manifest,
                   "lesson": planned, "concepts": assigned, "units": evidence_units,
                   "shared_route": shared_route,
                   "earlier_lessons": prior_lessons,
                   "context_scope": "Shared plan and exact prerequisite evidence; not completed earlier prose. Prerequisite context does not change ownership of this lesson's assigned concepts."}
        authored = stage("author", payload,
                          lambda raw: validation.validate_lesson(raw, planned, concept_by_id, units_by_id))
        review_payload = {"source_manifest": assigned_manifest,
                          "lesson": authored, "concepts": assigned, "units": evidence_units,
                          "review_rubric": "grounding, objective coverage, answerability, teaching flow"}
        review = stage("review", review_payload, validation.validate_review)
        if review["status"] != "pass":
            details = "; ".join(str(i["detail"]) for i in review["issues"])
            raise validation.ValidationError(f"lesson {planned['id']} needs revision: {details}")
        return {**authored, "review": review}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        lessons = list(pool.map(write, plan["lessons"]))
    counts = workspace.stats()
    return {
        "schema_version": "1.0", "title": plan["title"],
        "description": "A source-grounded learning sequence with teaching, practice, and a speakable script.",
        "sources": sources, "units": units, "raw_concepts": raw_concepts,
        "concepts": concepts,
        "lessons": lessons, "plan": plan,
        "counters": {"teaching_sources": len(sources), "teaching_units": len(units),
                     "extracted_concepts": len(raw_concepts),
                     "canonical_concepts": len(concepts),
                     "assigned_concepts": sum(len(x["concept_ids"]) for x in plan["lessons"]),
                     "deferred_concepts": len(plan["deferred"]),
                     "lessons": len(lessons), "workspace": counts},
        "build": {"provider": provider.identity,
                  "review_mode": "curated_fixture" if isinstance(provider, DemoProvider) else "configured_adapter",
                  "review_scope": ("Curated offline fixture review response; no model review was run."
                                   if isinstance(provider, DemoProvider) else
                                   "Configured adapter review of grounding, assigned objectives, answerability, and flow; no independent truth or mastery guarantee."),
                  "coverage_scope": "Assignment of extracted concepts, not completeness of source comprehension.",
                  "assessment_boundary": "Held-out assessment text was excluded from generation and this bundle.",
                  "audio_scope": "Speakable script only; no audio synthesized or audited."},
    }
