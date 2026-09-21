"""Per-project source authority and explicitly selected operator experience.

Workspace roles remain teaching/assessment. A project may further classify its
selected teaching sources. No classification can make held-out assessment data
available to production.
"""

from __future__ import annotations

import re

from .method_runtime import _tables
from .store import Workspace

SOURCE_POLICIES = {"authority", "supplement", "historical", "form_exemplar"}
DEFAULT_METHOD_FAMILY = "document-production"
_OBS_ID = re.compile(r"[0-9a-f]{32}\Z")
_FAMILY = re.compile(r"[a-z][a-z0-9-]{0,63}\Z")


def normalize_production_inputs(
    workspace: Workspace, source_ids: list[str], options: dict | None = None
) -> dict:
    """Validate selection before queueing, returning stable, explicit policy.

    `source_policy` must account for every selected source if supplied. Absent
    policy means all selected teaching sources are factual authorities for this
    project, preserving existing callers' behavior. `observation_ids` are
    operator-selected local records; they do not promote or rank a method.
    """
    if (
        not isinstance(source_ids, list)
        or not source_ids
        or len(source_ids) > 2048
        or any(not isinstance(sid, str) or not sid for sid in source_ids)
        or len(source_ids) != len(set(source_ids))
    ):
        raise ValueError("source_ids must be a nonempty list of unique source IDs")
    if options is None:
        options = {}
    if not isinstance(options, dict):
        raise ValueError("production options must be an object")
    options = dict(options)
    known = {source["id"]: source for source in workspace.sources()}
    for sid in source_ids:
        if sid not in known or known[sid].get("role") != "teaching":
            raise ValueError(f"Source {sid} is missing or is not a teaching source")
    supplied_policy = options.get("source_policy")
    if supplied_policy is None:
        policy = {sid: "authority" for sid in source_ids}
    else:
        if not isinstance(supplied_policy, dict) or set(supplied_policy) != set(
            source_ids
        ):
            raise ValueError(
                "source_policy must map every selected source ID exactly once"
            )
        if any(
            not isinstance(value, str) or value not in SOURCE_POLICIES
            for value in supplied_policy.values()
        ):
            raise ValueError(
                "source_policy values must be authority, supplement, historical, or form_exemplar"
            )
        policy = {sid: supplied_policy[sid] for sid in source_ids}
    factual_ids = [sid for sid in source_ids if policy[sid] != "form_exemplar"]
    exemplar_ids = [sid for sid in source_ids if policy[sid] == "form_exemplar"]
    if not factual_ids:
        raise ValueError("A project needs at least one factual source")
    family = options.get("method_family", DEFAULT_METHOD_FAMILY)
    if not isinstance(family, str) or not _FAMILY.fullmatch(family):
        raise ValueError("method_family must be a lowercase slug")
    observation_ids = options.get("observation_ids", [])
    if (
        not isinstance(observation_ids, list)
        or len(observation_ids) > 20
        or any(
            not isinstance(oid, str) or not _OBS_ID.fullmatch(oid)
            for oid in observation_ids
        )
        or len(observation_ids) != len(set(observation_ids))
    ):
        raise ValueError(
            "observation_ids must be at most 20 unique local observation IDs"
        )
    observations = []
    if observation_ids:
        _tables(workspace)
        marks = ",".join("?" for _ in observation_ids)
        with workspace.connection() as db:
            rows = db.execute(
                f"SELECT * FROM method_observations WHERE observation_id IN ({marks})",
                tuple(observation_ids),
            ).fetchall()
        found = {row["observation_id"]: dict(row) for row in rows}
        missing = [oid for oid in observation_ids if oid not in found]
        if missing:
            raise ValueError(f"Unknown observations: {missing}")
        wrong = [oid for oid in observation_ids if found[oid]["family"] != family]
        if wrong:
            raise ValueError(f"Observations belong to another family: {wrong}")
        observations = [
            {"kind": "operator_observation", "observation": found[oid]}
            for oid in observation_ids
        ]
    sources = [
        {
            **{k: known[sid][k] for k in ("id", "title", "filename", "sha256", "role")},
            "policy": policy[sid],
        }
        for sid in source_ids
    ]
    return {
        "source_ids": list(source_ids),
        "options": {
            **options,
            "source_policy": policy,
            "observation_ids": list(observation_ids),
            "method_family": family,
        },
        "sources": sources,
        "factual_source_ids": factual_ids,
        "form_exemplar_ids": exemplar_ids,
        "observations": observations,
    }
