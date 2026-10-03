/* Lamina: local fixed-format document builder and procedure editor. */
(() => {
  "use strict";

  const ROOT = new URL("./", document.baseURI);
  const OUTPUTS = ["study-guide", "samp", "oral-case", "audio-script"];
  const OUTPUT_LABELS = {
    "study-guide": "Study guide",
    samp: "Practice exam",
    "oral-case": "Oral scenario",
    "audio-script": "Audio script",
  };
  const GLYPHS = {
    "study-guide": "§",
    samp: "∑",
    "oral-case": "↗",
    "audio-script": "♫",
  };
  const DEFAULTS = [
    {
      schema_version: "1",
      id: "study-guide",
      name: "Study guide",
      description:
        "Build a source-grounded concept sequence with explanations, recall, contrast, and application.",
      audience: "Independent learners",
      instructions:
        "Extract atomic concepts with exact source evidence. Merge equivalent ideas without losing distinct claims. Sequence lessons by dependency. Explain the material and choose useful practice forms; retain evidence for each claim.",
      outputs: ["study-guide"],
      workers: 4,
    },
    {
      schema_version: "1",
      id: "samp-assessment",
      name: "Practice exam",
      description:
        "Write progressive short-answer problems with staged information, marking points, and source evidence.",
      audience: "Candidates and examiners",
      instructions:
        "Generate progressive problems from the source-grounded curriculum. Each step reveals new information and requires a decision. Keep answer points, marks, critical errors, and evidence inspectable for an examiner.",
      outputs: ["samp"],
      workers: 4,
    },
    {
      schema_version: "1",
      id: "oral-scenario",
      name: "Oral scenario",
      description:
        "Create a candidate brief, private examiner findings, second event, and debrief.",
      audience: "Candidates and examiners",
      instructions:
        "Write a case packet with a short candidate brief. Put requestable findings in the examiner sheet. Add a staged second event, reassessment prompt, source-grounded checklist, and debrief.",
      outputs: ["oral-case"],
      workers: 4,
    },
    {
      schema_version: "1",
      id: "audio-script",
      name: "Audio script",
      description:
        "Write a podcast script with explanations and pauses for recall.",
      audience: "Audio learners and narrators",
      instructions:
        "Transform the lesson sequence into a speakable script. Use concise explanations, examples, and retrieval pauses. Keep the script grounded in source evidence; do not claim audio synthesis or delivery evaluation.",
      outputs: ["audio-script"],
      workers: 4,
    },
  ];
  const state = {
    view: "workflows",
    mode: "disconnected",
    adapter: false,
    serverSources: [],
    files: [],
    procedures: DEFAULTS,
    selected: DEFAULTS[0].id,
    run: null,
    poll: null,
  };
  const $ = (s, root = document) => root.querySelector(s);
  const $$ = (s, root = document) => Array.from(root.querySelectorAll(s));
  function node(tag, className, content) {
    const x = document.createElement(tag);
    if (className) x.className = className;
    if (content !== undefined) x.textContent = String(content);
    return x;
  }
  function add(parent, ...children) {
    children.forEach((c) => c && parent.appendChild(c));
    return parent;
  }
  function clear(parent) {
    parent.replaceChildren();
    return parent;
  }
  function trim(s, n = 320) {
    s = String(s || "").trim();
    return s.length > n ? s.slice(0, n - 1).trimEnd() + "…" : s;
  }
  function currentProcedure() {
    return (
      state.procedures.find((p) => p.id === state.selected) ||
      state.procedures[0]
    );
  }
  function displayProcedureName(p) {
    return /samp/i.test(p.name) ? "Practice exam" : p.name;
  }
  function linkFor(path) {
    if (
      typeof path !== "string" ||
      !path ||
      path.startsWith("//") ||
      /^[a-z][a-z\d+.-]*:/i.test(path) ||
      path.includes("\\")
    )
      return null;
    try {
      const u = new URL(path, location.origin);
      return u.origin === location.origin && u.pathname.startsWith("/outputs/")
        ? u.href
        : null;
    } catch {
      return null;
    }
  }
  async function getJSON(path) {
    const response = await fetch(new URL(path, ROOT), { cache: "no-store" });
    if (!response.ok) throw Error(`HTTP ${response.status}`);
    return response.json();
  }
  function errorMessage(e) {
    return e instanceof Error ? e.message : String(e);
  }

  function showView(view) {
    if (!["workflows", "studio", "procedures"].includes(view)) view = "workflows";
    state.view = view;
    document.body.classList.add("subview");
    $$(".nav-link").forEach((b) => {
      const yes = b.dataset.view === view;
      b.classList.toggle("is-active", yes);
      if (yes) b.setAttribute("aria-current", "page");
      else b.removeAttribute("aria-current");
    });
    $$(".view").forEach((p) => {
      const yes = p.id === `view-${view}`;
      p.hidden = !yes;
      p.classList.toggle("is-active", yes);
    });
    if (view === "procedures") renderInspector();
    if (view === "studio") {
      getJSON("api/status").then(status => {
        state.mode = status.mode;
        state.adapter = Boolean(status.adapter_configured);
        state.serverSources = Array.isArray(status.sources) ? status.sources : [];
        updateMode();
      }).catch(() => { state.mode = "disconnected"; updateMode(); });
    }
    window.dispatchEvent(new CustomEvent("lamina:view", {detail:view}));
    const title = $(`#view-${view} h1, #view-${view} h2`);
    if (title) {
      title.setAttribute("tabindex", "-1");
      title.focus({ preventScroll: true });
    }
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
  function validateProcedure(value) {
    const exact = [
      "schema_version",
      "id",
      "name",
      "description",
      "audience",
      "instructions",
      "outputs",
      "workers",
    ];
    if (
      !value ||
      typeof value !== "object" ||
      Array.isArray(value) ||
      Object.keys(value).some((k) => !exact.includes(k)) ||
      exact.some((k) => !Object.hasOwn(value, k))
    )
      throw Error("Procedure must contain only the eight documented fields.");
    for (const k of [
      "schema_version",
      "id",
      "name",
      "description",
      "audience",
      "instructions",
    ])
      if (typeof value[k] !== "string") throw Error(`${k} must be text.`);
    if (
      value.schema_version !== "1" ||
      !/^[a-z][a-z0-9-]{0,47}$/.test(value.id)
    )
      throw Error(
        "Use schema_version 1 and a lowercase hyphenated id (48 characters maximum).",
      );
    for (const [k, limit] of [
      ["name", 100],
      ["description", 500],
      ["audience", 300],
      ["instructions", 4000],
    ])
      if (
        !value[k].trim() ||
        value[k].length > limit ||
        value[k].includes("\0")
      )
        throw Error(`${k} must be nonempty and under ${limit} characters.`);
    if (
      !Array.isArray(value.outputs) ||
      !value.outputs.length ||
      value.outputs.length > 4 ||
      new Set(value.outputs).size !== value.outputs.length ||
      value.outputs.some((x) => !OUTPUTS.includes(x))
    )
      throw Error(
        "Outputs must be a unique, nonempty list of supported output names.",
      );
    if (
      !Number.isInteger(value.workers) ||
      value.workers < 1 ||
      value.workers > 16
    )
      throw Error("workers must be an integer from 1 to 16.");
    return value;
  }
  function procedureDownload(p) {
    const content = JSON.stringify(p, null, 2) + "\n";
    const url = URL.createObjectURL(
      new Blob([content], { type: "application/json" }),
    );
    const a = node("a");
    a.href = url;
    a.download = `${p.id}.procedure.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 30000);
  }
  function selectProcedure(id) {
    if (!state.procedures.some((p) => p.id === id)) return;
    state.selected = id;
    renderProcedures();
    renderOutput();
    renderInspector();
    updateRunControl();
  }
  function renderProcedures() {
    const choices = clear($("#procedure-choices")),
      library = clear($("#procedure-library"));
    state.procedures.forEach((p) => {
      const active = p.id === state.selected,
        output = p.outputs[0],
        choice = node("button", "procedure-choice");
      choice.type = "button";
      choice.setAttribute("role", "radio");
      choice.setAttribute("aria-checked", String(active));
      choice.setAttribute("aria-label", displayProcedureName(p));
      add(
        choice,
        node("span", "choice-glyph", GLYPHS[output] || "◇"),
        node("strong", "", displayProcedureName(p)),
      );
      choice.addEventListener("click", () => selectProcedure(p.id));
      choices.appendChild(choice);
      const item = node("button", `library-card${active ? " active" : ""}`);
      item.type = "button";
      add(
        item,
        node("span", "library-glyph", GLYPHS[output] || "◇"),
        add(
          node("span"),
          node("strong", "", displayProcedureName(p)),
          node("small", "", trim(p.description, 94)),
        ),
      );
      item.addEventListener("click", () => selectProcedure(p.id));
      library.appendChild(item);
    });
    const p = currentProcedure();
    clear($("#selected-procedure"));
    add(
      $("#selected-procedure"),
      node("strong", "", displayProcedureName(p)),
      node("p", "", p.description),
      node(
        "div",
        "procedure-meta",
        `${p.outputs.map((o) => OUTPUT_LABELS[o]).join(" · ")}  /  ${p.workers} workers`,
      ),
      node(
        "p",
        "procedure-shared",
        "Each run includes the shared lesson bundle and reader; the selected procedure adds its specialized artifact.",
      ),
    );
  }
  function renderOutput() {
    const p = currentProcedure(),
      list = clear($("#output-list"));
    $("#output-description").textContent = p.description;
    OUTPUTS.forEach((name) => {
      const selected = p.outputs.includes(name),
        row = node("div", `output-row${selected ? " active" : ""}`);
      add(
        row,
        node("span", "", GLYPHS[name]),
        node("b", "", OUTPUT_LABELS[name]),
        node("small", "", selected ? "Selected" : "Available"),
      );
      list.appendChild(row);
    });
    renderOutputPreview();
  }
  function renderOutputPreview() {
    const box = clear($("#output-preview"));
    const run = state.run;
    if (!run) {
      box.appendChild(node("p", "", "Your completed run and export links will appear here."));
      return;
    }
    box.appendChild(node("p", "", `Run ${run.id || ""} · ${run.status || "unknown"}`));
    if (run.status === "ready" && run.outputs) {
      Object.entries(run.outputs).forEach(([name, path]) => {
        const href = linkFor(path);
        if (!href) return;
        const a = node("a", "", name.replaceAll("_", " "));
        a.href = href;
        box.appendChild(a);
        box.appendChild(node("br"));
      });
    }
  }
  function persistProcedures() {
    try {
      localStorage.setItem(
        "lamina-studio-procedures-v1",
        JSON.stringify(state.procedures),
      );
    } catch {}
  }
  function renderInspector() {
    const p = currentProcedure(),
      box = clear($("#procedure-inspector"));
    add(
      box,
      node("span", "section-index", "PROCEDURE / PORTABLE JSON"),
      node("h3", "", displayProcedureName(p)),
      node("p", "", p.description),
    );
    const grid = node("div", "inspector-grid");
    [
      ["Audience", p.audience],
      ["Outputs", p.outputs.map((x) => OUTPUT_LABELS[x]).join(", ")],
      ["Parallel workers", p.workers],
      ["Schema", p.schema_version],
    ].forEach(([a, b]) =>
      add(
        grid,
        add(node("div"), node("span", "small-label", a), node("strong", "", b)),
      ),
    );
    box.appendChild(grid);
    add(
      box,
      node("span", "small-label", "AUTHORING INSTRUCTIONS"),
      node("div", "instructions", p.instructions),
    );
    const actions = node("div", "source-actions"),
      download = node("button", "button button-secondary", "Download JSON ↓"),
      use = node("button", "text-button", "Use in Build →");
    download.type = use.type = "button";
    download.addEventListener("click", () =>
      procedureDownload(currentProcedure()),
    );
    use.addEventListener("click", () => showView("studio"));
    add(actions, download, use);
    box.appendChild(actions);
    const details = node("details", "procedure-edit"),
      summary = node("summary", "", "Edit this procedure in your browser");
    details.appendChild(summary);
    const form = node("form", "procedure-form");
    form.noValidate = true;
    function field(label, key, multiline = false) {
      const wrap = node("label", "form-field"),
        name = node("span", "", label),
        input = node(multiline ? "textarea" : "input");
      input.name = key;
      input.value = p[key];
      input.required = true;
      if (multiline) input.rows = key === "instructions" ? 7 : 3;
      else input.type = "text";
      add(wrap, name, input);
      return wrap;
    }
    add(
      form,
      field("Procedure ID · lowercase slug", "id"),
      field("Name", "name"),
      field("Description", "description", true),
      field("Audience", "audience"),
      field("Instructions", "instructions", true),
    );
    const out = node("fieldset", "output-fieldset");
    out.appendChild(node("legend", "", "Outputs"));
    OUTPUTS.forEach((o) => {
      const label = node("label"),
        check = node("input");
      check.type = "checkbox";
      check.name = "output";
      check.value = o;
      check.checked = p.outputs.includes(o);
      add(label, check, node("span", "", OUTPUT_LABELS[o]));
      out.appendChild(label);
    });
    form.appendChild(out);
    const workers = field("Parallel workers · 1–16", "workers");
    $("input", workers).type = "number";
    $("input", workers).min = "1";
    $("input", workers).max = "16";
    form.appendChild(workers);
    const save = node("button", "button button-primary", "Save procedure");
    save.type = "submit";
    const note = node("p", "inline-note");
    add(form, save, note);
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      try {
        const candidate = validateProcedure({
          schema_version: "1",
          id: form.elements.namedItem("id").value.trim(),
          name: form.elements.namedItem("name").value,
          description: form.elements.namedItem("description").value,
          audience: form.elements.namedItem("audience").value,
          instructions: form.elements.namedItem("instructions").value,
          outputs: $$('input[name="output"]:checked', form).map((x) => x.value),
          workers: Number(form.elements.namedItem("workers").value),
        });
        const old = state.procedures.findIndex((x) => x.id === p.id),
          duplicate = state.procedures.findIndex((x) => x.id === candidate.id);
        if (duplicate >= 0 && duplicate !== old)
          throw Error("That procedure ID already exists. Choose a unique ID.");
        if (candidate.id === p.id) state.procedures[old] = candidate;
        else state.procedures.push(candidate);
        persistProcedures();
        state.selected = candidate.id;
        renderProcedures();
        renderOutput();
        renderInspector();
        $("#import-note").textContent =
          `Saved ${candidate.name} in this browser. Download the JSON for a copy.`;
      } catch (err) {
        note.textContent = `Could not save: ${errorMessage(err)}`;
      }
    });
    details.appendChild(form);
    box.appendChild(details);
  }

  function updateMode() {
    const local = state.mode === "local",
      pill = $("#mode-pill");
    pill.textContent = local
      ? "Local build available"
      : "Local server unavailable";
    pill.classList.toggle("local", local);
    $("#mode-description").textContent = local
      ? state.adapter
        ? "Adapter ready. You can run this workflow with local sources."
        : "Connect a command adapter to run this workflow."
      : "The local server could not be reached. Start lamina app and reload this page.";
    $("#submit-sources").disabled = !local || !state.files.length;
    $("#sources-note").textContent = local
      ? state.files.length
        ? "Files are sent to the local server only when you choose Store sources."
        : `${state.serverSources.length} source${state.serverSources.length === 1 ? "" : "s"} stored locally.`
      : "Files selected here stay in this browser. Run locally to store and process them.";
    $("#source-input").accept = local
      ? ".md,.txt,.pdf,text/plain,text/markdown,application/pdf"
      : ".md,.txt,text/plain,text/markdown";
    $("#source-hint").textContent = local
      ? "Choose or drop .md, .txt, or .pdf files"
      : "Choose or drop .md and .txt files · PDF import requires the local server";
    updateRunControl();
  }
  function updateRunControl() {
    const b = $("#run-button"),
      g = $("#run-guidance");
    if (state.mode !== "local") {
      b.textContent = "Local server unavailable";
      b.disabled = true;
      g.textContent = "Start lamina app and reload this page to run a project.";
      return;
    }
    if (!state.adapter) {
      b.textContent = "Configure adapter to run";
      b.disabled = true;
      g.textContent =
        'Start the local server with lamina app --adapter @models.json. See Documentation for model setup.';
      return;
    }
    if (!state.serverSources.length) {
      b.textContent = "Store sources to begin";
      b.disabled = true;
      g.textContent =
        "Select .md or .txt files above and store them on the local server first.";
      return;
    }
    if (state.run && ["queued", "running"].includes(state.run.status)) {
      b.textContent = "Production in progress";
      b.disabled = true;
      g.textContent = "Progress appears below.";
      return;
    }
    b.textContent = `Run ${currentProcedure().name} →`;
    b.disabled = false;
    g.textContent = `Runs locally on ${state.serverSources.length} stored source${state.serverSources.length === 1 ? "" : "s"}.`;
  }

  function renderFiles() {
    const list = clear($("#source-list"));
    if (!state.files.length) {
      list.appendChild(
        node(
          "p",
          "empty-small",
          "No local files selected. Add files above to begin.",
        ),
      );
      updateMode();
      return;
    }
    state.files.forEach((file, i) => {
      const row = node("div", "source-item");
      const icon = node("span", "choice-glyph", "▤");
      const title = add(
        node("div"),
        node("strong", "", file.name),
        node(
          "small",
          "",
          `${((file.size ?? file.text?.length ?? 0) / 1024).toFixed(1)} KB · ${file.role}${file.base64 ? " · PDF preview unavailable" : ""}`,
        ),
      );
      const remove = node("button", "", "Remove");
      remove.type = "button";
      remove.setAttribute("aria-label", `Remove ${file.name}`);
      remove.addEventListener("click", () => {
        state.files.splice(i, 1);
        renderFiles();
      });
      add(row, icon, title, remove);
      list.appendChild(row);
      if (file.text !== undefined) {
        const details = node("details"),
          summary = node("summary", "", "Preview source text");
        add(
          details,
          summary,
          node("pre", "source-preview", trim(file.text, 2200)),
        );
        list.appendChild(details);
      }
    });
    updateMode();
  }
  function readPDF(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onerror = () => reject(Error("PDF could not be read"));
      reader.onload = () => {
        const data = String(reader.result || "");
        const comma = data.indexOf(",");
        if (comma < 0) reject(Error("PDF encoding failed"));
        else resolve(data.slice(comma + 1));
      };
      reader.readAsDataURL(file);
    });
  }
  async function readFiles(files) {
    const accepted = [],
      errors = [];
    for (const file of files) {
      if (
        !/^[A-Za-z0-9][A-Za-z0-9._ -]{0,119}\.(md|txt|pdf)$/i.test(file.name)
      ) {
        errors.push(`${file.name} has an unsupported name or type.`);
        continue;
      }
      const pdf = /\.pdf$/i.test(file.name);
      if (pdf && state.mode !== "local") {
        errors.push(
          "PDF import requires the local server or CLI.",
        );
        continue;
      }
      if (file.size > (pdf ? 5_000_000 : 2 * 1024 * 1024)) {
        errors.push(
          `${file.name} exceeds the ${pdf ? "5 MB PDF" : "2 MB text preview"} limit.`,
        );
        continue;
      }
      try {
        accepted.push(
          pdf
            ? {
                name: file.name,
                base64: await readPDF(file),
                role: "teaching",
                size: file.size,
              }
            : {
                name: file.name,
                text: await file.text(),
                role: "teaching",
                size: file.size,
              },
        );
      } catch (e) {
        errors.push(`Could not read ${file.name}: ${errorMessage(e)}`);
      }
    }
    state.files.push(...accepted);
    renderFiles();
    if (errors.length) setNote(errors.join(" "));
  }
  function setNote(message) {
    $("#sources-note").textContent = message;
  }
  async function submitSources() {
    if (state.mode !== "local" || !state.files.length) return;
    const b = $("#submit-sources");
    b.disabled = true;
    setNote("Storing sources on the local server…");
    try {
      const files = state.files.map((file) =>
        file.base64
          ? { name: file.name, base64: file.base64, role: file.role }
          : { name: file.name, text: file.text, role: file.role },
      );
      const res = await fetch(new URL("api/sources", ROOT), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ files }),
      });
      const data = await res.json();
      if (!res.ok) throw Error(data.error || `HTTP ${res.status}`);
      state.serverSources = Array.isArray(data.sources)
        ? data.sources
        : state.serverSources;
      state.files = [];
      renderFiles();
      setNote(
        `${data.count ?? state.serverSources.length} source${(data.count ?? state.serverSources.length) === 1 ? "" : "s"} stored on the local server.`,
      );
    } catch (e) {
      setNote(`Source upload failed: ${errorMessage(e)}`);
      b.disabled = false;
    }
    updateRunControl();
  }
  function renderRun() {
    const box = $("#run-status"),
      run = state.run;
    if (!run) {
      box.hidden = true;
      return;
    }
    box.hidden = false;
    box.classList.toggle("error", run.status === "failed");
    clear(box);
    add(
      box,
      node("strong", "", `Run ${run.id || ""} · ${run.status || "unknown"}`),
    );
    if (run.error) add(box, node("p", "", run.error));
    if (run.status === "ready" && run.outputs) {
      const rows = node("div");
      Object.entries(run.outputs).forEach(([name, path]) => {
        const href = linkFor(path);
        if (!href) return;
        const a = node("a", "", name.replaceAll("_", " "));
        a.href = href;
        rows.appendChild(a);
      });
      box.appendChild(rows);
    }
    renderOutputPreview();
    updateRunControl();
  }
  async function pollRun(id) {
    if (state.poll) clearTimeout(state.poll);
    try {
      const run = await getJSON(`api/runs/${encodeURIComponent(id)}`);
      state.run = run;
      renderRun();
      if (["queued", "running"].includes(run.status))
        state.poll = setTimeout(() => pollRun(id), 2000);
    } catch (e) {
      state.run = {
        id,
        status: "failed",
        error: `Could not read run state: ${errorMessage(e)}`,
      };
      renderRun();
    }
  }
  async function startRun() {
    if (state.mode !== "local") return;
    if (!state.adapter || !state.serverSources.length) return;
    const b = $("#run-button");
    b.disabled = true;
    try {
      const res = await fetch(new URL("api/runs", ROOT), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ procedure: currentProcedure() }),
      });
      const data = await res.json();
      if (!res.ok) throw Error(data.error || `HTTP ${res.status}`);
      if (typeof data.id !== "string")
        throw Error("The server did not return a run id.");
      state.run = { id: data.id, status: data.status || "queued" };
      renderRun();
      pollRun(data.id);
    } catch (e) {
      state.run = { id: "", status: "failed", error: errorMessage(e) };
      renderRun();
    }
  }

  async function initialize() {
    $$("[data-view]").forEach((b) =>
      b.addEventListener("click", () => showView(b.dataset.view)),
    );
    $("#source-input").addEventListener("change", (e) => {
      readFiles(e.target.files);
      e.target.value = "";
    });
    const drop = $("#dropzone");
    drop.addEventListener("dragover", (e) => {
      e.preventDefault();
      drop.classList.add("drag-over");
    });
    drop.addEventListener("dragleave", () =>
      drop.classList.remove("drag-over"),
    );
    drop.addEventListener("drop", (e) => {
      e.preventDefault();
      drop.classList.remove("drag-over");
      readFiles(e.dataTransfer.files);
    });
    $("#submit-sources").addEventListener("click", submitSources);
    $("#run-button").addEventListener("click", startRun);
    $("#download-selected").addEventListener("click", () =>
      procedureDownload(currentProcedure()),
    );
    $("#procedure-input").addEventListener("change", async (e) => {
      const file = e.target.files?.[0];
      if (!file) return;
      const note = $("#import-note");
      try {
        if (file.size > 100 * 1024)
          throw Error("Procedure JSON must be under 100 KB.");
        const p = validateProcedure(JSON.parse(await file.text()));
        const index = state.procedures.findIndex((x) => x.id === p.id);
        if (index >= 0) state.procedures[index] = p;
        else state.procedures.push(p);
        persistProcedures();
        selectProcedure(p.id);
        note.textContent = `Imported ${p.name} in this browser. Download it to keep a copy.`;
      } catch (err) {
        note.textContent = `Import rejected: ${errorMessage(err)}`;
      }
      e.target.value = "";
    });
    renderProcedures();
    renderOutput();
    renderFiles();
    const loaded = await Promise.allSettled([
      getJSON("api/status"),
      getJSON("api/procedures"),
      getJSON("procedures.json"),
    ]);
    if (loaded[0].status === "fulfilled" && loaded[0].value?.mode === "local") {
      const status = loaded[0].value;
      state.mode = "local";
      state.adapter = Boolean(status.adapter_configured);
      state.serverSources = Array.isArray(status.sources) ? status.sources : [];
      if (status.active_run?.id) pollRun(status.active_run.id);
    }
    const localProcedures =
        loaded[1].status === "fulfilled" ? loaded[1].value?.procedures : null,
      staticProcedures =
        loaded[2].status === "fulfilled" ? loaded[2].value : null;
    const incoming = Array.isArray(localProcedures)
      ? localProcedures
      : Array.isArray(staticProcedures)
        ? staticProcedures
        : staticProcedures?.procedures;
    if (Array.isArray(incoming) && incoming.length) {
      const valid = [];
      incoming.forEach((p) => {
        try {
          valid.push(validateProcedure(p));
        } catch {}
      });
      if (valid.length) state.procedures = valid;
    }
    try {
      const saved = JSON.parse(
        localStorage.getItem("lamina-studio-procedures-v1") || "[]",
      );
      if (Array.isArray(saved) && saved.length < 100)
        saved.forEach((item) => {
          try {
            const p = validateProcedure(item),
              index = state.procedures.findIndex((x) => x.id === p.id);
            if (index >= 0) state.procedures[index] = p;
            else state.procedures.push(p);
          } catch {}
        });
    } catch {}
    if (!state.procedures.some((p) => p.id === state.selected))
      state.selected = state.procedures[0].id;
    renderProcedures();
    renderOutput();
    renderInspector();
    updateMode();
  }
  initialize();
})();
