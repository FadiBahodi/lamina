"""Source-linked, portable lesson exports from an already validated bundle.

The printable routes preserve the question/answer separation. They do not
infer correctness, generate new content, or synthesize audio.
"""

from __future__ import annotations

from html import escape
from pathlib import Path

from .validation import validate_bundle


def _bundle_parts(bundle: dict) -> tuple[list[dict], dict[str, dict], dict[str, dict]]:
    validate_bundle(bundle)
    lessons = bundle["lessons"]
    sources = bundle["sources"]
    units = bundle["units"]
    source_by_id = {row["id"]: row for row in sources}
    unit_by_id = {row["id"]: row for row in units}
    return lessons, source_by_id, unit_by_id


def _source_label(evidence: dict, sources: dict[str, dict], units: dict[str, dict]) -> str:
    unit_id = evidence.get("unit_id", "")
    unit = units.get(unit_id)
    if unit is None:
        raise ValueError(f"Evidence names unknown unit {unit_id}")
    source = sources.get(unit["source_id"])
    if source is None:
        raise ValueError(f"Unit {unit_id} names an unknown source")
    quote = evidence.get("quote", "")
    if not quote or quote not in unit.get("text", ""):
        raise ValueError(f"Evidence quote is absent from unit {unit_id}")
    return f"{source['filename']} · {unit['locator']} · {unit_id}"


def _evidence_labels(evidence: list[dict], sources: dict[str, dict], units: dict[str, dict]) -> list[str]:
    return list(dict.fromkeys(_source_label(row, sources, units) for row in evidence))


def export_markdown(bundle: dict, output: Path) -> None:
    """Write a dependency-free handout with a separate answer key."""
    lessons, sources, units = _bundle_parts(bundle)
    title = str(bundle.get("title") or "Learning route")
    lines = [f"# {title}", "", "A source-linked study route. Try the questions before opening the answer key.",
             "", "## Contents", ""]
    for index, lesson in enumerate(lessons, 1):
        lines.append(f"{index}. {lesson['title']}")
    lines.extend(["", "## Lessons", ""])
    for index, lesson in enumerate(lessons, 1):
        lines.extend([f"### {index}. {lesson['title']}", "", lesson.get("summary", ""), ""])
        for section in lesson.get("sections", []):
            lines.extend([f"#### {section['heading']}", "", section["body"], ""])
            refs = _evidence_labels(section.get("evidence", []), sources, units)
            if refs:
                lines.extend(["Source: " + "; ".join(refs), ""])
        lines.extend(["#### Practice", "", "Answer these before turning to the answer key.", ""])
        for qindex, question in enumerate(lesson.get("questions", []), 1):
            lines.extend([f"{index}.{qindex} **{question['kind'].title()}** — {question['prompt']}", ""])
        scenario = lesson.get("scenario")
        if scenario:
            lines.extend(["#### Scenario · candidate brief", "", scenario["candidate_brief"], "",
                          f"First decision: {scenario['decision_prompt']}", ""])
    lines.extend(["\n---\n", "## Answer key", ""])
    for index, lesson in enumerate(lessons, 1):
        lines.extend([f"### {index}. {lesson['title']}", ""])
        for qindex, question in enumerate(lesson.get("questions", []), 1):
            lines.extend([f"**{index}.{qindex} · {question['kind'].title()}**", "",
                          question["answer"], "", f"Why: {question['rationale']}", ""])
            refs = _evidence_labels(question.get("evidence", []), sources, units)
            if refs:
                lines.extend(["Source: " + "; ".join(refs), ""])
        scenario = lesson.get("scenario")
        if scenario:
            lines.extend(["#### Scenario · examiner notes", "", "Release findings when requested:", ""])
            for finding in scenario.get("findings", []):
                refs = _evidence_labels(finding.get("evidence", []), sources, units)
                lines.extend([f"- **{finding['label']}:** {finding['text']}",
                              "  Source: " + "; ".join(refs)])
            event = scenario["second_event"]
            lines.extend(["", f"Second event ({event['trigger']}): {event['text']}",
                          "Source: " + "; ".join(_evidence_labels(event.get("evidence", []), sources, units)),
                          "", f"Reassess: {scenario['reassessment_prompt']}", "",
                          "Discussion checklist:", ""])
            for item in scenario.get("checklist", []):
                refs = _evidence_labels(item.get("evidence", []), sources, units)
                lines.extend([f"- [ ] {item['criterion']}", "  Source: " + "; ".join(refs)])
            lines.extend(["", "Debrief: " + scenario["debrief"], ""])
    lines.extend(["## Listen scripts", "", "These are authored scripts with pauses, not synthesized or audited audio.", ""])
    for index, lesson in enumerate(lessons, 1):
        lines.extend([f"### {index}. {lesson['title']}", ""])
        for turn in lesson.get("audio_script", []):
            lines.extend([f"**{turn['kind'].title()}:** {turn['text']}", ""])
    lines.extend(["## Source ledger", ""])
    for source in sources.values():
        lines.extend([f"- **{source['title']}** — {source['filename']} (`{source['id']}`)"])
        for unit in units.values():
            if unit["source_id"] == source["id"]:
                lines.append(f"  - {unit['locator']} · `{unit['id']}` · {unit['heading']}")
    lines.extend(["", "## Scope", "", "Coverage accounts for extracted concepts that were assigned or deferred; it does not prove complete extraction or learning effectiveness. The Listen lane is a script, not synthesized audio.", ""])
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")


