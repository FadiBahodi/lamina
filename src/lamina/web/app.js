(() => {
  "use strict";

  const bundle = window.LAMINA_BUNDLE;
  const host = document.getElementById("app");
  const nav = Array.from(document.querySelectorAll("[data-view]"));
  const views = ["learn", "practice", "sources", "coverage"];
  // Revision namespace for local UI notes only (not a cryptographic receipt).
  // Changed questions must not inherit a previous edition's reveals or ratings.
  function revision(value) {
    let hash = 2166136261;
    for (const ch of JSON.stringify(value)) {
      hash ^= ch.codePointAt(0);
      hash = Math.imul(hash, 16777619);
    }
    return (hash >>> 0).toString(16);
  }
  const storageKey = bundle
    ? `lamina:study:${(bundle.sources || []).map((s) => s.sha256 || s.id).join(":")}:${revision(bundle.lessons || [])}`
    : "lamina:study:empty";
  let saved = readSaved();
  const state = {
    view: "learn",
    practiceMode: "recall",
    lesson: 0,
    question: 0,
    sourceFocus: null,
    sourceSearch: "",
    scriptOpen: false,
    examinerOpen: false,
  };
  let speech = null;

  function readSaved() {
    try {
      const value = JSON.parse(localStorage.getItem(storageKey) || "{}");
      return value && typeof value === "object" && !Array.isArray(value)
        ? value
        : {};
    } catch (_) {
      return {};
    }
  }
  function persist() {
    try {
      localStorage.setItem(storageKey, JSON.stringify(saved));
    } catch (_) {
      /* private storage may be disabled */
    }
  }
  function node(tag, className, value) {
    const n = document.createElement(tag);
    if (className) n.className = className;
    if (value != null) n.textContent = String(value);
    return n;
  }
  function add(parent, ...children) {
    children.forEach((c) => c && parent.append(c));
    return parent;
  }
  function paragraph(parent, value, cls) {
    if (!value) return;
    String(value)
      .split(/\n\s*\n/)
      .forEach((t) => add(parent, node("p", cls || "", t)));
  }
  function button(label, className, onClick) {
    const b = node("button", className, label);
    b.type = "button";
    b.addEventListener("click", onClick);
    return b;
  }
  function field(label, value) {
    return node("span", label, value);
  }
  function safeDownloadPath(path) {
    return typeof path === "string" &&
      /^[A-Za-z0-9_-][A-Za-z0-9_./-]*$/.test(path) &&
      !path.includes("..")
      ? path
      : null;
  }
  function renderDownloads() {
    const rail = document.getElementById("rail-downloads");
    const footer = document.getElementById("footer-downloads");
    if (!rail || !footer) return;
    const files = [
      ["pdf", "Study guide PDF"],
      ["markdown", "Markdown notes"],
    ]
      .map(([key, label]) => [
        safeDownloadPath(bundle?.downloads?.[key]),
        label,
      ])
      .filter(([path]) => path);
    if (!files.length) {
      footer.textContent = "Study guide";
      return;
    }
    add(rail, node("div", "small-label", "TAKE IT WITH YOU"));
    files.forEach(([path, label]) => {
      const a = node("a", "download-link", `${label} ↗`);
      a.href = path;
      a.download = path.split("/").pop();
      add(rail, a);
      const f = node("a", "", label);
      f.href = path;
      f.download = a.download;
      add(footer, f);
    });
  }
  function lessons() {
    return Array.isArray(bundle?.lessons) ? bundle.lessons : [];
  }
  function currentLesson() {
    return lessons()[state.lesson];
  }
  function allQuestions() {
    return lessons().flatMap((lesson, li) =>
      (lesson.questions || []).map((question, qi) => ({
        lesson,
        question,
        li,
        qi,
      })),
    );
  }
  function currentQuestions() {
    return currentLesson()?.questions || [];
  }
  function sourceById(id) {
    return (bundle.sources || []).find((s) => s.id === id);
  }
  function unitById(id) {
    return (bundle.units || []).find((u) => u.id === id);
  }
  function selectedEvidence() {
    return state.sourceFocus;
  }
  function setView(view, focusMain = true) {
    if (!views.includes(view)) return;
    stopSpeech();
    state.view = view;
    nav.forEach((b) => {
      const active = b.dataset.view === view;
      b.classList.toggle("active", active);
      active
        ? b.setAttribute("aria-current", "page")
        : b.removeAttribute("aria-current");
    });
    history.replaceState(null, "", `#${view}`);
    render();
    window.scrollTo({ top: 0, behavior: "instant" });
    if (focusMain)
      document.getElementById("main").focus({ preventScroll: true });
  }
  function hero(kicker, title, intro, meta) {
    const h = node("section", "hero");
    add(
      h,
      node("div", "eyebrow", kicker),
      node("h1", "", title),
      node("p", "lede", intro),
    );
    if (meta) {
      const m = node("div", "hero-meta");
      add(m, node("span", "pill", meta));
      add(h, m);
    }
    return h;
  }
  function sectionLead(label, title, intro) {
    const s = node("div", "section-rule");
    add(
      s,
      node("div", "section-kicker", label),
      node("h2", "section-title", title),
    );
    if (intro) add(s, node("p", "section-intro", intro));
    return s;
  }
  function evidenceButtons(items) {
    const list = node("div", "evidence-list");
    (items || []).forEach((ev, i) => {
      if (!ev?.unit_id || !ev?.quote) return;
      const unit = unitById(ev.unit_id);
      const source = unit && sourceById(unit.source_id);
      const citation =
        unit?.heading || source?.filename || source?.title || "Source";
      add(
        list,
        button(
          `↗ ${citation}${unit?.locator ? ` · ${unit.locator}` : ""}${items.length > 1 ? ` (${i + 1})` : ""}`,
          "evidence-link",
          () => openEvidence(ev),
        ),
      );
    });
    return list;
  }
  function openEvidence(ev) {
    const unit = unitById(ev.unit_id);
    if (!unit) return;
    const source = sourceById(unit.source_id);
    const opener = document.activeElement;
    const dialog = node("dialog", "evidence-dialog");
    const top = node("div", "dialog-top");
    add(
      top,
      node("span", "case-label", "SOURCE EVIDENCE"),
      button("Close ×", "dialog-close", () => dialog.close()),
    );
    add(dialog, top);
    add(
      dialog,
      node("h2", "", unit.heading || "Source excerpt"),
      node(
        "p",
        "source-name",
        `${source?.filename || source?.title || "Source"}${unit.locator ? ` · ${unit.locator}` : ""}`,
      ),
    );
    const text = String(unit.text || "");
    const quote = String(ev.quote || "");
    const index = text.indexOf(quote);
    const excerpt = node("p", "source-text");
    if (quote && index >= 0)
      excerpt.append(
        document.createTextNode(text.slice(0, index)),
        node("mark", "", quote),
        document.createTextNode(text.slice(index + quote.length)),
      );
    else excerpt.textContent = text;
    add(dialog, excerpt);
    const actions = node("div", "dialog-actions");
    add(
      actions,
      button("Browse all sources →", "button secondary", () => {
        state.sourceFocus = { unitId: ev.unit_id, quote: ev.quote };
        dialog.close();
        setView("sources");
      }),
    );
    add(dialog, actions);
    dialog.addEventListener("close", () => {
      dialog.remove();
      if (
        opener instanceof HTMLElement &&
        opener.isConnected &&
        state.view !== "sources"
      )
        opener.focus({ preventScroll: true });
    });
    document.body.append(dialog);
    dialog.showModal();
    dialog.querySelector(".dialog-close").focus();
  }
  function lessonSelect() {
    const wrap = node("div", "lesson-pick");
    const label = node("label", "", "Choose a lesson");
    label.htmlFor = "lesson-selector";
    const select = node("select");
    select.id = "lesson-selector";
    lessons().forEach((l, i) => {
      const opt = node(
        "option",
        "",
        `${String(i + 1).padStart(2, "0")}  ${l.title || "Untitled lesson"}`,
      );
      opt.value = String(i);
      select.add(opt);
    });
    select.value = String(state.lesson);
    select.addEventListener("change", () => {
      state.lesson = Number(select.value);
      state.question = 0;
      stopSpeech();
      render();
    });
    return add(wrap, label, select);
  }
  function renderLearn() {
    const lesson = currentLesson();
    const intro =
      bundle.description ||
      "A small path from source material to concepts, explanation, and questions that expose what you know.";
    add(
      host,
      hero(
        "GENERATED GUIDE",
        bundle.title || "Learn with the grain of the source.",
        intro,
        `${lessons().length} ${lessons().length === 1 ? "lesson" : "lessons"}`,
      ),
    );
    if (String(bundle.build?.provider || "").startsWith("curated-offline"))
      add(
        host,
        node(
          "p",
          "fixture-note",
          "Example guide · The lessons were written for this demonstration.",
        ),
      );
    const art = node("img", "hero-art");
    art.src = "assets/diagram.svg";
    art.alt =
      "Source text leads to concepts, lessons, and practice with evidence kept in reach.";
    add(host, art);
    if (!lesson) {
      add(
        host,
        node(
          "p",
          "empty-note",
          "No lessons were included in this bundle. Inspect the source and coverage views for what is available.",
        ),
      );
      return;
    }
    add(
      host,
      sectionLead(
        `LESSON ${String(state.lesson + 1).padStart(2, "0")} / ${String(lessons().length).padStart(2, "0")}`,
        lesson.title || "Untitled lesson",
        "Read the explanation, then follow any source marker to the exact words behind it.",
      ),
    );
    add(host, lessonSelect());
    const layout = node("div", "lesson-layout");
    const body = node("article", "lesson-body");
    const aside = node("aside");
    add(body, node("p", "summary", lesson.summary || ""));
    (lesson.sections || []).forEach((section) => {
      const s = node("section", "prose-section");
      add(s, node("h3", "", section.heading || "Key idea"));
      paragraph(s, section.body || "");
      add(s, evidenceButtons(section.evidence));
      add(body, s);
    });
    const card = node("div", "aside-card");
    add(
      card,
      node("div", "small-label", "AFTER THE READ"),
      node("p", "", "Can you use the idea when the situation changes?"),
      button("Try the questions →", "button", () => setView("practice")),
      node(
        "p",
        "small-copy",
        "Recall, contrast, and apply give you three ways to work with it.",
      ),
    );
    add(aside, card);
    if (Array.isArray(lesson.audio_script) && lesson.audio_script.length)
      add(aside, renderAudio(lesson));
    add(layout, body, aside);
    add(host, layout);
  }
  function renderAudio(lesson) {
    const card = node("section", "audio-card");
    add(
      card,
      node("h3", "", "Listen through the idea"),
      node(
        "p",
        "",
        "A read-aloud script is included. Browser speech uses your device voice and may vary by browser.",
      ),
    );
    const actions = node("div", "audio-actions");
    const canSpeak = "speechSynthesis" in window;
    const play = button(
      speech ? "Stop reading" : "Read aloud",
      "button secondary",
      () => {
        speech ? stopSpeech() : startSpeech(lesson);
        render();
      },
    );
    play.disabled = !canSpeak;
    add(
      actions,
      play,
      button(
        state.scriptOpen ? "Hide script" : "Show script",
        "button ghost",
        () => {
          state.scriptOpen = !state.scriptOpen;
          render();
        },
      ),
    );
    add(card, actions);
    if (!canSpeak)
      add(
        card,
        node(
          "p",
          "caption",
          "Speech playback is not available in this browser; the script remains readable.",
        ),
      );
    if (state.scriptOpen) {
      const lines = node("div", "script-lines");
      lesson.audio_script.forEach((part) =>
        add(
          lines,
          node(
            "p",
            `script-line ${part.kind === "pause" ? "pause" : ""}`,
            part.kind === "pause"
              ? `Pause · ${part.text || ""}`
              : part.text || "",
          ),
        ),
      );
      add(card, lines);
    }
    return card;
  }
  function startSpeech(lesson) {
    if (!("speechSynthesis" in window)) return;
    const text = (lesson.audio_script || [])
      .filter((p) => p.kind === "speech")
      .map((p) => p.text)
      .join(" ");
    if (!text) return;
    window.speechSynthesis.cancel();
    speech = new SpeechSynthesisUtterance(text);
    speech.rate = 0.93;
    speech.onend = () => {
      speech = null;
      render();
    };
    speech.onerror = () => {
      speech = null;
      render();
    };
    window.speechSynthesis.speak(speech);
  }
  function stopSpeech() {
    if (speech && "speechSynthesis" in window) window.speechSynthesis.cancel();
    speech = null;
  }
  function renderPractice() {
    const lesson = currentLesson();
    add(
      host,
      hero(
        "DELIBERATE PRACTICE",
        "Practice the questions.",
        "Write an answer before opening the suggested response. Mark what needs another pass.",
        `${allQuestions().length} questions across ${lessons().length} lessons`,
      ),
    );
    const modes = node("div", "mode-switch");
    [
      ["recall", "Recall & apply"],
      ["case", "Run a case"],
    ].forEach(([id, label]) => {
      const b = button(
        label,
        `mode-button ${state.practiceMode === id ? "selected" : ""}`,
        () => {
          state.practiceMode = id;
          render();
        },
      );
      b.setAttribute("aria-pressed", String(state.practiceMode === id));
      add(modes, b);
    });
    add(host, modes);
    if (!lesson) {
      add(
        host,
        node("p", "empty-note", "No lessons were included in this bundle."),
      );
      return;
    }
    add(host, lessonSelect());
    if (state.practiceMode === "case") {
      renderCase(lesson);
      return;
    }
    if (!currentQuestions().length) {
      add(
        host,
        node(
          "p",
          "empty-note",
          "No recall questions were included for this lesson.",
        ),
      );
      return;
    }
    const qs = currentQuestions();
    state.question = Math.max(0, Math.min(state.question, qs.length - 1));
    const q = qs[state.question];
    const id = `${lesson.id || state.lesson}:${q.id || state.question}`;
    const head = node("div", "practice-head");
    add(
      head,
      sectionLead(
        "QUESTION",
        q.kind ? `${q.kind[0].toUpperCase()}${q.kind.slice(1)}` : "Question",
        "Write an answer, then reveal the suggested response to compare.",
      ),
      node("span", "practice-count", `${state.question + 1} / ${qs.length}`),
    );
    add(host, head);
    const track = node("div", "progress-track");
    const fill = node("div", "progress-fill");
    fill.style.width = `${((state.question + 1) / qs.length) * 100}%`;
    add(track, fill);
    add(host, track);
    const card = node("section", "question-card");
    add(
      card,
      node("span", "question-type", q.kind || "question"),
      node("h3", "", q.prompt || ""),
    );
    const label = node("label", "answer-label", "Your thinking");
    label.htmlFor = "practice-answer";
    const textarea = node("textarea", "answer-input");
    textarea.id = "practice-answer";
    textarea.placeholder =
      "Draft what you would say, then compare it with the suggested answer…";
    textarea.value = saved.answers?.[id] || "";
    textarea.addEventListener("input", () => {
      saved.answers ||= {};
      saved.answers[id] = textarea.value;
      persist();
    });
    add(card, label, textarea);
    const answerVisible = Boolean(saved.revealed?.[id]);
    const actions = node("div", "question-actions");
    add(
      actions,
      button(
        answerVisible ? "Hide suggested answer" : "Reveal suggested answer",
        "button",
        () => {
          saved.revealed ||= {};
          saved.revealed[id] = !saved.revealed[id];
          persist();
          render();
          const el = document.getElementById("practice-answer");
          if (el) el.focus({ preventScroll: true });
        },
      ),
    );
    add(card, actions);
    if (answerVisible) {
      const panel = node("div", "answer-panel");
      add(panel, node("h4", "", "Suggested answer"));
      paragraph(panel, q.answer, "answer-text");
      if (q.rationale) {
        add(panel, node("h4", "", "Why it works"));
        paragraph(panel, q.rationale);
      }
      add(panel, evidenceButtons(q.evidence));
      const row = node("div", "rating-row");
      add(row, node("span", "", "How did it feel?"));
      [
        ["again", "Revisit"],
        ["partial", "Almost there"],
        ["clear", "Could explain it"],
      ].forEach(([value, label]) => {
        const b = button(
          label,
          `rating ${saved.ratings?.[id] === value ? "selected" : ""}`,
          () => {
            saved.ratings ||= {};
            saved.ratings[id] = value;
            persist();
            render();
          },
        );
        b.setAttribute("aria-pressed", String(saved.ratings?.[id] === value));
        add(row, b);
      });
      add(panel, row);
      add(card, panel);
    }
    add(host, card);
    const bottom = node("div", "practice-next");
    add(
      bottom,
      node(
        "p",
        "micro-note",
        "Your answers and self-ratings stay in this browser; ratings are your own notes.",
      ),
    );
    const navs = node("div", "question-actions");
    const prev = button("← Previous", "button ghost", () => {
      state.question--;
      render();
    });
    prev.disabled = state.question === 0;
    const next = button(
      state.question === qs.length - 1 ? "Next lesson →" : "Next question →",
      "button secondary",
      () => {
        if (state.question < qs.length - 1) state.question++;
        else if (state.lesson < lessons().length - 1) {
          state.lesson++;
          state.question = 0;
        }
        render();
      },
    );
    next.disabled =
      state.question === qs.length - 1 && state.lesson === lessons().length - 1;
    add(navs, prev, next);
    add(bottom, navs);
    add(host, bottom);
  }
  function renderCase(lesson) {
    const scenario = lesson.scenario;
    if (!scenario) {
      add(
        host,
        node(
          "p",
          "empty-note",
          "This lesson has no authored case. Choose another lesson or use recall practice.",
        ),
      );
      return;
    }
    const key = `case:${lesson.id || state.lesson}`;
    const record = saved.cases?.[key] || {
      released: [],
      second: false,
      checked: [],
      debrief: false,
    };
    const saveCase = () => {
      saved.cases ||= {};
      saved.cases[key] = record;
      persist();
    };
    add(
      host,
      sectionLead(
        "LOCAL CASE PRACTICE",
        scenario.title || lesson.title,
        "Run the case with another person as examiner. Both roles use this screen.",
      ),
    );
    const candidate = node("section", "case-candidate");
    add(
      candidate,
      node("div", "case-label", "CANDIDATE BRIEF"),
      node("p", "case-brief", scenario.candidate_brief || ""),
    );
    if (scenario.decision_prompt)
      add(
        candidate,
        node("div", "case-label", "FIRST DECISION"),
        node("p", "case-prompt", scenario.decision_prompt),
      );
    if (record.released.length || record.second) {
      const results = node("div", "case-results");
      add(results, node("div", "case-label", "RELEASED FINDINGS"));
      (scenario.findings || [])
        .filter((f) => record.released.includes(f.id))
        .forEach((f) => {
          const item = node("div", "case-result");
          add(
            item,
            node("strong", "", f.label || "Finding"),
            node("p", "", f.text || ""),
          );
          add(results, item);
        });
      if (record.second) {
        const item = node("div", "case-result event");
        add(
          item,
          node("strong", "", "SECOND EVENT"),
          node("p", "", scenario.second_event?.text || ""),
        );
        add(results, item);
        if (scenario.reassessment_prompt)
          add(results, node("p", "case-prompt", scenario.reassessment_prompt));
      }
      add(candidate, results);
    } else
      add(
        candidate,
        node(
          "p",
          "case-waiting",
          "Findings appear here when the examiner releases them.",
        ),
      );
    add(host, candidate);
    const controls = node("section", "examiner-wrap");
    const toggle = button(
      state.examinerOpen ? "Close examiner desk ↑" : "Open examiner desk ↓",
      "button secondary",
      () => {
        state.examinerOpen = !state.examinerOpen;
        render();
      },
    );
    toggle.setAttribute("aria-expanded", String(state.examinerOpen));
    add(controls, toggle);
    if (state.examinerOpen) {
      const panel = node("div", "examiner-panel");
      add(
        panel,
        node("div", "case-label", "EXAMINER DESK"),
        node(
          "p",
          "examiner-warning",
          "Keep this panel out of the candidate’s view while they answer. This is a shared-screen local exercise.",
        ),
      );
      const findings = node("div", "examiner-findings");
      (scenario.findings || []).forEach((f) => {
        const row = node("div", "examiner-finding");
        const copy = node("div");
        add(
          copy,
          node("strong", "", f.label || "Finding"),
          node("p", "", f.text || ""),
        );
        add(copy, evidenceButtons(f.evidence));
        add(row, copy);
        add(
          row,
          button(
            record.released.includes(f.id) ? "Withdraw" : "Release →",
            record.released.includes(f.id) ? "button ghost" : "button",
            () => {
              record.released = record.released.includes(f.id)
                ? record.released.filter((x) => x !== f.id)
                : [...record.released, f.id];
              saveCase();
              render();
            },
          ),
        );
        add(findings, row);
      });
      add(panel, findings);
      if (scenario.second_event) {
        const event = node("div", "examiner-event");
        add(
          event,
          node("div", "case-label", "SECOND EVENT"),
          node(
            "p",
            "",
            `Trigger: ${scenario.second_event.trigger || "When ready, advance the case."}`,
          ),
          node("p", "examiner-event-text", scenario.second_event.text || ""),
        );
        if (scenario.reassessment_prompt)
          add(
            event,
            node(
              "p",
              "examiner-reassessment",
              `Then ask: ${scenario.reassessment_prompt}`,
            ),
          );
        add(
          event,
          button(
            record.second ? "Withdraw event" : "Release event →",
            "button",
            () => {
              record.second = !record.second;
              saveCase();
              render();
            },
          ),
          evidenceButtons(scenario.second_event.evidence),
        );
        add(panel, event);
      }
      const list = node("div", "case-checklist");
      add(
        list,
        node("div", "case-label", "DISCUSSION CHECKLIST"),
        node(
          "p",
          "micro-note",
          "Use the checklist to record discussion points for the debrief.",
        ),
      );
      (scenario.checklist || []).forEach((item) => {
        const row = node("div", "check-item");
        const check = node("input");
        check.type = "checkbox";
        check.id = `check-${String(key + item.id).replace(/[^a-zA-Z0-9_-]/g, "_")}`;
        check.checked = record.checked.includes(item.id);
        check.addEventListener("change", () => {
          record.checked = check.checked
            ? [...record.checked, item.id]
            : record.checked.filter((x) => x !== item.id);
          saveCase();
        });
        const label = node("label", "", item.criterion || "");
        label.htmlFor = check.id;
        add(row, check, label, evidenceButtons(item.evidence));
        add(list, row);
      });
      add(panel, list);
      const debrief = node("div", "case-debrief");
      add(
        debrief,
        button(
          record.debrief ? "Hide debrief" : "Reveal debrief",
          "button secondary",
          () => {
            record.debrief = !record.debrief;
            saveCase();
            render();
          },
        ),
      );
      if (record.debrief) paragraph(debrief, scenario.debrief || "");
      add(panel, debrief);
      add(controls, panel);
    }
    add(host, controls);
  }
  function renderSources() {
    add(
      host,
      hero(
        "THE EVIDENCE DESK",
        "Keep the source in view.",
        "Every citation here opens the exact excerpt used for a lesson or question. Inspect surrounding text and the document it came from.",
        `${(bundle.sources || []).length} source documents`,
      ),
    );
    add(
      host,
      sectionLead(
        "SOURCE LIBRARY",
        "Original text, visible links",
        "Search the source excerpts. A highlighted quote is the exact phrase attached to the selected claim.",
      ),
    );
    add(
      host,
      node(
        "p",
        "source-privacy",
        "This exported library contains teaching sources. Held-out assessment inputs are excluded.",
      ),
    );
    const toolbar = node("div", "source-toolbar");
    const search = node("input", "search");
    search.type = "search";
    search.placeholder = "Find a term in source text or headings";
    search.setAttribute("aria-label", "Search source excerpts");
    search.value = state.sourceSearch;
    search.addEventListener("input", () => {
      state.sourceSearch = search.value;
      paintSourceCards();
    });
    add(toolbar, search);
    add(host, toolbar);
    const grid = node("div", "source-grid");
    grid.id = "source-grid";
    add(host, grid);
    paintSourceCards();
  }
  function paintSourceCards() {
    const grid = document.getElementById("source-grid");
    if (!grid) return;
    grid.replaceChildren();
    const focus = selectedEvidence();
    const query = state.sourceSearch.trim().toLowerCase();
    const units = [...(bundle.units || [])].sort(
      (a, b) => (a.ordinal || 0) - (b.ordinal || 0),
    );
    let filtered = units.filter((u) => {
      const s = sourceById(u.source_id);
      return (
        !query ||
        `${u.heading || ""} ${u.text || ""} ${s?.title || ""}`
          .toLowerCase()
          .includes(query)
      );
    });
    if (focus && !query)
      filtered.sort((a, b) =>
        a.id === focus.unitId ? -1 : b.id === focus.unitId ? 1 : 0,
      );
    if (!filtered.length) {
      add(
        grid,
        node("p", "empty-note", "No source excerpts match that search."),
      );
      return;
    }
    filtered.forEach((unit) => {
      const source = sourceById(unit.source_id);
      const selected = focus?.unitId === unit.id;
      const card = node("article", `source-card ${selected ? "focused" : ""}`);
      card.id = `unit-${unit.id.replace(/[^a-zA-Z0-9_-]/g, "_")}`;
      const top = node("div", "source-heading");
      add(
        top,
        node("h3", "", unit.heading || "Source excerpt"),
        node("span", "locator", unit.locator || ""),
      );
      add(card, top);
      add(card, node("p", "source-name", source?.title || "Unknown source"));
      const sourceText = String(unit.text || "");
      const quote = selected ? String(focus.quote || "") : "";
      if (quote) {
        const index = sourceText.indexOf(quote);
        if (index >= 0) {
          const text = node("p", "source-text");
          text.append(
            document.createTextNode(sourceText.slice(0, index)),
            node("mark", "", quote),
            document.createTextNode(sourceText.slice(index + quote.length)),
          );
          add(card, text);
        } else {
          add(
            card,
            node("p", "source-quote", quote),
            node("p", "source-text", sourceText),
            node(
              "p",
              "caption",
              "The selected quote was not found in this exported excerpt.",
            ),
          );
        }
      } else add(card, node("p", "source-text", sourceText));
      const meta = node("div", "source-meta");
      add(
        meta,
        node("span", "source-badge", source?.role || "teaching"),
        node("span", "source-badge", source?.filename || "source document"),
      );
      add(card, meta);
      add(grid, card);
    });
  }
  function renderCoverage() {
    const concepts = bundle.concepts || [];
    const plan = bundle.plan || {};
    const deferred = Array.isArray(plan.deferred) ? plan.deferred : [];
    const assigned = new Set(
      (plan.lessons || []).flatMap((l) => l.concept_ids || []),
    );
    add(
      host,
      hero(
        "SCOPE & BOUNDARIES",
        "See what was covered.",
        "See which extracted concepts were used, deferred, or left unassigned. Extraction may miss ideas in the source.",
        `${concepts.length} extracted concepts`,
      ),
    );
    if (String(bundle.build?.provider || "").startsWith("curated-offline"))
      add(
        host,
        node(
          "p",
          "fixture-note",
          "Recorded example · The lessons and cases in this guide are hand-authored.",
        ),
      );
    add(
      host,
      sectionLead(
        "EXTRACTION → ALLOCATION",
        "Concepts in this guide",
        "These counts describe this guide: concepts assigned to lessons, deferred, or unassigned.",
      ),
    );
    const metrics = node("div", "metric-row");
    [
      [concepts.length, "Concepts extracted"],
      [assigned.size, "Assigned to lessons"],
      [deferred.length, "Explicitly deferred"],
    ].forEach(([v, l]) => {
      const m = node("div", "metric");
      add(m, node("strong", "", v), node("span", "", l));
      add(metrics, m);
    });
    add(host, metrics);
    const list = node("div", "coverage-list");
    concepts.forEach((c) => {
      const d = deferred.find((x) => x.concept_id === c.id);
      const row = node("div", "coverage-row");
      add(row, node("span", `coverage-marker ${d ? "deferred" : ""}`));
      const copy = node("div");
      add(
        copy,
        node("h3", "", c.title || c.id),
        node(
          "p",
          "",
          d
            ? `Deferred: ${d.reason || "No reason supplied"}`
            : assigned.has(c.id)
              ? `Assigned to ${(plan.lessons || [])
                  .filter((l) => (l.concept_ids || []).includes(c.id))
                  .map((l) => l.title || l.id)
                  .join(", ")}`
              : "Unassigned in this bundle",
        ),
      );
      add(row, copy);
      add(list, row);
    });
    if (!concepts.length)
      add(
        list,
        node(
          "p",
          "empty-note",
          "No extracted concepts are included in this bundle.",
        ),
      );
    add(host, list);
    const boundary = node("div", "boundary");
    add(
      boundary,
      node("h3", "", "What these marks mean"),
      node(
        "p",
        "",
        "Source excerpts identify quoted passages. Review covers the stated rubric; completeness requires checking the original material. Self-ratings record your own assessment. Held-out questions stay outside the guide.",
      ),
    );
    add(host, boundary);
  }
  function render() {
    host.replaceChildren();
    if (!bundle) {
      add(
        host,
        hero(
          "A LEARNING WORKBENCH",
          "No bundle loaded.",
          "Run the Lamina demo or export a build to place data.js beside this page.",
        ),
      );
      return;
    }
    if (state.view === "learn") renderLearn();
    if (state.view === "practice") renderPractice();
    if (state.view === "sources") renderSources();
    if (state.view === "coverage") renderCoverage();
  }
  nav.forEach((b) =>
    b.addEventListener("click", () => setView(b.dataset.view)),
  );
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && speech) {
      stopSpeech();
      render();
    }
  });
  window.addEventListener("hashchange", () => {
    const v = location.hash.slice(1);
    if (views.includes(v) && v !== state.view) setView(v, false);
  });
  const initial = location.hash.slice(1);
  if (views.includes(initial)) state.view = initial;
  nav.forEach((b) => {
    const active = b.dataset.view === state.view;
    b.classList.toggle("active", active);
    active
      ? b.setAttribute("aria-current", "page")
      : b.removeAttribute("aria-current");
  });
  renderDownloads();
  render();
})();
