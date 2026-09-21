/* Inspect an exported bundle. This is a reader of recorded objects, not a live run monitor. */
(() => {
  "use strict";

  const label = (value, fallback = "Untitled") =>
    typeof value === "string" && value.trim() ? value : fallback;
  const items = (value) => (Array.isArray(value) ? value : []);
  const el = (tag, className, value) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (value !== undefined) node.textContent = String(value);
    return node;
  };
  const add = (parent, ...children) => {
    children.forEach((child) => child && parent.appendChild(child));
    return parent;
  };
  const clear = (node) => {
    node.replaceChildren();
    return node;
  };

  function mount(container, bundle) {
    if (!container) return;
    clear(container);
    container.classList.add("inspector");
    if (
      !bundle ||
      !Array.isArray(bundle.sources) ||
      !Array.isArray(bundle.units)
    ) {
      add(
        container,
        el(
          "p",
          "inspector-empty",
          "The exported example bundle is unavailable.",
        ),
      );
      return;
    }

    const sources = [...items(bundle.sources)].sort((a, b) =>
      label(a.filename).localeCompare(label(b.filename)),
    );
    const units = items(bundle.units);
    const raw = items(bundle.raw_concepts);
    const concepts = items(bundle.concepts);
    const lessons = items(bundle.lessons);
    const plannedLessons = items(bundle.plan?.lessons);
    const deferred = items(bundle.plan?.deferred);
    const sourceById = new Map(sources.map((source) => [source.id, source]));
    const unitById = new Map(units.map((unit) => [unit.id, unit]));
    const rawById = new Map(raw.map((concept) => [concept.id, concept]));
    const conceptById = new Map(
      concepts.map((concept) => [concept.id, concept]),
    );
    const lessonById = new Map(lessons.map((lesson) => [lesson.id, lesson]));
    const outputRows = [
      {
        id: "reader",
        title: "Static study reader",
        kind: "HTML + JSON",
        description:
          "The exported bundle powers source-linked lessons, practice, scenarios, and scripts.",
      },
      ...(bundle.downloads?.markdown
        ? [
            {
              id: "markdown",
              title: "Study handout",
              kind: "Markdown",
              description: bundle.downloads.markdown,
            },
          ]
        : []),
      ...(bundle.downloads?.pdf
        ? [
            {
              id: "pdf",
              title: "Printable edition",
              kind: "PDF",
              description: bundle.downloads.pdf,
            },
          ]
        : []),
    ];
    const stages = [
      {
        id: "sources",
        number: "01",
        title: "Sources",
        count: sources.length,
        unit: "files",
        rows: sources,
        summary: `${units.length} accepted text units across ${sources.length} teaching files.`,
      },
      {
        id: "extract",
        number: "02",
        title: "Extract",
        count: raw.length,
        unit: "raw ideas",
        rows: raw,
        summary: `${raw.length} proposed ideas, each tied to an exact source quote.`,
      },
      {
        id: "reconcile",
        number: "03",
        title: "Reconcile",
        count: concepts.length,
        unit: "canonical",
        rows: concepts,
        summary: `${raw.length} raw ideas → ${concepts.length} canonical ideas; ${Math.max(0, raw.length - concepts.length)} overlapping records consolidated.`,
      },
      {
        id: "plan",
        number: "04",
        title: "Plan",
        count: plannedLessons.length,
        unit: "lessons",
        rows: plannedLessons,
        summary: `${plannedLessons.length} planned lessons; ${deferred.length} explicitly deferred concepts.`,
      },
      {
        id: "author",
        number: "05",
        title: "Author + review",
        count: lessons.length,
        unit: "lessons",
        rows: lessons,
        summary: `${lessons.length} lessons with authored sections, practice, scripts, and recorded review responses. ${label(bundle.build?.review_scope, "Review scope unavailable")}`,
      },
      {
        id: "outputs",
        number: "06",
        title: "Outputs",
        count: outputRows.length,
        unit: "formats",
        rows: outputRows,
        summary:
          "Formats present in this exported example bundle. Separate SAMP artifacts are inspected in their own example.",
      },
    ];

    const head = el("div", "inspector-head");
    add(
      head,
      add(
        el("div"),
        el("span", "inspector-kicker", "RECORDED PIPELINE / EXPORTED EXAMPLE"),
        el("h3", "", "Trace the transformation"),
        el(
          "p",
          "",
          "Choose a stage, then a record. Counts and citations come from this bundle. This is not live execution telemetry.",
        ),
      ),
    );
    const flow = el("div", "inspector-flow");
    flow.setAttribute("role", "tablist");
    flow.setAttribute("aria-label", "Pipeline stages");
    const stageButtons = new Map();
    stages.forEach((stage, index) => {
      const button = el("button", "inspector-stage");
      button.type = "button";
      button.id = `inspector-stage-${stage.id}`;
      button.setAttribute("role", "tab");
      button.setAttribute("aria-selected", "false");
      button.setAttribute("aria-controls", "inspector-detail");
      add(
        button,
        el("span", "inspector-stage-num", stage.number),
        el("strong", "", stage.title),
        el("span", "inspector-stage-count", `${stage.count} ${stage.unit}`),
      );
      flow.appendChild(button);
      stageButtons.set(stage.id, button);
      if (index < stages.length - 1)
        flow.appendChild(el("span", "inspector-arrow", "→"));
    });
    const panel = el("div", "inspector-panel");
    panel.id = "inspector-detail";
    panel.setAttribute("role", "tabpanel");
    const list = el("div", "inspector-record-list");
    const detail = el("article", "inspector-record-detail");
    const stageIntro = el("div", "inspector-stage-intro");
    const grid = add(el("div", "inspector-grid"), list, detail);
    add(panel, stageIntro, grid);
    add(container, head, flow, panel);

    const sourceRef = (evidence) => {
      const unit = unitById.get(evidence?.unit_id);
      const source = sourceById.get(unit?.source_id);
      return {
        unit,
        source,
        title: `${label(source?.filename, "Unknown source")} · ${label(unit?.heading, "Untitled unit")} · ${label(unit?.locator, "No locator")}`,
      };
    };
    const evidenceView = (parent, evidence) => {
      const rows = items(evidence);
      if (!rows.length) return;
      add(
        parent,
        el("h5", "inspector-minihead", `SOURCE EVIDENCE / ${rows.length}`),
      );
      rows.forEach((entry, index) => {
        const ref = sourceRef(entry);
        const wrap = el("div", "inspector-evidence");
        const button = el("button", "inspector-evidence-toggle", ref.title);
        button.type = "button";
        button.setAttribute("aria-expanded", "false");
        const quote = el(
          "blockquote",
          "inspector-quote",
          label(entry?.quote, "Quote unavailable"),
        );
        quote.hidden = true;
        quote.id = `inspector-quote-${index}-${Math.random().toString(36).slice(2, 9)}`;
        button.setAttribute("aria-controls", quote.id);
        button.addEventListener("click", () => {
          quote.hidden = !quote.hidden;
          button.setAttribute("aria-expanded", String(!quote.hidden));
        });
        add(wrap, button, quote);
        parent.appendChild(wrap);
      });
    };
    const textRow = (parent, name, value) => {
      add(
        parent,
        add(
          el("div", "inspector-field"),
          el("span", "inspector-field-label", name),
          el("p", "", label(value, "None recorded")),
        ),
      );
    };
    const pillRow = (parent, name, values) => {
      const wrap = el("div", "inspector-field");
      wrap.appendChild(el("span", "inspector-field-label", name));
      const pills = el("div", "inspector-pills");
      if (!values.length)
        pills.appendChild(el("span", "inspector-empty-inline", "None"));
      values.forEach((value) =>
        pills.appendChild(el("span", "inspector-pill", value)),
      );
      wrap.appendChild(pills);
      parent.appendChild(wrap);
    };
    const recordTitle = (stage, row) => {
      if (stage.id === "sources") return label(row.filename);
      if (stage.id === "plan" || stage.id === "author") return label(row.title);
      return label(row.title);
    };
    const recordMeta = (stage, row) => {
      if (stage.id === "sources")
        return `${units.filter((unit) => unit.source_id === row.id).length} units · ${label(row.role)}`;
      if (stage.id === "extract")
        return sourceRef(items(row.evidence)[0]).title;
      if (stage.id === "reconcile")
        return `${items(row.member_ids).length} raw member${items(row.member_ids).length === 1 ? "" : "s"}`;
      if (stage.id === "plan")
        return `${items(row.concept_ids).length} concepts · ${items(row.prerequisite_ids).length} prerequisites`;
      if (stage.id === "author")
        return `${items(row.sections).length} sections · ${items(row.questions).length} questions`;
      return row.kind;
    };
    const renderRecord = (stage, row) => {
      clear(detail);
      add(
        detail,
        el(
          "span",
          "inspector-kicker",
          `${stage.title.toUpperCase()} / RECORDED OBJECT`,
        ),
        el("h4", "", recordTitle(stage, row)),
      );
      if (stage.id === "sources") {
        textRow(
          detail,
          "Source identity",
          `${row.filename} · SHA-256 ${label(row.sha256).slice(0, 12)}…`,
        );
        units
          .filter((unit) => unit.source_id === row.id)
          .forEach((unit) => {
            const block = el("div", "inspector-subrecord");
            add(
              block,
              el("strong", "", label(unit.heading)),
              el("span", "inspector-submeta", label(unit.locator)),
              el(
                "p",
                "",
                label(unit.text).slice(0, 430) +
                  (unit.text?.length > 430 ? "…" : ""),
              ),
            );
            detail.appendChild(block);
          });
      } else if (stage.id === "extract") {
        textRow(detail, "Proposed interpretation", row.explanation);
        evidenceView(detail, row.evidence);
      } else if (stage.id === "reconcile") {
        textRow(detail, "Canonical interpretation", row.explanation);
        const members = items(row.member_ids)
          .map((id) => rawById.get(id))
          .filter(Boolean);
        pillRow(
          detail,
          "Raw concepts accounted for",
          members.map((member) => member.title),
        );
        if (members.length > 1)
          textRow(
            detail,
            "Consolidation",
            `${members.length} source interpretations share this teaching concept. Inspect each source quote below; membership does not prove semantic equivalence.`,
          );
        members.forEach((member) => {
          const block = el("div", "inspector-subrecord");
          add(
            block,
            el("strong", "", label(member.title)),
            el("p", "", label(member.explanation)),
          );
          evidenceView(block, member.evidence);
          detail.appendChild(block);
        });
      } else if (stage.id === "plan") {
        pillRow(
          detail,
          "Assigned concepts",
          items(row.concept_ids).map((id) =>
            label(conceptById.get(id)?.title, id),
          ),
        );
        pillRow(
          detail,
          "Actual prerequisite edges",
          items(row.prerequisite_ids).map(
            (id) =>
              `${label(lessonById.get(id)?.title, id)} → ${label(row.title)}`,
          ),
        );
        if (deferred.length) {
          const block = el("div", "inspector-subrecord");
          add(block, el("strong", "", "Explicit deferrals"));
          deferred.forEach((entry) =>
            add(
              block,
              el(
                "p",
                "",
                `${label(conceptById.get(entry.concept_id)?.title, entry.concept_id)}: ${label(entry.reason)}`,
              ),
            ),
          );
          detail.appendChild(block);
        }
      } else if (stage.id === "author") {
        textRow(detail, "Lesson summary", row.summary);
        const review = row.review || {};
        textRow(
          detail,
          "Recorded review response",
          `${label(review.status, "Unavailable")} · ${items(review.issues).length} issues`,
        );
        textRow(
          detail,
          "Review scope",
          `${label(bundle.build?.review_mode, "unknown mode")} · ${label(bundle.build?.review_scope, "Scope unavailable")}`,
        );
        const section = items(row.sections)[0];
        if (section) {
          const block = el("div", "inspector-subrecord");
          add(
            block,
            el("strong", "", label(section.heading)),
            el("p", "", label(section.body)),
          );
          evidenceView(block, section.evidence);
          detail.appendChild(block);
        }
        pillRow(detail, "Practice modes", [
          ...new Set(
            items(row.questions).map((question) => label(question.kind)),
          ),
        ]);
        textRow(
          detail,
          "Other authored forms",
          `${row.scenario ? "Scenario recorded" : "No scenario recorded"} · ${items(row.audio_script).length} script segments`,
        );
      } else {
        textRow(detail, "Recorded format", row.kind);
        textRow(detail, "What is present", row.description);
        const destination =
          row.id === "reader"
            ? "workbench/"
            : row.id === "markdown"
              ? "workbench/study-guide.md"
              : row.id === "pdf"
                ? "workbench/study-guide.pdf"
                : null;
        if (destination) {
          const link = el("a", "inspector-output-link", `Open ${row.title} →`);
          link.href = new URL(destination, document.baseURI).href;
          detail.appendChild(link);
        }
        textRow(
          detail,
          "Scope",
          "This inspector reads the exported bundle. It does not infer audio delivery, assessment validity, or runtime duration.",
        );
      }
    };
    const renderStage = (stage) => {
      panel.setAttribute("aria-labelledby", `inspector-stage-${stage.id}`);
      stageButtons.forEach((button, id) => {
        const selected = id === stage.id;
        button.classList.toggle("is-selected", selected);
        button.setAttribute("aria-selected", String(selected));
        button.tabIndex = selected ? 0 : -1;
      });
      clear(stageIntro);
      add(
        stageIntro,
        el(
          "span",
          "inspector-kicker",
          `STAGE ${stage.number} / ${stage.title.toUpperCase()}`,
        ),
        el("p", "", stage.summary),
      );
      clear(list);
      if (!stage.rows.length) {
        add(
          list,
          el("p", "inspector-empty", "No records in this exported bundle."),
        );
        clear(detail);
        return;
      }
      stage.rows.forEach((row, index) => {
        const button = el("button", "inspector-record");
        button.type = "button";
        add(
          button,
          el("strong", "", recordTitle(stage, row)),
          el("span", "", recordMeta(stage, row)),
        );
        button.addEventListener("click", () => {
          [...list.querySelectorAll(".inspector-record")].forEach((other) =>
            other.classList.remove("is-selected"),
          );
          button.classList.add("is-selected");
          renderRecord(stage, row);
        });
        list.appendChild(button);
        if (index === 0) button.click();
      });
    };
    stages.forEach((stage) =>
      stageButtons
        .get(stage.id)
        .addEventListener("click", () => renderStage(stage)),
    );
    flow.addEventListener("keydown", (event) => {
      if (!["ArrowRight", "ArrowLeft", "Home", "End"].includes(event.key))
        return;
      event.preventDefault();
      const active = stages.findIndex(
        (stage) =>
          stageButtons.get(stage.id).getAttribute("aria-selected") === "true",
      );
      const next =
        event.key === "Home"
          ? 0
          : event.key === "End"
            ? stages.length - 1
            : (active + (event.key === "ArrowRight" ? 1 : -1) + stages.length) %
              stages.length;
      stageButtons.get(stages[next].id).focus();
      renderStage(stages[next]);
    });
    renderStage(stages[0]);
  }

  window.LaminaInspector = { mount };
})();
