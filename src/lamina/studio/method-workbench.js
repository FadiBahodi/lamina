/* Local custom-method workbench. Hosted pages show an editable, non-running example. */
(() => {
  "use strict";
  const host = document.getElementById("method-workbench");
  if (!host) return;
  const url = path => new URL(path, document.baseURI);
  const make = (tag, cls = "", value) => {
    const item = document.createElement(tag);
    if (cls) item.className = cls;
    if (value !== undefined) item.textContent = String(value);
    return item;
  };
  const state = { local: false, adapter: false, activeId: "", selected: "", receipt: null, poll: null, runMethod: null, runTask: null };
  const wrap = make("section", "mw-shell");
  const head = make("div", "mw-head");
  const title = make("div");
  title.append(make("span", "mw-kicker", "CUSTOM METHOD / LOCAL WORKBENCH"), make("h3", "", "Workflow definition"));
  const mode = make("span", "mw-mode", "Checking local availability…");
  head.append(title, mode);
  const lead = make("p", "mw-lead", "Start from the published incident-guide method or import your own. The method declares workers, dependencies, selected task fields, and expected results. Its instructions are sent only to the adapter you configure locally.");
  const top = make("div", "mw-top");
  const summary = make("div", "mw-summary");
  const starters = make("div", "mw-starters");
  const fixtureButton = make("button", "mw-button mw-button-secondary", "Load small example"); fixtureButton.type = "button";
  const briefButton = make("button", "mw-button mw-button-secondary", "Load technical brief"); briefButton.type = "button";
  starters.append(fixtureButton, briefButton);
  const importLabel = make("label", "mw-import");
  importLabel.append(make("span", "", "Import method JSON"));
  const file = make("input"); file.type = "file"; file.accept = ".json,application/json";
  importLabel.append(file);
  const download = make("button", "mw-button mw-button-secondary", "Download method"); download.type = "button";
  top.append(summary, starters, importLabel, download);
  const editors = make("div", "mw-editors");
  const methodField = make("label", "mw-editor");
  methodField.append(make("span", "mw-label", "METHOD JSON · TECHNICAL EDITOR"));
  const methodText = make("textarea"); methodText.spellcheck = false; methodText.rows = 21; methodText.setAttribute("aria-label", "Method JSON");
  methodField.append(methodText);
  const taskField = make("label", "mw-editor");
  taskField.append(make("span", "mw-label", "TASK JSON · INPUT FOR THIS RUN"));
  const taskText = make("textarea"); taskText.spellcheck = false; taskText.rows = 9; taskText.setAttribute("aria-label", "Task JSON");
  taskField.append(taskText);
  editors.append(methodField, taskField);
  const editorDisclosure = make("details", "mw-editor-disclosure");
  editorDisclosure.append(make("summary", "", "Edit method and task JSON"), editors);
  const graph = make("div", "mw-graph");
  const graphTitle = make("div", "mw-subhead"); graphTitle.append(make("span", "mw-label", "DEPENDENCY PREVIEW"), make("span", "mw-hint", "Select a node to inspect its work and record an observation."));
  const graphBody = make("div", "mw-graph-body"); graph.append(graphTitle, graphBody);
  const actions = make("div", "mw-actions");
  const validate = make("button", "mw-button mw-button-secondary", "Validate method"); validate.type = "button";
  const run = make("button", "mw-button mw-button-primary", "Run locally"); run.type = "button";
  const status = make("p", "mw-status"); status.setAttribute("role", "status"); status.setAttribute("aria-live", "polite");
  actions.append(validate, run, status);
  const result = make("div", "mw-result"); result.hidden = true;
  wrap.append(head, lead, top, graph, editorDisclosure, actions, result); host.replaceChildren(wrap);

  function message(value, error = false) { status.textContent = value; status.classList.toggle("error", error); }
  function parse(field, label) {
    try { const value = JSON.parse(field.value); if (!value || typeof value !== "object" || Array.isArray(value)) throw Error("must be a JSON object"); return value; }
    catch (err) { throw Error(`${label}: ${err.message}`); }
  }
  function current() { return parse(methodText, "Method JSON"); }
  function selectedNode(method) { return method.nodes?.find(n => n.id === state.selected) || method.nodes?.[0]; }
  function showSummary(method) {
    summary.replaceChildren();
    summary.append(make("strong", "", method.description || method.id || "Unnamed method"));
    const meta = make("p", "", `${method.family || "method"} / ${method.id || "id"} / version ${method.version || "?"}`);
    summary.append(meta);
    const scope = method.applicability || {};
    const conditions = make("details", "mw-conditions");
    conditions.append(make("summary", "", "Applicability and limits"));
    for (const [label, key] of [["Use when", "contexts"], ["Exclusions", "exclusions"], ["Limits", "limits"]]) {
      const items = scope[key];
      if (Array.isArray(items) && items.length) conditions.append(make("p", "", `${label}: ${items.join(" · ")}`));
    }
    summary.append(conditions);
  }
  function codeBlock(value) { const pre = make("pre", "mw-code"); pre.append(make("code", "", JSON.stringify(value, null, 2))); return pre; }
  function renderGraph() {
    graphBody.replaceChildren();
    let method;
    try { method = current(); }
    catch (err) { graphBody.append(make("p", "mw-graph-error", err.message)); return; }
    showSummary(method);
    if (!Array.isArray(method.nodes) || !method.nodes.length) { graphBody.append(make("p", "mw-graph-error", "Add nodes to preview the work graph.")); return; }
    if (!method.nodes.some(n => n.id === state.selected)) state.selected = method.nodes[0].id;
    const list = make("div", "mw-node-list");
    method.nodes.forEach(node => {
      const button = make("button", `mw-node${node.id === state.selected ? " selected" : ""}`);
      button.type = "button"; button.setAttribute("aria-pressed", String(node.id === state.selected));
      button.append(make("span", "mw-node-id", node.id), make("strong", "", node.role || "Untitled worker"));
      button.append(make("small", "", `AFTER ${node.depends_on?.length ? node.depends_on.join(", ") : "START"}`));
      button.append(make("small", "", `LANE ${node.lane || "?"} · TASK ${Array.isArray(node.task_keys) ? node.task_keys.join(", ") || "none" : "all fields"}`));
      button.addEventListener("click", () => { state.selected = node.id; renderGraph(); });
      list.append(button);
    });
    const detail = make("div", "mw-node-detail");
    const node = selectedNode(method);
    detail.append(make("span", "mw-label", "SELECTED WORKER"), make("h4", "", node.role || node.id));
    detail.append(make("p", "", node.instructions || "No instructions provided."));
    detail.append(make("div", "mw-detail-meta", `Depends on: ${node.depends_on?.join(", ") || "none"} · Lane: ${node.lane || "?"} · Task fields: ${Array.isArray(node.task_keys) ? node.task_keys.join(", ") || "none" : "all"}`));
    if (node.observation_ids?.length) detail.append(make("p", "mw-observation-ids", `Selected observations: ${node.observation_ids.join(", ")}`));
    graphBody.append(list, detail);
  }
  let editTimer;
  methodText.addEventListener("input", () => { clearTimeout(editTimer); editTimer = setTimeout(renderGraph, 220); });
  file.addEventListener("change", async () => {
    const selected = file.files?.[0]; if (!selected) return;
    try {
      if (selected.size > 250000) throw Error("Method file exceeds 250 KB.");
      const value = JSON.parse(await selected.text());
      if (!value || typeof value !== "object" || Array.isArray(value)) throw Error("Expected a JSON object.");
      methodText.value = JSON.stringify(value, null, 2); state.selected = ""; renderGraph(); message("Method loaded. Validate it before running.");
    } catch (err) { message(`Import failed: ${err.message}`, true); }
    file.value = "";
  });
  let fixture = null;
  fixtureButton.addEventListener("click", () => {
    if (!fixture) return;
    const starter = structuredClone(fixture.method);
    for (const node of starter.nodes || []) node.observation_ids = [];
    starter.version = "1.0";
    methodText.value = JSON.stringify(starter, null, 2);
    taskText.value = JSON.stringify(fixture.task.initial, null, 2);
    state.selected = ""; renderGraph(); message("Small example loaded. This starter has no fixture-only observation reference.");
  });
  briefButton.addEventListener("click", async () => {
    briefButton.disabled = true; message("Loading technical brief method…");
    try {
      const [methodResponse, taskResponse] = await Promise.all([fetch(url("assets/technical-brief.json")), fetch(url("assets/technical-brief-task.json"))]);
      if (!methodResponse.ok || !taskResponse.ok) throw Error("Technical brief example is unavailable in this site build.");
      methodText.value = JSON.stringify(await methodResponse.json(), null, 2);
      taskText.value = JSON.stringify(await taskResponse.json(), null, 2);
      state.selected = ""; renderGraph(); message("Technical brief loaded. Validate it and review the inputs before running.");
    } catch (err) { message(err.message, true); }
    finally { briefButton.disabled = false; }
  });
  download.addEventListener("click", () => {
    try {
      const value = current(); const data = new Blob([JSON.stringify(value, null, 2) + "\n"], {type:"application/json"});
      const objectUrl = URL.createObjectURL(data); const a = make("a"); a.href = objectUrl; a.download = `${value.id || "lamina-method"}.json`; document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(objectUrl), 30000);
    } catch (err) { message(err.message, true); }
  });
  async function post(path, body) {
    const response = await fetch(url(path), {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body)});
    let data; try { data = await response.json(); } catch { throw Error(`HTTP ${response.status}: no JSON response`); }
    if (!response.ok) throw Error(data.error || data.message || `HTTP ${response.status}`);
    return data;
  }
  validate.addEventListener("click", async () => {
    let method; try { method = current(); parse(taskText, "Task JSON"); } catch (err) { message(err.message, true); return; }
    if (!state.local) { message("JSON parses. Full method validation requires the local app."); return; }
    validate.disabled = true; message("Validating method…");
    try {
      const data = await post("api/methods/validate", {method});
      if (data.method) methodText.value = JSON.stringify(data.method, null, 2);
      renderGraph(); message("Method validated by the local server.");
    } catch (err) { message(`Validation failed: ${err.message}`, true); }
    finally { validate.disabled = false; }
  });
  function receiptView(runData) {
    result.hidden = false; result.replaceChildren();
    result.append(make("span", "mw-label", "ACTUAL RUN RESULT"));
    result.append(make("h4", "", `${state.runMethod?.id || "Method"} · ${runData.status || "unknown"}`));
    if (runData.error) result.append(make("p", "mw-graph-error", runData.error));
    const receipt = runData.receipt || runData.result?.receipt || runData.result;
    if (receipt && typeof receipt === "object") {
      state.receipt = receipt;
      const rows = make("div", "mw-receipt-rows");
      const nodes = receipt.nodes || {};
      Object.entries(nodes).forEach(([id, row]) => {
        const item = make("div", "mw-receipt-row");
        item.append(make("strong", "", id), make("span", "", row.status || "unknown"));
        const declared = state.runMethod?.nodes?.find(node => node.id === id);
        if (declared && state.runTask) {
          const chosen = Array.isArray(declared.task_keys)
            ? Object.fromEntries(declared.task_keys.filter(key => Object.hasOwn(state.runTask, key)).map(key => [key, state.runTask[key]]))
            : state.runTask;
          item.append(make("small", "mw-declared-label", "SUBMITTED TASK FIELDS & DEPENDENCIES"));
          item.append(codeBlock({task:chosen, depends_on:declared.depends_on || [], fixed_input:declared.input || {}, selected_observation_ids:declared.observation_ids || []}));
        }
        if (receipt.results && Object.hasOwn(receipt.results, id)) { item.append(make("small", "mw-declared-label", "ACTUAL RETURNED RESULT")); item.append(codeBlock(receipt.results[id])); }
        rows.append(item);
      });
      result.append(rows);
    }
    const path = runData.outputs?.receipt;
    if (typeof path === "string" && path.startsWith("/outputs/") && !path.includes("\\")) {
      const a = make("a", "mw-download", "Download receipt"); a.href = url(path); result.append(a);
    }
    if (runData.status === "ready" && state.receipt) showObservationForm();
  }
  async function poll(id) {
    clearTimeout(state.poll);
    try {
      const response = await fetch(url(`api/runs/${encodeURIComponent(id)}`), {cache:"no-store"});
      const data = await response.json();
      if (!response.ok) throw Error(data.error || `HTTP ${response.status}`);
      receiptView(data);
      if (data.status === "queued" || data.status === "running") state.poll = setTimeout(() => poll(id), 2000);
      else { run.disabled = false; message(data.status === "ready" ? "Run complete. Inspect the actual results below." : `Run ${data.status}.`, data.status !== "ready"); }
    } catch (err) { run.disabled = false; message(`Could not read run state: ${err.message}`, true); }
  }
  run.addEventListener("click", async () => {
    let method, task; try { method = current(); task = parse(taskText, "Task JSON"); } catch (err) { message(err.message, true); return; }
    if (!state.local || !state.adapter) { message("Run locally with a configured adapter to execute this method.", true); return; }
    run.disabled = true; state.receipt = null; state.runMethod = structuredClone(method); state.runTask = structuredClone(task); message("Submitting method run…");
    try { const data = await post("api/method-runs", {method, task}); if (!data.id) throw Error("Server returned no run ID."); state.activeId = data.id; receiptView(data); poll(data.id); }
    catch (err) { run.disabled = false; message(`Run failed: ${err.message}`, true); }
  });
  function showObservationForm() {
    const section = make("div", "mw-observation");
    section.append(make("span", "mw-label", "REOPEN SELECTED WORKER"), make("h5", "", "Record an operator observation"));
    section.append(make("p", "", "The note is stored with this run. Its returned ID is added only to the selected node in the method editor. Review the change, then run again explicitly."));
    const note = make("textarea"); note.rows = 3; note.placeholder = "What was missing, wrong, or useful?"; note.setAttribute("aria-label", "Observation note");
    const outcome = make("input"); outcome.placeholder = "Outcome, e.g. needs revision"; outcome.setAttribute("aria-label", "Observation outcome");
    const applicability = make("input"); applicability.placeholder = "When does this observation apply?"; applicability.setAttribute("aria-label", "Observation applicability");
    const save = make("button", "mw-button mw-button-secondary", "Save note for selected worker"); save.type = "button";
    const feedback = make("p", "mw-note-feedback"); feedback.setAttribute("role", "status");
    section.append(note, outcome, applicability, save, feedback); result.append(section);
    save.addEventListener("click", async () => {
      if (!state.activeId || !state.selected || !state.receipt?.nodes?.[state.selected]) { feedback.textContent = "Select a worker from this run first."; return; }
      if (!note.value.trim() || !outcome.value.trim() || !applicability.value.trim()) { feedback.textContent = "Enter a note, outcome, and applicability."; return; }
      let method;
      try {
        method = current();
        if (method.family !== state.runMethod?.family || method.id !== state.runMethod?.id || !method.nodes?.some(node => node.id === state.selected))
          throw Error("The editor no longer matches this run's method. Restore it before adding an observation.");
      } catch (err) { feedback.textContent = err.message; return; }
      save.disabled = true; feedback.textContent = "Saving observation…";
      try {
        const data = await post("api/method-observations", {run_id:state.activeId, node_id:state.selected, note:note.value.trim(), outcome:outcome.value.trim(), applicability:applicability.value.trim()});
        if (!data.observation_id) throw Error("Server returned no observation ID.");
        const node = method.nodes.find(n => n.id === state.selected);
        if (!node) throw Error("Selected worker is no longer in the method editor.");
        node.observation_ids = [...new Set([...(node.observation_ids || []), data.observation_id])];
        methodText.value = JSON.stringify(method, null, 2); renderGraph();
        feedback.textContent = `Observation ${data.observation_id} saved and selected for ${node.id}. Review the method, then choose Run locally.`;
      } catch (err) { feedback.textContent = `Could not save: ${err.message}`; }
      finally { save.disabled = false; }
    });
  }
  async function initialize() {
    try {
      const [exampleResponse, statusResponse] = await Promise.allSettled([
        fetch(url("method-example.json"), {cache:"no-store"}),
        fetch(url("api/status"), {cache:"no-store"}),
      ]);
      if (exampleResponse.status !== "fulfilled" || !exampleResponse.value.ok) throw Error("Published method example unavailable.");
      const example = await exampleResponse.value.json(); fixture = example;
      const starter = structuredClone(example.method);
      // The published trace refers to an observation in its temporary fixture store.
      // A new local run starts without that external observation reference.
      for (const node of starter.nodes || []) node.observation_ids = [];
      starter.version = "1.0";
      methodText.value = JSON.stringify(starter, null, 2);
      taskText.value = JSON.stringify(example.task.initial, null, 2);
      renderGraph();
      if (statusResponse.status === "fulfilled" && statusResponse.value.ok) {
        const statusData = await statusResponse.value.json();
        state.local = statusData.mode === "local"; state.adapter = Boolean(statusData.adapter_configured);
      }
      mode.textContent = state.local ? (state.adapter ? "LOCAL / ADAPTER READY" : "LOCAL / ADAPTER REQUIRED") : "HOSTED / EDIT & DOWNLOAD";
      run.disabled = !state.local || !state.adapter;
      message(state.local ? (state.adapter ? "Ready to validate and run with your configured adapter." : "Configure a local adapter to run. You can still edit, validate, and download.") : "This hosted page does not execute models. Edit or download a method; run it with the local app.");
    } catch (err) { mode.textContent = "EXAMPLE UNAVAILABLE"; run.disabled = true; message(err.message, true); }
  }
  initialize();
})();
