"""Structural and provenance checks at each learning-stage boundary.

These checks establish traceability and complete assignment of extracted ideas.
They cannot establish that extraction found every idea or that a lesson is true.
"""
from __future__ import annotations

from collections import Counter
import hashlib
from pathlib import PurePath, PureWindowsPath


class ValidationError(ValueError):
    pass


def _object(value: object, label: str) -> dict:
    if not isinstance(value, dict):
        raise ValidationError(f"{label} must be an object")
    return value


def _list(value: object, label: str) -> list:
    if not isinstance(value, list):
        raise ValidationError(f"{label} must be a list")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{label} must be nonempty text")
    return value.strip()


def _fields(row: dict, allowed: set[str], label: str) -> None:
    extra = set(row) - allowed
    if extra:
        raise ValidationError(f"{label} contains unexpected fields: {sorted(extra)}")


def validate_evidence(evidence: object, units_by_id: dict[str, dict], label: str,
                      *, required: bool = True) -> list[dict]:
    rows = _list(evidence, label)
    if required and not rows:
        raise ValidationError(f"{label} needs exact source evidence")
    clean = []
    for i, item in enumerate(rows):
        row = _object(item, f"{label}[{i}]")
        _fields(row, {"unit_id", "quote"}, f"{label}[{i}]")
        unit_id = _text(row.get("unit_id"), f"{label}[{i}].unit_id")
        quote = _text(row.get("quote"), f"{label}[{i}].quote")
        unit = units_by_id.get(unit_id)
        if unit is None:
            raise ValidationError(f"{label}[{i}] names unknown unit {unit_id}")
        if unit.get("role") != "teaching":
            raise ValidationError(f"{label}[{i}] cites held-out assessment unit")
        if quote not in unit.get("text", ""):
            raise ValidationError(f"{label}[{i}] quote is absent from {unit_id}")
        clean.append({"unit_id": unit_id, "quote": quote})
    return clean


def validate_extraction(result: object, unit: dict, units_by_id: dict[str, dict]) -> list[dict]:
    obj = _object(result, "extraction")
    rows = _list(obj.get("concepts"), "extraction.concepts")
    concepts = []
    for i, raw in enumerate(rows, 1):
        row = _object(raw, f"concept {i}")
        evidence = validate_evidence(row.get("evidence"), units_by_id, f"concept {i}.evidence")
        if not any(e["unit_id"] == unit["id"] for e in evidence):
            raise ValidationError("extracted concept lacks evidence from its core unit")
        concepts.append({"id": f"{unit['id']}:c{i}",
                         "title": _text(row.get("title"), f"concept {i}.title"),
                         "explanation": _text(row.get("explanation"), f"concept {i}.explanation"),
                         "evidence": evidence})
    return concepts


def validate_reconcile(result: object, raw_concepts: list[dict], units_by_id: dict[str, dict]) -> list[dict]:
    rows = _list(_object(result, "reconciliation").get("concepts"), "reconciliation.concepts")
    raw = {c["id"]: c for c in raw_concepts}
    owner: Counter[str] = Counter()
    clean = []
    for i, item in enumerate(rows, 1):
        row = _object(item, f"canonical concept {i}")
        members = [_text(x, "member_id") for x in _list(row.get("member_ids"), "member_ids")]
        if not members or len(set(members)) != len(members) or any(x not in raw for x in members):
            raise ValidationError("canonical concept has empty, duplicate, or unknown members")
        owner.update(members)
        evidence = validate_evidence(row.get("evidence"), units_by_id, "canonical evidence")
        allowed = {(e["unit_id"], e["quote"]) for member in members for e in raw[member]["evidence"]}
        present = {(e["unit_id"], e["quote"]) for e in evidence}
        if not present <= allowed:
            raise ValidationError("canonical evidence must come from member concepts")
        if not allowed <= present:
            raise ValidationError("canonical concept dropped member evidence")
        key = "\x1f".join(sorted(members)).encode()
        cid = "cc-" + hashlib.sha256(key).hexdigest()[:20]
        clean.append({"id": cid, "title": _text(row.get("title"), "canonical title"),
                      "explanation": _text(row.get("explanation"), "canonical explanation"),
                      "member_ids": members, "evidence": evidence})
    if set(owner) != set(raw) or any(count != 1 for count in owner.values()):
        raise ValidationError("every raw concept must appear in exactly one canonical concept")
    return clean


