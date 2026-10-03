/* Goal-first production UI. All result text is inserted as text nodes. */
(() => {
  "use strict";
  const host = document.getElementById("production-workbench");
  if (!host) return;
  const make = (tag, cls = "", value) => { const x = document.createElement(tag); if (cls) x.className = cls; if (value !== undefined) x.textContent = String(value); return x; };
  const route = path => new URL(path, document.baseURI);
  const statusLabel = value => ({queued:"Waiting to start",running:"In progress",ready:"Complete",review:"Needs review",failed:"Failed",interrupted:"Interrupted",passed:"Passed",completed:"Complete"}[value] || "Status unavailable");
  const state = { local: false, adapter: false, audioAdapter: false, sources: [], selected: new Set(), roles: new Map(), observations: [], selectedObservations: new Set(), runId: "", run: null, poll: null };
  const shell = make("div", "pb-shell");
  const form = make("div", "pb-form");
  const goalBlock = make("section", "pb-block");
  const goalHead = make("div", "pb-block-head"); goalHead.append(make("span", "pb-step", "01"), make("h3", "", "Describe the result"));
  const goal = make("textarea", "pb-goal"); goal.rows = 5; goal.placeholder = "Example: Turn these chapters and slides into a practical guide, with key decisions, exceptions and source references."; goal.setAttribute("aria-label", "Project goal");
  const formatLabel = make("label", "pb-field"); formatLabel.append(make("span", "", "Output"));
  const format = make("select"); format.setAttribute("aria-label", "Output format");
  [["document", "Document"], ["guide", "Reference guide"], ["assessment", "Practice exam"], ["podcast-script", "Podcast script"], ["cards", "Flashcards (sweep)"]].forEach(([value, label]) => { const option = make("option", "", label); option.value = value; format.append(option); });
  const formatNote=make("p","pb-format-note");
  function updateFormatNote(){formatNote.hidden=format.value!=="podcast-script";formatNote.textContent=state.audioAdapter?"Planned in episodes of about 20 minutes. Each section is spoken as soon as it is reviewed, and the episodes are assembled as audio through your connected speech service.":"Planned in episodes of about 20 minutes. Connect a speech service to also create audio for each episode.";}
  format.addEventListener("change",updateFormatNote);
  formatLabel.append(format); goalBlock.append(goalHead, goal, formatLabel,formatNote);updateFormatNote();
  const sourceBlock = make("section", "pb-block");
  const sourceHead = make("div", "pb-block-head"); sourceHead.append(make("span", "pb-step", "02"), make("h3", "", "Add your sources"));
  const sourceNote = make("p", "pb-explain", "Add your files, then choose which provide facts, background or examples of the format you want.");
  const sourceList = make("div", "pb-sources");
  const uploadLabel = make("label", "pb-upload"); uploadLabel.append(make("span", "", "Add .txt, .md, .pdf, or .pptx files"));
  const fileInput = make("input"); fileInput.type = "file"; fileInput.multiple = true; fileInput.accept = ".txt,.md,.pdf,.pptx,text/plain,text/markdown,application/pdf"; uploadLabel.append(fileInput);
  const uploadStatus = make("p", "pb-upload-status"); uploadStatus.setAttribute("role", "status");
  sourceBlock.append(sourceHead, sourceNote, sourceList, uploadLabel, uploadStatus);
  const capacityBlock = make("section", "pb-block");
  const capacityHead = make("div", "pb-block-head"); capacityHead.append(make("span", "pb-step", "03"), make("h3", "", "Processing settings"));
  const capacityIntro = make("p", "pb-explain", "Choose how many requests can run at once. Each section is reviewed after it is written.");
  const capacityFields = make("div", "pb-capacity-fields");
  const workerInputs = {};
  [["reader_workers", "Reading", 8], ["writer_workers", "Writing", 8], ["review_workers", "Review", 8]].forEach(([key, label, value]) => {
    const field = make("label", "pb-worker"); field.append(make("span", "", `${label} at once`));
    const input = make("input"); input.type = "number"; input.min = "1"; input.max = "128"; input.step = "1"; input.value = ""; input.placeholder = "Use total limit"; input.setAttribute("aria-label", `${label} workers at once`);
    field.append(input); capacityFields.append(field); workerInputs[key] = input;
  });
  const context = make("details", "pb-context-options"); context.append(make("summary", "", "Advanced settings"));
  const contextFields = make("div", "pb-context-fields");
  function numericField(label, value, min, max) { const field = make("label", "pb-worker"); field.append(make("span", "", label)); const input = make("input"); input.type="number"; input.value=value===null?"":String(value); input.min=String(min); input.max=String(max); field.append(input); contextFields.append(field); return input; }
  const workflowLabel = make("label", "pb-worker"); workflowLabel.append(make("span", "", "Workflow"));
  const workflow = make("select"); workflow.setAttribute("aria-label", "Workflow");
  [["auto","Automatic"],["direct","Write directly from sources"],["planned","Read, outline and write"],["sweep","Read straight to flashcards"]].forEach(([value,label])=>{const item=make("option","",label);item.value=value;workflow.append(item);});
  workflowLabel.append(workflow); contextFields.append(workflowLabel);
  const totalWorkers = numericField("Maximum concurrent requests", 8, 1, 128);
  const totalWorkerField = totalWorkers.parentElement; totalWorkerField.remove();
  const readingLabel = make("label", "pb-worker"); readingLabel.append(make("span", "", "Source reading"));
  const reading = make("select"); reading.setAttribute("aria-label", "Source reading");
  [["task","Read for this project"],["reusable","Save extracted notes for other projects"]].forEach(([value,label])=>{const item=make("option","",label);item.value=value;reading.append(item);});
  readingLabel.append(reading);contextFields.append(readingLabel);
  const sectionsPerRequest = numericField("Sections per request", 1, 1, 32);
  const compareLabel=make("label","pb-retrieval-choice");
  const compareRelations=make("input");compareRelations.type="checkbox";
  compareLabel.append(compareRelations,make("span","","Compare related passages across sources"));
  contextFields.append(compareLabel);
  const maxAttempts = numericField("Attempts per model request", 2, 1, 5);
  const coreWords = numericField("Reading size in words (optional)", null, 100, 2000);
  coreWords.placeholder="Use default";
  const haloUnits = numericField("Extra neighboring passages", 0, 0, 8);
  const maxRequest = numericField("Request size limit in bytes (optional)", null, 4096, 2000000);
  maxRequest.placeholder="Use default";
  const retrievalChoice=make("label","pb-retrieval-choice");retrievalChoice.hidden=true;
  const retrievalTargets=make("input");retrievalTargets.type="checkbox";
  const retrievalCopy=make("span");retrievalCopy.append(make("strong","","Merge equivalent questions"),make("small","","Keep questions separate when they test different decisions."));
  retrievalChoice.append(retrievalTargets,retrievalCopy);
  function updateRetrievalChoice(){retrievalChoice.hidden=!(["guide","assessment"].includes(format.value));if(retrievalChoice.hidden)retrievalTargets.checked=false;}
  format.addEventListener("change",updateRetrievalChoice);updateRetrievalChoice();
  context.append(contextFields, capacityFields, make("p", "pb-explain", "Model settings limit how much each request can contain. Saved notes can speed up later projects, but should be checked before reuse."),retrievalChoice);
  capacityBlock.append(capacityHead, capacityIntro, totalWorkerField, context);
  const savedNotes=make("details","pb-saved-notes");savedNotes.hidden=true;
  savedNotes.append(make("summary","","Use saved project notes"),make("p","pb-explain","Choose notes that apply to this project."));
  const savedNotesList=make("div","pb-saved-notes-list");savedNotes.append(savedNotesList);
  const controls = make("div", "pb-controls");
  const start = make("button", "pb-primary", "Start project"); start.type = "button";
  const mode = make("p", "pb-mode", "Checking local app…"); mode.setAttribute("role", "status");
  controls.append(start, mode); form.append(goalBlock, sourceBlock, capacityBlock, savedNotes, controls);
  const activity = make("section", "pb-activity"); activity.hidden = true;
  const activityTitle = make("h3", "", "Project progress");
  const activityStatus = make("p", "pb-run-status");
  const events = make("div", "pb-events");
  const output = make("div", "pb-output");
  activity.append(activityTitle, activityStatus, events, output);
  const recent = make("details", "pb-recent"); recent.append(make("summary", "", "Recent local projects"));
  const recentList = make("div", "pb-recent-list"); recent.append(recentList);
  shell.append(form, activity, recent); host.replaceChildren(shell);
  const setMessage = (value, bad = false) => { mode.textContent = value; mode.classList.toggle("error", bad); };
  window.addEventListener("lamina:setup", event => {
    const setup=event.detail;
    if(!setup || typeof setup.brief!=="string" || !["guide","assessment","podcast-script","cards"].includes(setup.options?.format))return;
    goal.value=setup.brief; format.value=setup.options.format;
    for(const [key,input] of Object.entries(workerInputs)){
      const value=setup.options[key];input.value=Number.isInteger(value)&&value>=1&&value<=128?String(value):"";
    }
    coreWords.value=setup.options.core_words??"";haloUnits.value=setup.options.halo_units??0;
    maxRequest.value=setup.options.max_input_bytes??"";reading.value=setup.options.reading??"task";
    workflow.value=setup.options.workflow??"auto";maxAttempts.value=setup.options.max_attempts??2;
    totalWorkers.value=setup.options.workers??8;
    updateFormatNote();updateRetrievalChoice();retrievalTargets.checked=Boolean(setup.options.retrieval_targets)&&!retrievalChoice.hidden;
    let notice=form.querySelector('.setup-loaded');if(!notice){notice=make('p','setup-loaded');notice.setAttribute('role','status');form.prepend(notice);}
    notice.textContent=`${setup.name} setup loaded. Adjust the brief, then choose your sources.`;
    goal.focus();
  });
  function safeNumber(input, name) { const n = Number(input.value); if (!Number.isInteger(n) || n < Number(input.min) || n > Number(input.max)) throw Error(`${name} must be ${input.min}–${input.max}.`); return n; }
  function options(selected) {
    if(selected.every(id=>state.roles.get(id)==="form_exemplar"))throw Error("Choose at least one file that provides facts. A style example alone is not enough.");
    if(state.selectedObservations.size>20)throw Error("Choose at most 20 saved notes for one project.");
    const halo=safeNumber(haloUnits,"Neighboring passages");
    if(halo && !coreWords.value.trim())throw Error("Set a reading size in words before adding neighboring passages.");
    return {
      format:format.value, workflow:workflow.value, reading:reading.value,
      sections_per_request:safeNumber(sectionsPerRequest,"Sections per request"), compare_relations:compareRelations.checked,
      workers:safeNumber(totalWorkers,"Total calls"), max_attempts:safeNumber(maxAttempts,"Attempts"),
      ...Object.fromEntries(Object.entries(workerInputs).filter(([,input])=>input.value.trim()!=="").map(([key,input])=>[key,safeNumber(input,({reader_workers:"Reading limit",writer_workers:"Writing limit",review_workers:"Review limit"})[key])])),
      ...(coreWords.value.trim()?{core_words:safeNumber(coreWords,"Fixed reading target")}:{}),
      ...(maxRequest.value.trim()?{max_input_bytes:safeNumber(maxRequest,"Request byte ceiling")}:{}),
      halo_units:halo, retrieval_targets:retrievalTargets.checked && !retrievalChoice.hidden,
      source_policy:Object.fromEntries(selected.map(id=>[id,state.roles.get(id) || "authority"])),
      observation_ids:Array.from(state.selectedObservations)
    };
  }
  function renderSources() {
    sourceList.replaceChildren();
    if (!state.sources.length) { sourceList.append(make("p", "pb-empty", state.local ? "No sources stored locally yet. Add files below." : "Open the local app to add source files.")); return; }
    state.sources.forEach(source => {
      const row = make("div", "pb-source");
      const identity = make("label", "pb-source-identity");
      const checkbox = make("input"); checkbox.type="checkbox"; checkbox.value=source.id; checkbox.checked=state.selected.has(source.id); checkbox.disabled=source.role === "assessment" || !state.local;
      checkbox.addEventListener("change", () => { if (checkbox.checked) state.selected.add(source.id); else state.selected.delete(source.id); });
      const text = make("span"); text.append(make("strong", "", source.title || source.filename || source.id), make("small", "", `${source.units ?? "?"} passages · ${source.role === "assessment" ? "reserved for testing" : "source material"}`));
      identity.append(checkbox,text);row.append(identity);
      if(source.role !== "assessment") {
        const use=make("label","pb-source-use");use.append(make("span","","Use as"));
        const selector=make("select");selector.setAttribute("aria-label",`How to use ${source.title || source.filename || source.id}`);selector.disabled=!state.local;
        [["authority","Factual source"],["supplement","Supporting context"],["historical","Older or conflicting version"],["form_exemplar","Style or layout example"]].forEach(([value,label])=>{const option=make("option","",label);option.value=value;selector.append(option);});
        selector.value=state.roles.get(source.id) || "authority";
        selector.addEventListener("change",()=>state.roles.set(source.id,selector.value));use.append(selector);row.append(use);
      }
      sourceList.append(row);
    });
  }
  async function getJSON(path) { const response = await fetch(route(path), {cache:"no-store"}); if (!response.ok) throw Error(`HTTP ${response.status}`); return response.json(); }
  async function post(path, data) { const response = await fetch(route(path), {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(data)}); let value; try { value=await response.json(); } catch { throw Error(`HTTP ${response.status}: no JSON response`); } if (!response.ok) throw Error(value.error || `HTTP ${response.status}`); return value; }
  async function refreshSources() { const status = await getJSON("api/status"); state.local=status.mode === "local"; state.adapter=Boolean(status.adapter_configured);state.audioAdapter=Boolean(status.audio_adapter_configured);updateFormatNote(); state.sources=Array.isArray(status.sources)?status.sources:[]; renderSources(); start.disabled=!state.adapter; fileInput.disabled=!state.local; setMessage(state.adapter ? "Ready to run. Selected source text may go to your configured model provider." : "Start Lamina with --adapter @models.json to connect a model. See the adapter setup guide in Documentation."); const badge=document.getElementById("project-mode"); if (badge) badge.textContent=state.adapter?"Ready":"Model connection needed"; try { const projects=await getJSON("api/projects");renderRecent(projects.projects || []); } catch { recent.hidden=true; } await refreshObservations(); if (status.active_run?.kind === "production" && status.active_run.id) {state.runId=status.active_run.id; poll(status.active_run.id);} }
  async function refreshObservations(){try{const answer=await getJSON("api/project-observations");state.observations=Array.isArray(answer.observations)?answer.observations:[];renderObservations();}catch{savedNotes.hidden=true;}}
  function renderObservations(){savedNotesList.replaceChildren();savedNotes.hidden=!state.observations.length;state.observations.forEach(item=>{const id=item.observation_id;if(!id)return;const row=make("label","pb-note-choice");const input=make("input");input.type="checkbox";input.checked=state.selectedObservations.has(id);input.addEventListener("change",()=>{if(input.checked)state.selectedObservations.add(id);else state.selectedObservations.delete(id);});const text=make("span");text.append(make("strong","",item.note || "Saved project note"));if(item.applicability)text.append(make("small","",`Use when: ${item.applicability}`));row.append(input,text);savedNotesList.append(row);});}
  function renderRecent(projects) {
    recentList.replaceChildren(); recent.hidden=!projects.length;
    projects.slice(0,8).forEach(project=>{
      const row=make("div","pb-recent-row");
      const date=Number.isFinite(Number(project.created_at))?new Date(Number(project.created_at)*1000).toLocaleString():"Earlier project";
      row.append(make("span","",`${date} · ${statusLabel(project.status)}`));
      const open=make("button","pb-secondary","Open");open.type="button";
      open.addEventListener("click",()=>{state.runId=project.id;poll(project.id);});row.append(open);
      if(["failed","interrupted"].includes(project.status)){
        const resume=make("button","pb-secondary","Resume");resume.type="button";
        resume.addEventListener("click",async()=>{resume.disabled=true;try{const answer=await post(`api/projects/${encodeURIComponent(project.id)}/resume`,{});state.runId=answer.id;poll(answer.id);recent.open=false;}catch(err){setMessage(`Could not resume: ${err.message}`,true);resume.disabled=false;}});row.append(resume);
      }
      recentList.append(row);
    });
  }
  function readBinary(file) { return new Promise((resolve,reject) => { const reader=new FileReader(); reader.onerror=()=>reject(Error("Could not read file")); reader.onload=()=> { const text=String(reader.result||""); const pos=text.indexOf(","); if (pos<0) reject(Error("Could not encode file")); else resolve(text.slice(pos+1)); }; reader.readAsDataURL(file); }); }
  fileInput.addEventListener("change", async () => {
    const files=Array.from(fileInput.files || []); if (!files.length) return;
    uploadStatus.textContent="Reading files…"; fileInput.disabled=true;
    try {
      let stored=0;
      for (const file of files) {
        if (!/^[A-Za-z0-9][A-Za-z0-9._ -]{0,119}\.(txt|md|pdf|pptx)$/i.test(file.name)) throw Error(`${file.name}: unsupported file name or type.`);
        if (file.size > 256*1024*1024) throw Error(`${file.name}: the file exceeds 256 MiB.`);
        uploadStatus.textContent=`Uploading and parsing ${file.name}… (${stored}/${files.length} stored)`;
        const response=await fetch(route("api/source-upload"),{method:"POST",headers:{"Content-Type":"application/octet-stream","X-Lamina-Filename":file.name,"X-Lamina-Role":"teaching"},body:file});
        const answer=await response.json();if(!response.ok)throw Error(answer.error || `HTTP ${response.status}`);
        for (const source of answer.sources || []) state.selected.add(source.id);
        stored+=answer.count || 1;
        await refreshSources();
      }
      uploadStatus.textContent=`Stored ${stored} source${stored===1?"":"s"} locally.`;
    } catch (err) { uploadStatus.textContent=`Could not add sources: ${err.message}`; }
    finally { fileInput.disabled=!state.local; fileInput.value=""; }
  });
  function appendMarkdown(container, markdown) {
    const lines=String(markdown || "").split(/\r?\n/); let paragraph=[];
    const flush=()=>{if(paragraph.length){container.append(make("p", "", paragraph.join(" "))); paragraph=[];}};
    lines.forEach(line => {
      const text=line.trim();
      if (!text) { flush(); return; }
      const heading=/^(#{1,3})\s+(.+)$/.exec(text);
      if (heading) { flush(); container.append(make(heading[1].length===1?"h3":"h4", "", heading[2])); return; }
      if (/^[-*]\s+/.test(text)) { flush(); container.append(make("p", "pb-list-line", `• ${text.slice(2)}`)); return; }
      paragraph.push(text);
    }); flush();
  }
  function sourceLabel(id) { const unit=state.run?.plan?.units?.find?.(u=>u.id===id);const sourceId=unit?.source_id || id;const available=state.run?.receipt?.sources || state.sources;const source=available.find?.(s=>s.id===sourceId);return `${source?.title || source?.filename || sourceId}${unit?.locator ? ` · ${unit.locator}` : ""}`; }
  function sectionsFrom(receipt) { const sections=receipt?.sections; return Array.isArray(sections) ? sections : sections && typeof sections === "object" ? Object.entries(sections).map(([id,value])=>({id,...value})) : []; }
  function outputLink(path,label) { if (typeof path!=="string" || !/^\/outputs\/[a-f0-9]{32}\//.test(path) || path.includes("\\")) return null; const a=make("a","pb-output-link",label); a.href=route(path); a.target="_blank"; a.rel="noopener"; return a; }
  function renderReceipt(run, example=false) {
    output.replaceChildren(); const receipt=run.receipt;
    if (!receipt) return;
    const isAssessment=receipt.format==="assessment";
    output.append(make("h3", "", isAssessment?"Practice exam":receipt.title || "Result"));
    const planned=Array.isArray(run.plan?.route?.sections)?run.plan.route.sections:[];
    if(planned.length && !isAssessment){
      const plan=make("details","pb-plan");plan.append(make("summary","",`Project outline · ${planned.length} section${planned.length===1?"":"s"}`));
      const list=make("div","pb-plan-list");
      planned.forEach(section=>{
        const row=make("div","pb-plan-row");
        const heading=make("div","pb-plan-heading");heading.append(make("strong","",section.title || section.id || "Section"));
        if(section.representation?.kind)heading.append(make("span","pb-plan-kind",section.representation.kind));
        row.append(heading);
        if(section.purpose)row.append(make("p","",section.purpose));
        if(section.representation?.rationale)row.append(make("small","",`Why this form: ${section.representation.rationale}`));
        if(Array.isArray(section.representation?.requirements) && section.representation.requirements.length){
          const obligations=make("ul");section.representation.requirements.forEach(item=>obligations.append(make("li","",item)));row.append(obligations);
        }
        list.append(row);
      });
      plan.append(list);output.append(plan);
    }
    const sections=sectionsFrom(receipt);
    const sectionBodies=sections.length && sections.every(section=>section.body || section.candidate_body);
    if (sectionBodies) {
      const sectionBar=make("nav","pb-section-nav"); sectionBar.setAttribute("aria-label","Result sections");
      sections.forEach((section,index)=>{ const a=make("a","",isAssessment?`Question ${index+1}`:section.title || `Section ${index+1}`); a.href=`#pb-section-${index}`; sectionBar.append(a); }); output.append(sectionBar);
    }
    const article=make("article","pb-article");
    if (sectionBodies) sections.forEach((section,index)=>{ const block=make("section","pb-output-section"); block.id=`pb-section-${index}`; block.append(make("h4","",isAssessment?`Question ${index+1}`:section.title || `Section ${index+1}`)); appendMarkdown(block,isAssessment?section.candidate_body || "":section.body || ""); article.append(block); });
    else if (receipt.candidate_markdown || receipt.markdown) appendMarkdown(article,receipt.candidate_markdown || receipt.markdown);
    else if(isAssessment && sections.length)sections.forEach((section,index)=>{article.append(make("h4","",`Question ${index+1}`));appendMarkdown(article,section.candidate_body || "");});
    else article.append(make("p","","The run returned no readable document text."));
    output.append(article);
    const catalog=receipt.retrieval_targets || run.plan?.retrieval_targets;
    if(receipt.format==="guide" && Array.isArray(catalog?.targets) && catalog.targets.length){
      const practice=make("section","pb-targets");practice.append(make("h4","","Practice questions"));
      catalog.targets.forEach((target,index)=>{
        const item=make("div","pb-target");item.append(make("strong","",target.title || `Question ${index+1}`),make("p","pb-target-prompt",target.prompt || ""));
        if(target.context)item.append(make("small","",target.context));
        if(Array.isArray(target.answer_groups) && target.answer_groups.length){const answers=make("details");answers.append(make("summary","","Show answers"));target.answer_groups.forEach(group=>{const block=make("div","pb-answer-group");block.append(make("b","",group.label || "Answer"));(Array.isArray(group.items)?group.items:[]).forEach(answer=>{block.append(make("p","",answer.text || ""));(Array.isArray(answer.evidence)?answer.evidence:[]).forEach(ev=>block.append(make("small","",sourceLabel(ev.unit_id || ev.source_id))));});answers.append(block);});item.append(answers);}
        practice.append(item);
      });output.append(practice);
    }
    if(receipt.format==="podcast-script" && !run.outputs?.audio)output.append(make("p","pb-script-note","Script ready. Connect a speech service to create audio."));
    if(receipt.format==="cards"){
      const m=receipt.metrics || {};
      const deck=make("section","pb-deck");
      deck.append(make("h4","","Deck"));
      deck.append(make("p","",`${m.cards ?? (receipt.cards||[]).length} cards · ${m.suppressed_duplicates ?? 0} near-duplicates removed · ${m.audited_windows ?? 0} window${m.audited_windows===1?"":"s"} audited · ${m.audit_findings ?? 0} audit finding${m.audit_findings===1?"":"s"}`));
      const unresolved=Array.isArray(receipt.unresolved_reads)?receipt.unresolved_reads:[];
      if(unresolved.length)deck.append(make("p","pb-script-note",`${unresolved.length} source window${unresolved.length===1?"":"s"} could not be read; the deck covers the rest.`));
      const findings=receipt.audit_findings || {};
      const rows=Object.entries(findings).flatMap(([windowId,list])=>(Array.isArray(list)?list:[]).map(f=>({windowId,...f})));
      if(rows.length){const audit=make("details","pb-review");audit.append(make("summary","",`Audit findings · ${rows.length}`));rows.forEach(f=>{const item=make("div","pb-private-check");item.append(make("strong","",f.kind==="omission"?"Not yet a card":"Unsupported card"),make("p","",f.issue||""));(Array.isArray(f.evidence)?f.evidence:[]).forEach(ev=>{const cited=make("p","pb-citation");cited.append(make("span","",ev.quote||""));if(ev.unit_id)cited.append(make("small","",sourceLabel(ev.unit_id)));item.append(cited);});audit.append(item);});deck.append(audit);}
      output.append(deck);
    }
    if(Array.isArray(run.outputs?.episodes) && run.outputs.episodes.length>1){
      const episodes=make("div","pb-output-links");episodes.append(make("strong","","Episodes"));
      run.outputs.episodes.forEach((path,index)=>{const link=outputLink(path,`Episode ${index+1}`);if(link)episodes.append(link);});
      output.append(episodes);
    }
    let examinerDetails=null;
    if (receipt.assessment_checks){output.append(make("p","pb-assessment-status",`Question check: ${statusLabel(receipt.assessment_checks.status)} · ${receipt.assessment_checks.metrics?.flagged_sections ?? "?"} flagged section${receipt.assessment_checks.metrics?.flagged_sections===1?"":"s"}.`));}
    if (receipt.examiner_markdown || receipt.assessment_checks || isAssessment) {
      const examiner=make("details","pb-review pb-private"); examiner.append(make("summary","","Answer key and review"));examinerDetails=examiner;
      const body=make("div","pb-examiner"); if(receipt.examiner_markdown)appendMarkdown(body,receipt.examiner_markdown);
      const checks=receipt.assessment_checks;
      if(checks){body.append(make("h4","","Answers attempted without the key"),make("p","",`${statusLabel(checks.status)} · ${checks.metrics?.flagged_sections ?? "?"} flagged section${checks.metrics?.flagged_sections===1?"":"s"}`));
        (Array.isArray(checks.checks)?checks.checks:[]).forEach(item=>{const check=make("div","pb-private-check");check.append(make("strong","",item.section_id || "Section"));if(item.blind_answer?.answer)check.append(make("p","",`Attempted answer: ${item.blind_answer.answer}`));(Array.isArray(item.findings)?item.findings:[]).forEach(finding=>check.append(make("p","",`${finding.kind || "Finding"}: ${finding.issue || "Review needed"}`)));body.append(check);});}
      examiner.append(body); output.append(examiner);
    }
    if (sections.length) {
      const refs=make("div","pb-source-refs"); refs.append(make("strong","","Sources by section"));
      sections.forEach(section=>{
        const evidence=Array.isArray(section.evidence)?section.evidence:[];
        const ids=section.source_ids || section.sources || [];
        if (!evidence.length && (!Array.isArray(ids) || !ids.length)) return;
        const row=make("div","pb-source-ref"); row.append(make("b","",section.title || section.id || "Section"));
        if (Array.isArray(ids) && ids.length) row.append(make("p","",ids.map(sourceLabel).join(", ")));
        evidence.forEach(item=>{const cited=make("p","pb-citation"); cited.append(make("span","",typeof item==="string" ? item : item.quote || item.excerpt || item.text || "Source passage")); const id=typeof item==="object" && item ? item.source_id || item.unit_id : null; if(id)cited.append(make("small","",sourceLabel(id))); row.append(cited);});
        refs.append(row);
      });
      if(isAssessment && examinerDetails)examinerDetails.append(refs);else output.append(refs);
    }
    const links=make("div","pb-output-links");
    const audioPath=run.outputs?.audio;
    if(typeof audioPath==="string" && outputLink(audioPath,"Audio file")){
      const audioBlock=make("div","pb-audio");audioBlock.append(make("strong","","Audio"));
      const player=make("audio");player.controls=true;player.preload="metadata";player.src=route(audioPath).href;player.setAttribute("aria-label","Project audio");audioBlock.append(player);
      const delivery=receipt.audio_delivery;
      audioBlock.append(make("p","",delivery?.status==="review"?"Review this audio and its transcript before using it.":"Listen to check pronunciation and completeness. The transcript shows the text sent to the speech service."));
      output.append(audioBlock);
    }
    const linkLabels={reader:"Read formatted document",document:"Download text",pdf:"Download PDF",plan:"Inspect plan",report:"Download run details",candidate:"Open candidate sheet",examiner:"Open examiner sheet",examiner_pdf:"Download examiner PDF",audio:"Download audio WAV",transcript:"Download transcript",manifest:"Download audio details",cards_tsv:"Download Anki deck (TSV)",cards_json:"Download cards (JSON)"};
    Object.entries(run.outputs || {}).forEach(([kind,path])=>{ if(Array.isArray(path))return; const link=outputLink(path,linkLabels[kind] || `Open ${kind.replaceAll("_"," ")}`);if(!link)return;if(receipt.format==="assessment" && ["examiner","examiner_pdf","report","plan"].includes(kind) && examinerDetails)examinerDetails.append(link);else links.append(link); });
    if (links.childNodes.length) output.append(links);
    const findings=receipt.findings || receipt.initial_findings;
    if (findings && receipt.format!=="cards") {
      const review=make("details","pb-review");
      review.append(make("summary","","Review findings"));
      let count=0;
      for(const [id,items] of Object.entries(findings)){
        if(!Array.isArray(items) || !items.length)continue;
        const section=sections.find(item=>item.id===id);
        const block=make("section","pb-finding");
        block.append(make("h4","",section?.title || "Project review"));
        for(const item of items){
          count++;
          block.append(make("p","",item.issue || "This section needs review."));
          if(item.repair_instruction)block.append(make("p","",`Suggested change: ${item.repair_instruction}`));
          for(const ev of item.evidence || [])block.append(make("p","pb-citation",`${sourceLabel(ev.unit_id || ev.source_id)}: ${ev.quote || ""}`));
        }
        review.append(block);
      }
      if(!count)review.append(make("p","","No unresolved findings from the section checks."));
      const raw=make("details");raw.append(make("summary","","Technical details"),make("pre","",JSON.stringify(findings,null,2)));review.append(raw);
      if(receipt.format==="assessment" && examinerDetails)examinerDetails.append(review);else output.append(review);
    }
    if (sections.length && state.local && state.runId && !example) {
      const revision=make("div","pb-revision"); revision.append(make("h4","","Change one section")); revision.append(make("p","","Describe the change. Lamina starts a new run and reuses unaffected work when it can."));
      const select=make("select"); select.setAttribute("aria-label","Section to revise"); sections.forEach((section,index)=>{const option=make("option","",section.title || `Section ${index+1}`); option.value=section.id || String(index); select.append(option);});
      const note=make("textarea"); note.rows=3; note.placeholder="What should change in this section?"; note.setAttribute("aria-label","Requested section change");
      const button=make("button","pb-secondary","Revise section"); button.type="button";
      const feedback=make("p","pb-revision-feedback"); feedback.setAttribute("role","status");
      button.addEventListener("click",async()=>{ if(!note.value.trim()){feedback.textContent="Describe the change first.";return;} button.disabled=true; feedback.textContent="Revising section…"; try{const answer=await post(`api/projects/${encodeURIComponent(state.runId)}/revise`,{section_notes:{[select.value]:note.value.trim()}}); if(!answer.id) throw Error("Server returned no revision run ID.");state.runId=answer.id; output.replaceChildren();poll(answer.id);}catch(err){feedback.textContent=`Could not revise: ${err.message}`;button.disabled=false;} });
      revision.append(select,note,button,feedback); if(isAssessment && examinerDetails)examinerDetails.append(revision);else output.append(revision);
    }
    if(state.local && state.runId && !example){
      const memory=make("details","pb-save-note");memory.append(make("summary","","Keep a note for future projects"));
      const fields=make("div","pb-save-note-fields");
      function field(label,placeholder){const wrap=make("label");wrap.append(make("span","",label));const input=make("textarea");input.rows=2;input.placeholder=placeholder;wrap.append(input);fields.append(wrap);return input;}
      const note=field("What did you learn?","A useful observation from this run");
      const applicability=field("When should it apply?","The type of source or project where this matters");
      const outcome=field("What happened?","The result or limitation you observed");
      const button=make("button","pb-secondary","Save note");button.type="button";const feedback=make("p","pb-save-feedback");feedback.setAttribute("role","status");
      button.addEventListener("click",async()=>{if(!note.value.trim() || !applicability.value.trim() || !outcome.value.trim()){feedback.textContent="Fill in all three fields to keep a usable note.";return;}button.disabled=true;feedback.textContent="Saving…";try{await post(`api/projects/${encodeURIComponent(state.runId)}/observation`,{note:note.value.trim(),applicability:applicability.value.trim(),outcome:outcome.value.trim()});feedback.textContent="Saved. Select this note when it fits a future project.";await refreshObservations();}catch(err){feedback.textContent=`Could not save note: ${err.message}`;button.disabled=false;}});
      memory.append(fields,button,feedback);output.append(memory);
    }
  }
  function renderRun(run) {
    state.run=run; const wasHidden=activity.hidden; activity.hidden=false; events.replaceChildren();
    activityStatus.textContent=run.example ? "Saved fixture · not model output" : statusLabel(run.status);
    const records=Array.isArray(run.events)?run.events:[];
    const labels={production_read:"Reading sources",production_route:"Preparing the outline",production_group:"Organizing ideas",production_assign:"Assigning sources",production_targets:"Organizing questions",production_compare:"Comparing sources",production_consistency:"Checking sections together",production_write:"Writing sections",production_review:"Reviewing sections",production_repair:"Revising sections",assessment_blind_solve:"Trying the questions",assessment_judge:"Checking the answers"};
    const grouped=new Map();
    records.forEach(event=>{const stage=event.stage || event.node || "Work";if(!grouped.has(stage))grouped.set(stage,new Map());grouped.get(stage).set(event.item || "global",event.status || "updated");});
    grouped.forEach((items,stage)=>{const values=[...items.values()];const done=values.filter(status=>status==="completed").length;const failed=values.filter(status=>status==="failed").length;const active=values.filter(status=>status==="started").length;const row=make("div","pb-event");row.append(make("span","pb-event-stage",labels[stage] || stage.replaceAll("production_","").replaceAll("_"," ")),make("strong","",`${done}/${items.size} complete`));if(active || failed)row.append(make("p","",`${active ? `${active} active` : ""}${active && failed ? " · " : ""}${failed ? `${failed} failed` : ""}`));events.append(row);});
    if(!events.childNodes.length) events.append(make("p","pb-empty",run.status==="queued"?"Queued. Waiting for the first stage update…":"No stage events were reported for this run."));
    if(records.length){const detail=make("details","pb-event-details");detail.append(make("summary","",`Show ${records.length} processing updates`));const log=make("div","pb-event-log");records.forEach(event=>log.append(make("p","",`${labels[event.stage] || event.stage || "Work"} · ${event.item || "whole project"} · ${event.status || "updated"}`)));detail.append(log);events.append(detail);}
    if(run.error) output.replaceChildren(make("p","pb-error",run.error)); else renderReceipt(run,Boolean(run.example));
    if(wasHidden) activity.scrollIntoView({behavior:"smooth",block:"start"});
  }
  let previewRun="", previewCursor=0;
  const previews=new Map();
  async function loadPreviews(run){
    if(previewRun!==run.id){previewRun=run.id;previewCursor=0;previews.clear();}
    if((run.section_update_count||0)>previewCursor){
      const page=await getJSON(`api/section-updates/${encodeURIComponent(run.id)}/${previewCursor}`);
      for(const item of page.updates||[])previews.set(item.id,item);
      previewCursor=page.cursor;
    }
    if(!previews.size)return;
    output.replaceChildren(make("h3","","Draft preview"),make("p","pb-explain","Sections appear here as they are written and checked. They may change before the project finishes."));
    for(const item of [...previews.values()].sort((a,b)=>a.position-b.position)){
      const card=make("article","pb-section-preview");card.append(make("h4","",item.title),make("small","",item.status==="review"?"Needs review":"Draft"));
      appendMarkdown(card,item.body);
      if(item.truncated)card.append(make("p","","Preview shortened. Full text will be available in the completed project."));
      if(item.evidence?.length){const evidence=make("details");evidence.append(make("summary","","Supporting passages"));for(const e of item.evidence)evidence.append(make("p","",`${e.unit_id}: ${e.quote}`));card.append(evidence);}
      output.append(card);
    }
  }
  async function poll(id) {clearTimeout(state.poll);try{let run=await getJSON(`api/progress/${encodeURIComponent(id)}`);if(!["queued","running"].includes(run.status))run=await getJSON(`api/runs/${encodeURIComponent(id)}`);renderRun(run);if(["queued","running"].includes(run.status))await loadPreviews(run);if(["queued","running"].includes(run.status))state.poll=setTimeout(()=>poll(id),1800);else{start.disabled=!state.adapter;setMessage(run.status==="ready"?"Project complete. Your result and sources are below.":run.status==="review"?"Your draft is ready, with issues to review below.":`Project ${run.status}.`,run.status==="failed");}}catch(err){start.disabled=false;setMessage(`Could not read project progress: ${err.message}`,true);}}
  start.addEventListener("click",async()=>{
    if(!state.local || !state.adapter){setMessage("Connect a model in the local app to start a project.",true);return;}
    const brief=goal.value.trim();if(!brief){setMessage("Describe the result you want first.",true);goal.focus();return;}
    const selected=Array.from(state.selected).filter(id=>state.sources.some(s=>s.id===id && s.role==="teaching"));if(!selected.length){setMessage("Choose at least one source file.",true);return;}
    let chosen;try{chosen=options(selected);}catch(err){setMessage(err.message,true);return;}
    start.disabled=true;setMessage("Starting project…");
    try{const answer=await post("api/projects",{brief,source_ids:selected,options:chosen});if(!answer.id)throw Error("Server returned no project ID.");state.runId=answer.id;poll(answer.id);}catch(err){start.disabled=false;setMessage(`Could not start project: ${err.message}`,true);}
  });
  async function initialize(){
    try{await refreshSources();}catch{state.local=false;state.adapter=false;start.disabled=true;fileInput.disabled=true;recent.hidden=true;renderSources();setMessage("Cannot reach the local app. Start Lamina and open the address it prints.");const badge=document.getElementById("project-mode");if(badge)badge.textContent="Local server unavailable";}
  }
  window.addEventListener("lamina:view", event => {
    if (event.detail === "workflows") refreshSources().catch(() => setMessage("Cannot refresh local sources. Reload the app to reconnect.", true));
  });
  initialize();
})();
