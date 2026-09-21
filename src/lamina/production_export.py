"""Export source-aware production artifacts without executing authored markup."""

from __future__ import annotations
import html
import json
import re
from pathlib import Path


def document_html(markdown: str, title: str) -> str:
    blocks = []
    fenced = False
    for line in markdown.splitlines():
        if line.startswith("```"):
            blocks.append("</code></pre>" if fenced else "<pre><code>")
            fenced = not fenced
            continue
        escaped = html.escape(line)
        if fenced:
            blocks.append(escaped + "\n")
            continue
        heading = re.match(r"^(#{1,4})\s+(.+)", line)
        if heading:
            level = len(heading[1])
            blocks.append(f"<h{level}>{html.escape(heading[2])}</h{level}>")
        elif line.strip():
            blocks.append("<p>" + escaped + "</p>")
    if fenced:
        blocks.append("</code></pre>")
    return (
        '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'
        + html.escape(title)
        + "</title><style>body{margin:0;background:#f5f7f7;color:#17232b;font:17px/1.65 system-ui,sans-serif}main{max-width:850px;margin:40px auto;padding:40px;background:white}h1,h2,h3{line-height:1.2}p{white-space:pre-wrap}pre{overflow:auto;background:#edf3f6;padding:20px}header{font:12px monospace;color:#196c91;letter-spacing:.1em}@media(max-width:600px){main{padding:22px;margin:0}}</style><main><header>LAMINA / FINISHED DOCUMENT</header>"
        + "".join(blocks)
        + "</main></html>"
    )


def export_production(receipt: dict, plan: dict, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    markdown = receipt.get("markdown", "")
    if not isinstance(markdown, str):
        raise ValueError("production markdown must be text")
    (output / "document.md").write_text(markdown, encoding="utf-8")
    (output / "index.html").write_text(
        document_html(
            markdown, receipt.get("title", plan.get("title", "Lamina document"))
        ),
        encoding="utf-8",
    )
    for filename, value in [("report.json", receipt), ("plan.json", plan)]:
        (output / filename).write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    links = {
        "document": "document.md",
        "reader": "index.html",
        "report": "report.json",
        "plan": "plan.json",
    }
    for key in ("candidate_markdown", "examiner_markdown"):
        if isinstance(receipt.get(key), str) and receipt[key]:
            name = key.removesuffix("_markdown")
            (output / f"{name}.md").write_text(receipt[key], encoding="utf-8")
            (output / f"{name}.html").write_text(
                document_html(receipt[key], name.title()), encoding="utf-8"
            )
            links[name] = f"{name}.html"
    try:
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    except ImportError:
        return links
    styles = getSampleStyleSheet()
    story = []
    for line in markdown.splitlines():
        line = line.strip()
        if not line:
            continue
        level = len(line) - len(line.lstrip("#"))
        style = styles[
            "Heading1" if level == 1 else "Heading2" if level else "BodyText"
        ]
        story.append(Paragraph(html.escape(line.lstrip("#").strip()), style))
        story.append(Spacer(1, 5))
    if story:
        SimpleDocTemplate(
            str(output / "document.pdf"),
            title=receipt.get("title", "Lamina document"),
            author="",
        ).build(story)
        links["pdf"] = "document.pdf"
    return links