def validate_plan(result: object, concepts: list[dict]) -> dict:
    plan = _object(result, "plan")
    _text(plan.get("title"), "plan.title")
    title = plan["title"]
    lessons = _list(plan.get("lessons"), "plan.lessons")
    deferred = _list(plan.get("deferred"), "plan.deferred")
    if not lessons:
        raise ValidationError("plan needs at least one lesson")
    known = {c["id"] for c in concepts}
    usage: Counter[str] = Counter()
    ids: set[str] = set()
    clean_lessons = []
    for i, raw in enumerate(lessons):
        row = _object(raw, f"lesson {i+1}")
        lid = _text(row.get("id"), "lesson.id")
        if lid in ids:
            raise ValidationError(f"duplicate lesson id {lid}")
        cids = [_text(x, "concept_id") for x in _list(row.get("concept_ids"), "lesson.concept_ids")]
        if not cids or len(set(cids)) != len(cids) or any(x not in known for x in cids):
            raise ValidationError(f"lesson {lid} has empty, duplicate, or unknown concepts")
        prereqs = [_text(x, "prerequisite_id") for x in _list(row.get("prerequisite_ids"), "lesson.prerequisite_ids")]
        if len(set(prereqs)) != len(prereqs) or any(x not in ids for x in prereqs):
            raise ValidationError(f"lesson {lid} prerequisites must be earlier lessons")
        ids.add(lid)
        usage.update(cids)
        clean_lessons.append({"id": lid, "title": _text(row.get("title"), "lesson.title"),
                              "concept_ids": cids, "prerequisite_ids": prereqs})
    clean_deferred = []
    for raw in deferred:
        row = _object(raw, "deferred item")
        cid = _text(row.get("concept_id"), "deferred.concept_id")
        if cid not in known:
            raise ValidationError(f"deferred unknown concept {cid}")
        usage[cid] += 1
        clean_deferred.append({"concept_id": cid, "reason": _text(row.get("reason"), "deferred.reason")})
    if set(usage) != known or any(count != 1 for count in usage.values()):
        missing = sorted(known - set(usage))
        repeated = sorted(k for k, count in usage.items() if count != 1)
        raise ValidationError(f"every extracted concept needs one assignment or deferral; missing={missing}, repeated={repeated}")
    return {"title": title, "lessons": clean_lessons, "deferred": clean_deferred}