def export_pdf(bundle: dict, output: Path) -> None:
    """Write a paginated study book with practice and answer sections."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.platypus import BaseDocTemplate, Frame, KeepTogether, PageBreak, PageTemplate, Paragraph, Spacer
    except ImportError as exc:
        raise RuntimeError('PDF export requires the optional dependency: pip install "lamina-engine[pdf]"') from exc

    lessons, sources, units = _bundle_parts(bundle)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    page_w, page_h = A4
    ink = colors.HexColor("#19323B")
    muted = colors.HexColor("#617077")
    accent = colors.HexColor("#087D82")
    paper = colors.HexColor("#FAF8F3")
    line = colors.HexColor("#D6DFDD")
    styles = {
        "eyebrow": ParagraphStyle("eyebrow", fontName="Helvetica-Bold", fontSize=8, leading=12, textColor=accent, spaceAfter=13),
        "title": ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=30, leading=36, textColor=ink, spaceAfter=16),
        "deck": ParagraphStyle("deck", fontName="Helvetica", fontSize=12, leading=18, textColor=muted, spaceAfter=20),
        "h1": ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=19, leading=24, textColor=ink, spaceBefore=15, spaceAfter=10),
        "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=11, leading=16, textColor=accent, spaceBefore=13, spaceAfter=6),
        "body": ParagraphStyle("body", fontName="Helvetica", fontSize=9.5, leading=15, textColor=ink, spaceAfter=9),
        "small": ParagraphStyle("small", fontName="Helvetica", fontSize=7.5, leading=11, textColor=muted, spaceAfter=7),
        "q": ParagraphStyle("question", fontName="Helvetica-Bold", fontSize=10, leading=15, textColor=ink, spaceBefore=10, spaceAfter=7),
    }

    class Book(BaseDocTemplate):
        def __init__(self, path: Path):
            super().__init__(str(path), pagesize=A4, leftMargin=50, rightMargin=50,
                             topMargin=64, bottomMargin=54, title=str(bundle.get("title") or "Learning route"),
                             author="Fadi Bahodi")
            frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="content", showBoundary=0)
            self.addPageTemplates(PageTemplate(id="main", frames=frame, onPage=self.decorate))

        def decorate(self, canvas, doc):
            canvas.saveState()
            canvas.setFillColor(paper)
            canvas.rect(0, 0, page_w, page_h, fill=1, stroke=0)
            canvas.setStrokeColor(line)
            canvas.line(50, page_h - 43, page_w - 50, page_h - 43)
            canvas.line(50, 39, page_w - 50, 39)
            canvas.setFont("Helvetica-Bold", 8)
            canvas.setFillColor(accent)
            canvas.drawString(50, page_h - 32, "LAMINA  /  STUDY ROUTE")
            canvas.setFont("Helvetica", 8)
            canvas.setFillColor(muted)
            canvas.drawRightString(page_w - 50, 25, f"{doc.page}")
            canvas.restoreState()

    def p(value: object, kind: str = "body"):
        return Paragraph(escape(str(value or "")).replace("\n", "<br/>"), styles[kind])

    story = [Spacer(1, 44), p("SOURCE-LINKED LEARNING", "eyebrow"),
             p(bundle.get("title") or "Learning route", "title"),
             p("Read the lesson. Retrieve before revealing. Trace the answer to its source.", "deck"),
             p(f"{len(lessons)} lessons  ·  {len(bundle.get('concepts') or [])} canonical concepts  ·  {len(sources)} teaching sources", "body"),
             Spacer(1, 24), p("About this book", "h2"),
             p("Practice prompts and answers live in separate sections. Source notes identify the exact unit used for each teaching section and answer. Coverage means extracted concepts were accounted for; it does not establish that extraction was complete or that learning improved."),
             PageBreak(), p("Contents", "h1")]
    for index, lesson in enumerate(lessons, 1):
        story.append(p(f"{index:02d}   {lesson['title']}", "body"))
    story.extend([p("Answer key", "body"), p("Source ledger", "body"), PageBreak()])
    for index, lesson in enumerate(lessons, 1):
        story.extend([p(f"LESSON {index:02d}", "eyebrow"), p(lesson["title"], "h1"), p(lesson.get("summary", ""), "deck")])
        for section in lesson.get("sections", []):
            refs = _evidence_labels(section.get("evidence", []), sources, units)
            story.extend([p(section["heading"], "h2"), p(section["body"]), p("Source: " + "; ".join(refs), "small")])
        story.extend([p("Practice · answer before turning to the key", "h2")])
        for qindex, question in enumerate(lesson.get("questions", []), 1):
            story.append(KeepTogether([p(f"{index}.{qindex}  {question['kind'].upper()}", "small"),
                                       p(question["prompt"], "q"), Spacer(1, 27)]))
        scenario = lesson.get("scenario")
        if scenario:
            story.extend([p("Scenario · candidate brief", "h2"), p(scenario["candidate_brief"]),
                          p("First decision: " + scenario["decision_prompt"], "q")])
        story.append(PageBreak())
    story.extend([p("Answer key", "h1"), p("Use your answer, then inspect the rationale and source pointer.", "deck")])
    for index, lesson in enumerate(lessons, 1):
        story.extend([p(f"{index:02d}  {lesson['title']}", "h2")])
        for qindex, question in enumerate(lesson.get("questions", []), 1):
            refs = _evidence_labels(question.get("evidence", []), sources, units)
            story.extend([p(f"{index}.{qindex}  {question['kind'].upper()}  ·  {question['prompt']}", "q"),
                          p(question["answer"]), p("Why: " + question["rationale"], "small"),
                          p("Source: " + "; ".join(refs), "small")])
        scenario = lesson.get("scenario")
        if scenario:
            story.extend([p("Scenario · examiner notes", "h2"), p("Release findings when requested.", "small")])
            for finding in scenario.get("findings", []):
                refs = _evidence_labels(finding.get("evidence", []), sources, units)
                story.extend([p(finding["label"], "q"), p(finding["text"]),
                              p("Source: " + "; ".join(refs), "small")])
            event = scenario["second_event"]
            story.extend([p("Second event · " + event["trigger"], "q"), p(event["text"]),
                          p("Source: " + "; ".join(_evidence_labels(event.get("evidence", []), sources, units)), "small"),
                          p("Reassess: " + scenario["reassessment_prompt"], "body"),
                          p("Discussion checklist", "h2")])
            for item in scenario.get("checklist", []):
                story.extend([p("[ ]  " + item["criterion"], "body"),
                              p("Source: " + "; ".join(_evidence_labels(item.get("evidence", []), sources, units)), "small")])
            story.extend([p("Debrief", "h2"), p(scenario["debrief"])])
    story.extend([PageBreak(), p("Listen scripts", "h1"),
                  p("Authored speech and pause cues only. No audio was synthesized or audited.", "deck")])
    for index, lesson in enumerate(lessons, 1):
        story.append(p(f"{index:02d}  {lesson['title']}", "h2"))
        for turn in lesson.get("audio_script", []):
            story.append(p(f"{turn['kind'].title()}: {turn['text']}"))
    story.extend([PageBreak(), p("Source ledger", "h1"),
                  p("Document names and locators are preserved from the ingested teaching sources.", "deck")])
    for source in sources.values():
        story.append(p(f"{source['title']}  ·  {source['filename']}", "h2"))
        for unit in units.values():
            if unit["source_id"] == source["id"]:
                story.append(p(f"{unit['locator']}  ·  {unit['id']}  ·  {unit['heading']}", "small"))
    Book(output).build(story)
