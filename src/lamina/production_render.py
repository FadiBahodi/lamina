"""Render finished sections as Markdown: the document, examiner guide and episode scripts.

Rendering is deterministic and makes no model calls. An assessment renders
candidate questions and a separate examiner guide; the retrieval-target
catalog goes to the examiner guide for an assessment and to the end of the
document otherwise.
"""

from __future__ import annotations

from .retrieval_targets import render_retrieval_targets


def _markdown(route: dict, sections: list[dict], fmt: str) -> str:
    if fmt == "assessment":
        candidate = "\n\n".join(
            "## Question " + str(index) + "\n\n" + s["candidate_body"]
            for index, s in enumerate(sections, 1)
        )
        return "# Practice assessment\n\n" + candidate + "\n"
    title = "# " + route["title"]
    by_section = {row["id"]: row for row in route["sections"]}
    episodes = {by_section.get(s["id"], {}).get("episode") for s in sections}
    if fmt == "podcast-script" and len(episodes - {None}) > 1:
        parts, current = [], None
        for s in sections:
            number = by_section.get(s["id"], {}).get("episode", 1)
            if number != current:
                parts.append(f"## Episode {number}")
                current = number
            parts.append("### " + s["title"] + "\n\n" + s["body"])
        return title + "\n\n" + "\n\n".join(parts) + "\n"
    return (
        title
        + "\n\n"
        + "\n\n".join("## " + s["title"] + "\n\n" + s["body"] for s in sections)
        + "\n"
    )


def episode_scripts(route: dict, sections: list[dict]) -> list[dict]:
    """One script per episode, in listening order, with its sections' bodies."""
    by_section = {row["id"]: row for row in route["sections"]}
    episodes = {}
    for s in sections:
        number = by_section.get(s["id"], {}).get("episode", 1)
        row = episodes.setdefault(
            number,
            {"number": number, "title": f"Episode {number}", "section_ids": [], "markdown": ""},
        )
        row["section_ids"].append(s["id"])
        row["markdown"] += "## " + s["title"] + "\n\n" + s["body"] + "\n\n"
    result = []
    for number in sorted(episodes):
        row = episodes[number]
        row["markdown"] = f"# {route['title']} — {row['title']}\n\n" + row["markdown"].rstrip() + "\n"
        row["words"] = len(row["markdown"].split())
        result.append(row)
    return result


def _retrieval_markdown(plan: dict) -> str | None:
    """The catalog restricted to targets the route assigned, or None."""
    if not plan.get("retrieval_targets"):
        return None
    selected_ids = {
        tid
        for section in plan["route"]["sections"]
        for tid in section["target_ids"]
    }
    selected_catalog = {
        "targets": [
            target
            for target in plan["retrieval_targets"]["targets"]
            if target["id"] in selected_ids
        ],
        "relations": [
            link
            for link in plan["retrieval_targets"]["relations"]
            if link["from_target_id"] in selected_ids
            and link["to_target_id"] in selected_ids
        ],
    }
    if selected_catalog["targets"]:
        return render_retrieval_targets(selected_catalog)
    return None


def render_outputs(plan: dict, opts: dict, authored: list[dict]) -> dict:
    """Return the output route and the document, examiner and retrieval Markdown.

    A direct document takes the writer's document title; every other route
    keeps the planned title.
    """
    output_route = plan["route"]
    if opts["workflow"] == "direct" and opts["format"] != "assessment":
        output_route = {
            **output_route,
            "title": authored[0].get("document_title", output_route["title"]),
        }
        markdown = "# " + output_route["title"] + "\n\n" + authored[0]["body"] + "\n"
    else:
        markdown = _markdown(output_route, authored, opts["format"])
    retrieval_markdown = _retrieval_markdown(plan)
    examiner_markdown = None
    if opts["format"] == "assessment":
        examiner_markdown = (
            "# "
            + plan["route"]["title"]
            + " — Answer and marking guide\n\n"
            + "\n\n".join(
                "## " + s["title"] + "\n\n" + s["marking_body"] for s in authored
            )
            + "\n"
        )
        if retrieval_markdown:
            examiner_markdown += "\n" + retrieval_markdown
    elif retrieval_markdown:
        markdown += "\n" + retrieval_markdown
    return {
        "route": output_route,
        "markdown": markdown,
        "examiner_markdown": examiner_markdown,
        "retrieval_markdown": retrieval_markdown,
    }