def validate_lesson(result: object, planned: dict, concepts_by_id: dict[str, dict],
                    units_by_id: dict[str, dict]) -> dict:
    lesson = _object(result, "authored lesson")
    _fields(lesson, {"id", "title", "concept_ids", "summary", "sections", "questions",
                     "audio_script", "scenario", "review"}, "authored lesson")
    if lesson.get("id") != planned["id"] or lesson.get("title") != planned["title"]:
        raise ValidationError("authored lesson identity differs from plan")
    cids = lesson.get("concept_ids")
    if cids != planned["concept_ids"]:
        raise ValidationError("authored lesson concept IDs differ from plan")
    allowed_evidence = {(e["unit_id"], e["quote"]) for cid in cids
                        for e in concepts_by_id[cid]["evidence"]}
    def check_lesson_evidence(value: object, label: str) -> list[dict]:
        checked = validate_evidence(value, units_by_id, label)
        if any((e["unit_id"], e["quote"]) not in allowed_evidence for e in checked):
            raise ValidationError(f"{label} cites evidence outside assigned concepts")
        return checked
    _text(lesson.get("summary"), "lesson.summary")
    sections = _list(lesson.get("sections"), "lesson.sections")
    if not sections:
        raise ValidationError("lesson needs teaching sections")
    anchored: set[tuple[str, str]] = set()
    for i, raw in enumerate(sections):
        section = _object(raw, f"section {i+1}")
        _fields(section, {"heading", "body", "evidence"}, "section")
        _text(section.get("heading"), "section.heading")
        _text(section.get("body"), "section.body")
        for ev in check_lesson_evidence(section.get("evidence"), "section.evidence"):
            anchored.add((ev["unit_id"], ev["quote"]))
    questions = _list(lesson.get("questions"), "lesson.questions")
    qids: set[str] = set()
    for i, raw in enumerate(questions):
        row = _object(raw, f"question {i+1}")
        _fields(row, {"id", "kind", "prompt", "answer", "rationale", "concept_ids",
                      "evidence"}, "question")
        qid = _text(row.get("id"), "question.id")
        if qid in qids:
            raise ValidationError(f"duplicate question ID {qid}")
        qids.add(qid)
        kind = row.get("kind")
        if kind not in {"recall", "contrast", "apply"}:
            raise ValidationError(f"invalid question kind {kind}")
        for key in ("prompt", "answer", "rationale"):
            _text(row.get(key), f"question.{key}")
        refs = _list(row.get("concept_ids"), "question.concept_ids")
        if not refs or any(cid not in cids for cid in refs):
            raise ValidationError(f"question {qid} references unassigned concept")
        for ev in check_lesson_evidence(row.get("evidence"), "question.evidence"):
            anchored.add((ev["unit_id"], ev["quote"]))
    for cid in cids:
        if not any((e["unit_id"], e["quote"]) in anchored for e in concepts_by_id[cid]["evidence"]):
            raise ValidationError(f"lesson misses grounded coverage of objective {cid}")
    scenario = lesson.get("scenario")
    if scenario is not None:
        scenario = _object(scenario, "scenario")
        _fields(scenario, {"title", "candidate_brief", "findings", "decision_prompt",
                           "checklist", "second_event", "reassessment_prompt", "debrief"}, "scenario")
        for key in ("title", "candidate_brief", "decision_prompt", "reassessment_prompt", "debrief"):
            _text(scenario.get(key), f"scenario.{key}")
        findings = _list(scenario.get("findings"), "scenario.findings")
        checklist = _list(scenario.get("checklist"), "scenario.checklist")
        if not findings or not checklist:
            raise ValidationError("scenario needs findings and a decision checklist")
        ids = set()
        for item in findings:
            row = _object(item, "scenario finding")
            _fields(row, {"id", "label", "text", "evidence"}, "scenario finding")
            fid = _text(row.get("id"), "finding.id")
            if fid in ids:
                raise ValidationError("duplicate scenario finding ID")
            ids.add(fid)
            _text(row.get("label"), "finding.label")
            _text(row.get("text"), "finding.text")
            check_lesson_evidence(row.get("evidence"), "finding.evidence")
        ids.clear()
        for item in checklist:
            row = _object(item, "checklist item")
            _fields(row, {"id", "criterion", "evidence"}, "checklist item")
            fid = _text(row.get("id"), "checklist.id")
            if fid in ids:
                raise ValidationError("duplicate checklist ID")
            ids.add(fid)
            _text(row.get("criterion"), "checklist.criterion")
            check_lesson_evidence(row.get("evidence"), "checklist.evidence")
        event = _object(scenario.get("second_event"), "scenario.second_event")
        _fields(event, {"trigger", "text", "evidence"}, "scenario.second_event")
        _text(event.get("trigger"), "second_event.trigger")
        _text(event.get("text"), "second_event.text")
        check_lesson_evidence(event.get("evidence"), "second_event.evidence")
    audio = _list(lesson.get("audio_script"), "lesson.audio_script")
    if not audio:
        raise ValidationError("lesson needs a speakable script")
    for row in audio:
        item = _object(row, "audio turn")
        _fields(item, {"kind", "text"}, "audio turn")
        if item.get("kind") not in {"speech", "pause"}:
            raise ValidationError("audio kind must be speech or pause")
        _text(item.get("text"), "audio turn.text")
    return lesson


