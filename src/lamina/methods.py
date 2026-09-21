"""Validate portable, data-only work methods.

A method describes work and dependencies. The operator supplies the adapter;
method JSON has no control field for selecting a program, endpoint, or model.
"""
from __future__ import annotations

import re

from .store import canonical

_ID = re.compile(r"[a-z][a-z0-9-]{0,63}\Z")
_VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
_OBSERVATION_ID = re.compile(r"[0-9a-f]{32}\Z")


def _text(value: object, name: str, maximum: int = 4000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or "\x00" in value:
        raise ValueError(f"{name} must be nonempty text of at most {maximum} characters")
    return value.strip()


def _id(value: object, name: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError(f"{name} must be a lowercase slug")
    return value


def validate_method(value: dict) -> dict:
    """Return a canonical v1 method, rejecting ambiguous graphs/resources.

    This validates data shape. It is not a sandbox for the operator's adapter,
    and reference text may contain links, paths, or technical terminology.
    """
    if not isinstance(value, dict):
        raise ValueError("method must be an object")
    fields = {"schema_version", "family", "id", "version", "description", "applicability", "resources", "nodes"}
    if set(value) != fields or value["schema_version"] != "1":
        raise ValueError("method needs exactly the v1 fields")
    method = {"schema_version": "1", "family": _id(value["family"], "family"),
              "id": _id(value["id"], "id")}
    if not isinstance(value["version"], str) or not _VERSION.fullmatch(value["version"]):
        raise ValueError("version must be a short version token")
    method["version"] = value["version"]
    method["description"] = _text(value["description"], "description", 500)
    applicability = value["applicability"]
    if not isinstance(applicability, dict) or set(applicability) != {"contexts", "exclusions", "limits"}:
        raise ValueError("applicability needs contexts, exclusions, and limits")
    method["applicability"] = {}
    for key in ("contexts", "exclusions", "limits"):
        items = applicability[key]
        if not isinstance(items, list) or len(items) > 20 or (key == "contexts" and not items):
            raise ValueError(f"applicability.{key} must be a bounded list")
        method["applicability"][key] = [_text(x, f"applicability.{key}", 300) for x in items]
    resources = value["resources"]
    if not isinstance(resources, dict) or set(resources) != {"workers", "lanes"}:
        raise ValueError("resources needs workers and lanes")
    workers, lanes = resources["workers"], resources["lanes"]
    if type(workers) is not int or not 1 <= workers <= 32:
        raise ValueError("workers must be 1..32")
    if not isinstance(lanes, dict) or not lanes or len(lanes) > 16:
        raise ValueError("lanes must be a nonempty bounded object")
    clean_lanes = {}
    for lane, capacity in lanes.items():
        _id(lane, "lane")
        if type(capacity) is not int or not 1 <= capacity <= workers:
            raise ValueError("lane capacity must be 1..workers")
        clean_lanes[lane] = capacity
    method["resources"] = {"workers": workers, "lanes": dict(sorted(clean_lanes.items()))}
    nodes = value["nodes"]
    if not isinstance(nodes, list) or not 1 <= len(nodes) <= 64:
        raise ValueError("nodes must contain 1..64 entries")
    clean_nodes, seen = [], set()
    for raw in nodes:
        required = {"id", "role", "instructions", "lane", "depends_on", "input"}
        if not isinstance(raw, dict) or not required <= set(raw) or set(raw) - required - {"task_keys", "expected_shape", "observation_ids"}:
            raise ValueError("each node needs id, role, instructions, lane, depends_on, input; task_keys, expected_shape, and observation_ids are optional")
        nid = _id(raw["id"], "node.id")
        if nid in seen:
            raise ValueError(f"duplicate node id: {nid}")
        seen.add(nid)
        lane = _id(raw["lane"], "node.lane")
        if lane not in clean_lanes:
            raise ValueError(f"unknown lane: {lane}")
        deps = raw["depends_on"]
        if not isinstance(deps, list) or any(not isinstance(d, str) for d in deps) or len(deps) != len(set(deps)):
            raise ValueError(f"{nid} has invalid or duplicate dependencies")
        if not isinstance(raw["input"], dict):
            raise ValueError(f"{nid}.input must be an object")
        canonical(raw["input"])  # JSON serializability and finite numbers.
        expected_shape = raw.get("expected_shape", {"result": "str"})
        if not isinstance(expected_shape, dict) or not expected_shape or len(canonical(expected_shape)) > 4000:
            raise ValueError(f"{nid}.expected_shape must be a small JSON object")
        task_keys = raw.get("task_keys")
        if task_keys is not None and (not isinstance(task_keys, list) or len(task_keys) > 64 or
                                      any(not isinstance(key, str) or not key or len(key) > 100 for key in task_keys)):
            raise ValueError(f"{nid}.task_keys must be a unique list of top-level task keys")
        if task_keys is not None and len(task_keys) != len(set(task_keys)):
            raise ValueError(f"{nid}.task_keys has duplicates")
        observation_ids = raw.get("observation_ids", [])
        if (not isinstance(observation_ids, list) or len(observation_ids) > 20 or
            any(not isinstance(oid, str) or not _OBSERVATION_ID.fullmatch(oid) for oid in observation_ids) or
            len(observation_ids) != len(set(observation_ids))):
            raise ValueError(f"{nid}.observation_ids must be unique local observation IDs (at most 20)")
        clean_nodes.append({"id": nid, "role": _text(raw["role"], f"{nid}.role", 160),
                            "instructions": _text(raw["instructions"], f"{nid}.instructions"),
                            "lane": lane, "depends_on": deps, "input": raw["input"],
                            "task_keys": task_keys, "expected_shape": expected_shape,
                            "observation_ids": observation_ids})
    for node in clean_nodes:
        if any(dep not in seen for dep in node["depends_on"]):
            raise ValueError(f"{node['id']} has an unknown dependency")
    pending = {n["id"]: set(n["depends_on"]) for n in clean_nodes}
    reached = set()
    while pending:
        ready = {n for n, deps in pending.items() if deps <= reached}
        if not ready:
            raise ValueError("method dependency graph has a cycle")
        reached |= ready
        for n in ready:
            del pending[n]
    method["nodes"] = clean_nodes
    return method
