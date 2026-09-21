"""Readable, inert artifact exports from the same authored Markdown."""

from __future__ import annotations

import html
import json
from pathlib import Path
from markdown_it import MarkdownIt


def _parser():
    parser = MarkdownIt("commonmark", {"html": False}).enable("table")
    # Image references remain visible; exporting text is not image verification.
    parser.add_render_rule(
        "image",
        lambda self, tokens, idx, options, env: '<span class="media-reference">[Image reference: '
        + html.escape(tokens[idx].content)
        + "]</span>",
    )
    return parser


def document_html(markdown: str, title: str) -> str:
    parser = _parser()
    tokens = parser.parse(markdown)
    toc = []
    for i, token in enumerate(tokens):
        if token.type == "heading_open":
            anchor = f"section-{len(toc)+1}"
            token.attrSet("id", anchor)
            text = tokens[i + 1].content
            toc.append((anchor, text, token.tag))
    body = parser.renderer.render(tokens, parser.options, {})
    links = "".join(
        f'<a href="#{anchor}" class="toc-{level}">{html.escape(text)}</a>'
        for anchor, text, level in toc
    )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>
<style>:root{{color-scheme:light}}*{{box-sizing:border-box}}body{{margin:0;background:#f4f7f8;color:#1b2931;font:17px/1.7 system-ui,sans-serif}}header{{background:#10171c;color:#f4f7f8;padding:20px 5vw;font:12px monospace;letter-spacing:.12em}}.layout{{display:grid;grid-template-columns:230px minmax(0,850px);gap:40px;max-width:1180px;margin:40px auto;padding:0 24px}}nav{{position:sticky;top:25px;align-self:start;max-height:90vh;overflow:auto;font-size:13px}}nav a{{display:block;padding:6px 10px;color:#415866;text-decoration:none;border-left:2px solid #d2dee4}}nav a:hover{{border-color:#237795;background:#e7eff2}}.toc-h1{{font-weight:700}}main{{background:white;padding:40px 44px;border:1px solid #dce3e7;min-width:0}}h1,h2,h3,h4{{line-height:1.2;scroll-margin-top:25px}}h1{{font-size:34px;letter-spacing:-.03em}}h2{{margin-top:1.8em;font-size:25px}}p,li{{overflow-wrap:anywhere}}a{{color:#176784}}pre{{background:#eef3f5;padding:18px;overflow:auto;font:13px/1.6 monospace}}code{{font-size:.88em}}table{{border-collapse:collapse;width:100%;font-size:14px;margin:24px 0}}th,td{{border-bottom:1px solid #d9e2e7;padding:10px;text-align:left;overflow-wrap:anywhere}}th{{background:#edf4f7}}blockquote{{border-left:3px solid #72a3b8;margin:20px 0;padding:4px 20px;color:#48606d}}.media-reference{{color:#725528}}@media(max-width:760px){{.layout{{display:block;margin:20px auto;padding:0 14px}}nav{{position:static;max-height:180px;margin-bottom:20px}}main{{padding:24px}}h1{{font-size:28px}}}}@media print{{header,nav{{display:none}}.layout{{display:block;margin:0;padding:0}}main{{border:0;padding:0}}body{{background:white}}pre{{white-space:pre-wrap}}table{{break-inside:auto}}tr{{break-inside:avoid}}}}</style></head>
<body><header>LAMINA / DOCUMENT</header><div class="layout"><nav aria-label="Document sections">{links}</nav><main>{body}</main></div></body></html>"""


def _inline_pdf(children):
    out = []
    for token in children or []:
        if token.type in {"text", "html_inline"}:
            out.append(html.escape(token.content))
        elif token.type in {"softbreak", "hardbreak"}:
            out.append("<br/>" if token.type == "hardbreak" else " ")
        elif token.type == "code_inline":
            out.append(
                '<font name="LaminaMono">' + html.escape(token.content) + "</font>"
            )
        elif token.type == "strong_open":
            out.append("<b>")
        elif token.type == "strong_close":
            out.append("</b>")
        elif token.type == "em_open":
            out.append("<i>")
        elif token.type == "em_close":
            out.append("</i>")
        elif token.type == "image":
            out.append("[Image reference: " + html.escape(token.content) + "]")
    return "".join(out)


def _pdf(markdown: str, title: str, path: Path):
    from reportlab import __file__ as reportlab_file
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        SimpleDocTemplate,
        Paragraph,
        Spacer,
        Preformatted,
        Table,
        TableStyle,
    )

    fonts = Path(reportlab_file).parent / "fonts"
    for name, file in [
        ("Lamina", "Vera.ttf"),
        ("LaminaBold", "VeraBd.ttf"),
        ("LaminaItalic", "VeraIt.ttf"),
        ("LaminaMono", "Vera.ttf"),
    ]:
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(fonts / file)))
    pdfmetrics.registerFontFamily(
        "Lamina",
        normal="Lamina",
        bold="LaminaBold",
        italic="LaminaItalic",
        boldItalic="LaminaBold",
    )
    body = ParagraphStyle(
        "Body",
        fontName="Lamina",
        fontSize=10,
        leading=15,
        spaceAfter=8,
        textColor=colors.HexColor("#1b2931"),
    )
    headings = {
        f"h{n}": ParagraphStyle(
            f"H{n}",
            parent=body,
            fontName="LaminaBold",
            fontSize=22 if n == 1 else 16 if n == 2 else 12,
            leading=28 if n == 1 else 21 if n == 2 else 17,
            spaceBefore=16,
            spaceAfter=10,
            keepWithNext=True,
        )
        for n in range(1, 7)
    }
    cell = ParagraphStyle("Cell", parent=body, fontSize=8, leading=11, spaceAfter=0)
    code = ParagraphStyle(
        "Code",
        parent=body,
        fontName="LaminaMono",
        fontSize=8,
        leading=11,
        backColor=colors.HexColor("#edf3f5"),
        spaceBefore=8,
        spaceAfter=10,
    )
    tokens = _parser().parse(markdown)
    story = []
    i = 0
    lists = []
    in_item = False
    while i < len(tokens):
        t = tokens[i]
        if t.type == "table_open":
            rows = []
            row = []
            i += 1
            while i < len(tokens) and tokens[i].type != "table_close":
                current = tokens[i]
                if current.type == "tr_open":
                    row = []
                elif current.type == "inline":
                    row.append(Paragraph(_inline_pdf(current.children), cell))
                elif current.type == "tr_close":
                    rows.append(row)
                i += 1
            if rows:
                cols = max(len(r) for r in rows)
                for r in rows:
                    r.extend([""] * (cols - len(r)))
                table = Table(
                    rows,
                    colWidths=[480 / cols] * cols,
                    repeatRows=1,
                    hAlign="LEFT",
                    splitByRow=1,
                    splitInRow=1,
                )
                table.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e7f0f4")),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            (
                                "LINEBELOW",
                                (0, 0),
                                (-1, -1),
                                0.3,
                                colors.HexColor("#d0dde4"),
                            ),
                            ("LEFTPADDING", (0, 0), (-1, -1), 7),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                            ("TOPPADDING", (0, 0), (-1, -1), 7),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                        ]
                    )
                )
                story.extend([table, Spacer(1, 12)])
        elif t.type in {"bullet_list_open", "ordered_list_open"}:
            lists.append(
                {
                    "ordered": t.type == "ordered_list_open",
                    "number": int(t.attrGet("start") or 1),
                }
            )
        elif t.type in {"bullet_list_close", "ordered_list_close"}:
            lists.pop()
        elif t.type == "list_item_open":
            in_item = True
        elif t.type == "heading_open":
            story.append(
                Paragraph(_inline_pdf(tokens[i + 1].children), headings[t.tag])
            )
            i += 2
        elif t.type == "inline":
            prefix = ""
            if in_item and lists:
                item = lists[-1]
                prefix = str(item["number"]) + ". " if item["ordered"] else "• "
                item["number"] += 1
                in_item = False
            style = (
                ParagraphStyle("Indented", parent=body, leftIndent=14 * len(lists))
                if lists
                else body
            )
            story.append(
                Paragraph(html.escape(prefix) + _inline_pdf(t.children), style)
            )
        elif t.type in {"fence", "code_block"}:
            story.append(Preformatted(t.content.rstrip(), code, maxLineLength=82))
        i += 1
    if not story:
        story = [Paragraph("No authored content.", body)]

    def footer(canvas, doc):
        canvas.setFont("Lamina", 8)
        canvas.setFillColor(colors.HexColor("#6c7d87"))
        canvas.drawString(54, 30, "LAMINA")
        canvas.drawRightString(558, 30, str(doc.page))

    SimpleDocTemplate(
        str(path),
        title=title,
        author="",
        leftMargin=54,
        rightMargin=54,
        topMargin=48,
        bottomMargin=48,
    ).build(story, onFirstPage=footer, onLaterPages=footer)


def export_production(receipt: dict, plan: dict, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    markdown = receipt.get("markdown", "")
    if not isinstance(markdown, str):
        raise ValueError("production markdown must be text")
    assessment = receipt.get("format") == "assessment"
    title = (
        "Practice assessment" if assessment else receipt.get("title", "Lamina document")
    )
    (output / "document.md").write_text(markdown, encoding="utf-8")
    (output / "index.html").write_text(document_html(markdown, title), encoding="utf-8")
    links = {
        "document": "document.md",
        "reader": "index.html",
        "report": "report.json",
        "plan": "plan.json",
    }
    for name, value in [("report", receipt), ("plan", plan)]:
        (output / f"{name}.json").write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    for key in ("candidate_markdown", "examiner_markdown"):
        if isinstance(receipt.get(key), str) and receipt[key]:
            name = key.removesuffix("_markdown")
            (output / f"{name}.md").write_text(receipt[key], encoding="utf-8")
            (output / f"{name}.html").write_text(
                document_html(receipt[key], name.title()), encoding="utf-8"
            )
            links[name] = f"{name}.html"
    try:
        import reportlab
    except ImportError:
        return links
    _pdf(markdown, title, output / "document.pdf")
    links["pdf"] = "document.pdf"
    if assessment and receipt.get("examiner_markdown"):
        _pdf(receipt["examiner_markdown"], "Examiner guide", output / "examiner.pdf")
        links["examiner_pdf"] = "examiner.pdf"
    return links