def validate_review(result: object) -> dict:
    row = _object(result, "review")
    _fields(row, {"status", "issues"}, "review")
    if row.get("status") not in {"pass", "revise"}:
        raise ValidationError("review status must be pass or revise")
    issues = _list(row.get("issues"), "review.issues")
    for issue in issues:
        issue = _object(issue, "review issue")
        _fields(issue, {"detail"}, "review issue")
        _text(issue.get("detail"), "review issue.detail")
    if row["status"] == "pass" and issues:
        raise ValidationError("passing review cannot contain issues")
    if row["status"] == "revise" and not issues:
        raise ValidationError("revise review must explain what needs work")
    return row


def validate_bundle(bundle: object) -> dict:
    """Recheck a loaded bundle before static export.

    This checks internal provenance, not possession or truth of original files.
    A maliciously replaced bundle and matching source text require an external
    signature or trusted source copy to detect; those are outside this format.
    """
    doc = _object(bundle, "bundle")
    _fields(doc, {"schema_version", "title", "description", "sources", "units",
                  "raw_concepts", "concepts", "lessons", "plan", "counters",
                  "build", "downloads"}, "bundle")
    if doc.get("schema_version") != "1.0":
        raise ValidationError("unsupported bundle schema version")
    _text(doc.get("title"), "bundle.title")
    _text(doc.get("description"), "bundle.description")
    sources = _list(doc.get("sources"), "bundle.sources")
    units = _list(doc.get("units"), "bundle.units")
    raw_concepts = _list(doc.get("raw_concepts"), "bundle.raw_concepts")
    concepts = _list(doc.get("concepts"), "bundle.concepts")
    lessons = _list(doc.get("lessons"), "bundle.lessons")
    if not sources or not units or not raw_concepts or not concepts:
        raise ValidationError("bundle is missing teaching sources, units, or concepts")
    source_ids: set[str] = set()
    for source in sources:
        row = _object(source, "source")
        _fields(row, {"id", "title", "filename", "sha256", "role"}, "source")
        sid = _text(row.get("id"), "source.id")
        if sid in source_ids:
            raise ValidationError("duplicate source ID")
        source_ids.add(sid)
        if row.get("role") != "teaching":
            raise ValidationError("bundle contains a held-out assessment source")
        name = _text(row.get("filename"), "source.filename")
        if (PurePath(name).name != name or PureWindowsPath(name).name != name
                or name in {".", ".."}):
            raise ValidationError("source filename must be a basename")
        _text(row.get("title"), "source.title")
        digest = _text(row.get("sha256"), "source.sha256")
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest.lower()):
            raise ValidationError("source.sha256 must be a hex digest")
    units_by_id: dict[str, dict] = {}
    for unit in units:
        row = _object(unit, "unit")
        _fields(row, {"id", "source_id", "heading", "text", "locator", "ordinal", "role"}, "unit")
        uid = _text(row.get("id"), "unit.id")
        if uid in units_by_id:
            raise ValidationError("duplicate unit ID")
        if row.get("source_id") not in source_ids or row.get("role") != "teaching":
            raise ValidationError("unit has unknown or held-out source role")
        _text(row.get("text"), "unit.text")
        _text(row.get("heading"), "unit.heading")
        _text(row.get("locator"), "unit.locator")
        if not isinstance(row.get("ordinal"), int) or row["ordinal"] < 0:
            raise ValidationError("unit.ordinal must be a nonnegative integer")
        units_by_id[uid] = row
    raw_ids = set()
    for raw in raw_concepts:
        row = _object(raw, "raw concept")
        _fields(row, {"id", "title", "explanation", "evidence"}, "raw concept")
        cid = _text(row.get("id"), "raw concept.id")
        if cid in raw_ids:
            raise ValidationError("duplicate raw concept ID")
        raw_ids.add(cid)
        _text(row.get("title"), "raw concept.title")
        _text(row.get("explanation"), "raw concept.explanation")
        validate_evidence(row.get("evidence"), units_by_id, "raw concept.evidence")
    expected = validate_reconcile({"concepts": concepts}, raw_concepts, units_by_id)
    if expected != concepts:
        raise ValidationError("canonical concepts were modified after reconciliation")
    plan = validate_plan(doc.get("plan"), concepts)
    if plan != doc.get("plan"):
        raise ValidationError("plan differs from validated shape")
    if doc.get("title") != plan["title"]:
        raise ValidationError("bundle title differs from plan")
    by_id = {c["id"]: c for c in concepts}
    if len(lessons) != len(plan["lessons"]):
        raise ValidationError("lesson count differs from plan")
    for lesson, planned in zip(lessons, plan["lessons"]):
        validate_lesson(lesson, planned, by_id, units_by_id)
        if validate_review(lesson.get("review"))["status"] != "pass":
            raise ValidationError("unresolved lesson review blocks export")
    counters = _object(doc.get("counters"), "bundle.counters")
    _fields(counters, {"teaching_sources", "teaching_units", "extracted_concepts",
                       "canonical_concepts", "assigned_concepts", "deferred_concepts",
                       "lessons", "workspace"}, "bundle.counters")
    expected_counts = {
        "teaching_sources": len(sources), "teaching_units": len(units),
        "extracted_concepts": len(raw_concepts), "canonical_concepts": len(concepts),
        "assigned_concepts": sum(len(x["concept_ids"]) for x in plan["lessons"]),
        "deferred_concepts": len(plan["deferred"]), "lessons": len(lessons),
    }
    for key, expected_count in expected_counts.items():
        if type(counters.get(key)) is not int or counters[key] != expected_count:
            raise ValidationError(f"bundle.counters.{key} disagrees with validated content")
    workspace = _object(counters.get("workspace"), "bundle.counters.workspace")
    _fields(workspace, {"sources", "units", "teaching_units", "assessment_units",
                        "jobs", "attempts"}, "bundle.counters.workspace")
    for key, value in workspace.items():
        if key == "jobs":
            jobs = _object(value, "bundle.counters.workspace.jobs")
            _fields(jobs, {"queued", "running", "completed", "failed"}, "bundle.counters.workspace.jobs")
            for status, count in jobs.items():
                if type(count) is not int or count < 0:
                    raise ValidationError(f"workspace jobs.{status} must be a nonnegative integer")
        elif type(value) is not int or value < 0:
            raise ValidationError(f"workspace.{key} must be a nonnegative integer")
    build = _object(doc.get("build"), "bundle.build")
    _fields(build, {"provider", "review_mode", "review_scope", "coverage_scope",
                    "assessment_boundary", "audio_scope"}, "bundle.build")
    for key in ("provider", "review_scope", "coverage_scope", "assessment_boundary", "audio_scope"):
        _text(build.get(key), f"bundle.build.{key}")
    if build.get("review_mode") not in {"curated_fixture", "configured_adapter"}:
        raise ValidationError("bundle.build.review_mode is invalid")
    if "downloads" in doc:
        downloads = _object(doc["downloads"], "bundle.downloads")
        _fields(downloads, {"markdown", "pdf"}, "bundle.downloads")
        if downloads.get("markdown") != "study-guide.md":
            raise ValidationError("bundle.downloads.markdown must name the generated study guide")
        if "pdf" in downloads and downloads["pdf"] != "study-guide.pdf":
            raise ValidationError("bundle.downloads.pdf must name the generated PDF")
    return doc
