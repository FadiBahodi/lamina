/* Goal-first production UI. All result text is inserted as text nodes. */
(() => {
  "use strict";
  const host = document.getElementById("production-workbench");
  if (!host) return;
  const make = (tag, cls = "", value) => { const x = document.createElement(tag); if (cls) x.className = cls; if (value !== undefined) x.textContent = String(value); return x; };
  const route = path => new URL(path, document.baseURI);
  function initScaleLab() {
    const units=document.getElementById("scale-units"), readers=document.getElementById("scale-readers"), waves=document.getElementById("scale-waves");
    if(!units || !readers || !waves) return;
    function paint() {
      const count=Number(units.value), width=Number(readers.value), total=Math.ceil(count/width);
      document.getElementById("scale-units-value").textContent=String(count);
      document.getElementById("scale-readers-value").textContent=String(width);
      document.getElementById("scale-wave-count").textContent=`${total} wave${total===1?"":"s"} of reading`;
      waves.replaceChildren(); let left=count;
      for(let i=0;i<total;i++){const row=make("div","scale-wave");const n=Math.min(width,left);for(let j=0;j<n;j++)row.append(make("i"));row.setAttribute("aria-label",`Reading wave ${i+1}: ${n} source pieces`);waves.append(row);left-=n;}
    }
    units.addEventListener("input",paint); readers.addEventListener("input",paint); paint();
  }
  initScaleLab();
  const state = { local: false, adapter: false, sources: [], selected: new Set(), runId: "", run: null, poll: null, example: null };
  const shell = make("div", "pb-shell");
  const form = make("div", "pb-form");
  const goalBlock = make("section", "pb-block");
  const goalHead = make("div", "pb-block-head"); goalHead.append(make("span", "pb-step", "01"), make("h3", "", "What should this project produce?"));
  const goal = make("textarea", "pb-goal"); goal.rows = 5; goal.placeholder = "Example: Make a concise field guide that helps an on-call engineer decide when a retried job may publish its result."; goal.setAttribute("aria-label", "Project goal");
  const formatLabel = make("label", "pb-field"); formatLabel.append(make("span", "", "Output"));
  const format = make("select"); format.setAttribute("aria-label", "Output format");
  [["document", "Document"], ["guide", "Study guide"], ["assessment", "Decision practice"], ["podcast-script", "Listening script (text only)"]].forEach(([value, label]) => { const option = make("option", "", label); option.value = value; format.append(option); });
  formatLabel.append(format); goalBlock.append(goalHead, goal, formatLabel);
  const sourceBlock = make("section", "pb-block");
  const sourceHead = make("div", "pb-block-head"); sourceHead.append(make("span", "pb-step", "02"), make("h3", "", "Which sources should it use?"));
  const sourceNote = make("p", "pb-explain", "Select local teaching sources. Assessment sources stay held out from generation.");
  const sourceList = make("div", "pb-sources");
  const uploadLabel = make("label", "pb-upload"); uploadLabel.append(make("span", "", "Add .txt, .md, or .pdf files"));
  const fileInput = make("input"); fileInput.type = "file"; fileInput.multiple = true; fileInput.accept = ".txt,.md,.pdf,text/plain,text/markdown,application/pdf"; uploadLabel.append(fileInput);
  const uploadStatus = make("p", "pb-upload-status"); uploadStatus.setAttribute("role", "status");
  sourceBlock.append(sourceHead, sourceNote, sourceList, uploadLabel, uploadStatus);
  const capacityBlock = make("section", "pb-block");
  const capacityHead = make("div", "pb-block-head"); capacityHead.append(make("span", "pb-step", "03"), make("h3", "", "How much work can run together?"));
  const capacityIntro = make("p", "pb-explain", "These are concurrency ceilings, not promises of speed. Your model provider may impose lower limits.");
  const capacityFields = make("div", "pb-capacity-fields");
  const workerInputs = {};
  [["reader_workers", "Reading", 16], ["writer_workers", "Writing", 8], ["review_workers", "Review", 8]].forEach(([key, label, value]) => {
    const field = make("label", "pb-worker"); field.append(make("span", "", `${label} at once`));
    const input = make("input"); input.type = "number"; input.min = "1"; input.max = "128"; input.step = "1"; input.value = String(value); input.setAttribute("aria-label", `${label} workers at once`);
    field.append(input); capacityFields.append(field); workerInputs[key] = input;
  });
  const context = make("details", "pb-context-options"); context.append(make("summary", "", "Source context settings"));
  const contextFields = make("div", "pb-context-fields");
  function numericField(label, value, min, max) { const field = make("label", "pb-worker"); field.append(make("span", "", label)); const input = make("input"); input.type="number"; input.value=String(value); input.min=String(min); input.max=String(max); field.append(input); contextFields.append(field); return input; }
  const coreWords = numericField("Words in each owned passage", 800, 100, 2000);
  const haloUnits = numericField("Neighboring passages lent", 2, 0, 8);
  const maxRequest = numericField("Maximum request bytes", 1500000, 4096, 2000000);
  context.append(contextFields, make("p", "pb-explain", "Neighboring passages help a reader interpret the boundary of its assigned piece. The result still belongs to the passage it owns."));
  capacityBlock.append(capacityHead, capacityIntro, capacityFields, context);
  const controls = make("div", "pb-controls");
  const start = make("button", "pb-primary", "Start project"); start.type = "button";
  const mode = make("p", "pb-mode", "Checking local app…"); mode.setAttribute("role", "status");
  controls.append(start, mode); form.append(goalBlock, sourceBlock, capacityBlock, controls);
  const activity = make("section", "pb-activity"); activity.hidden = true;
  const activityTitle = make("h3", "", "Project progress");
  const activityStatus = make("p", "pb-run-status");
  const events = make("div", "pb-events");
  const output = make("div", "pb-output");
  activity.append(activityTitle, activityStatus, events, output);
  const replay = make("section", "pb-replay");
  const replayHeading = make("div"); replayHeading.append(make("strong", "", "Explore a recorded project"), make("p", "", "This replay uses a deterministic test adapter. Its stage records are real; its writing is fixture content, not a model-quality demonstration."));
  const replayActions = make("div", "pb-replay-actions");
  const replayButton = make("button", "pb-secondary", "Initial result"); replayButton.type = "button";
  const replayRevision = make("button", "pb-secondary", "After section revision"); replayRevision.type = "button";
  replayActions.append(replayButton,replayRevision); replay.append(replayHeading, replayActions);
  const recent = make("details", "pb-recent"); recent.append(make("summary", "", "Recent local projects"));
  const recentList = make("div", "pb-recent-list"); recent.append(recentList);
  shell.append(form, activity, recent, replay); host.replaceChildren(shell);
  const setMessage = (value, bad = false) => { mode.textContent = value; mode.classList.toggle("error", bad); };
  function safeNumber(input, name) { const n = Number(input.value); if (!Number.isInteger(n) || n < Number(input.min) || n > Number(input.max)) throw Error(`${name} must be ${input.min}–${input.max}.`); return n; }
  function options() { return {format:format.value, reader_workers:safeNumber(workerInputs.reader_workers,"Reading capacity"), writer_workers:safeNumber(workerInputs.writer_workers,"Writing capacity"), review_workers:safeNumber(workerInputs.review_workers,"Review capacity"), core_words:safeNumber(coreWords,"Passage size"), halo_units:safeNumber(haloUnits,"Neighboring passages"), max_request_bytes:safeNumber(maxRequest,"Request byte limit")}; }
  function renderSources() {
    sourceList.replaceChildren();
    if (!state.sources.length) { sourceList.append(make("p", "pb-empty", state.local ? "No sources stored locally yet. Add files below." : "Source selection is available in the local app. Open the recorded example below to inspect a completed project.")); return; }
    state.sources.forEach(source => {
      const row = make("label", "pb-source");
      const checkbox = make("input"); checkbox.type="checkbox"; checkbox.value=source.id; checkbox.checked=state.selected.has(source.id); checkbox.disabled=source.role === "assessment" || !state.local;
      checkbox.addEventListener("change", () => { if (checkbox.checked) state.selected.add(source.id); else state.selected.delete(source.id); });
      const text = make("span"); text.append(make("strong", "", source.title || source.filename || source.id), make("small", "", `${source.units ?? "?"} passages · ${source.role === "assessment" ? "held out from generation" : "teaching source"}`));
      row.append(checkbox, text); sourceList.append(row);
    });
  }
  async function getJSON(path) { const response = await fetch(route(path), {cache:"no-store"}); if (!response.ok) throw Error(`HTTP ${response.status}`); return response.json(); }
  async function post(path, data) { const response = await fetch(route(path), {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(data)}); let value; try { value=await response.json(); } catch { throw Error(`HTTP ${response.status}: no JSON response`); } if (!response.ok) throw Error(value.error || `HTTP ${response.status}`); return value; }
  async function refreshSources() { const status = await getJSON("api/status"); state.local=status.mode === "local"; state.adapter=Boolean(status.adapter_configured); state.sources=Array.isArray(status.sources)?status.sources:[]; renderSources(); start.disabled=!state.adapter; fileInput.disabled=!state.local; setMessage(state.adapter ? "Local adapter ready. It may send selected source text to your configured model provider." : "Local app connected; configure a model adapter to run projects."); const badge=document.getElementById("project-mode"); if (badge) badge.textContent=state.adapter?"LOCAL / READY":"LOCAL / ADAPTER REQUIRED"; try { const projects=await getJSON("api/projects");renderRecent(projects.projects || []); } catch { recent.hidden=true; } if (status.active_run?.kind === "production" && status.active_run.id) {state.runId=status.active_run.id; poll(status.active_run.id);} }
  function renderRecent(projects) {
    recentList.replaceChildren(); recent.hidden=!projects.length;
    projects.slice(0,8).forEach(project=>{
      const row=make("div","pb-recent-row");
      const date=Number.isFinite(Number(project.created_at))?new Date(Number(project.created_at)*1000).toLocaleString():"Earlier project";
      row.append(make("span","",`${date} · ${project.status || "unknown"}`));
      const open=make("button","pb-secondary","Open");open.type="button";
      open.addEventListener("click",()=>{state.runId=project.id;poll(project.id);});row.append(open);
      if(["failed","interrupted"].includes(project.status)){
        const resume=make("button","pb-secondary","Resume");resume.type="button";
        resume.addEventListener("click",async()=>{resume.disabled=true;try{const answer=await post(`api/projects/${encodeURIComponent(project.id)}/resume`,{});state.runId=answer.id;poll(answer.id);recent.open=false;}catch(err){setMessage(`Could not resume: ${err.message}`,true);resume.disabled=false;}});row.append(resume);
      }
      recentList.append(row);
    });
  }
  function readPDF(file) { return new Promise((resolve,reject) => { const reader=new FileReader(); reader.onerror=()=>reject(Error("Could not read PDF")); reader.onload=()=> { const text=String(reader.result||""); const pos=text.indexOf(","); if (pos<0) reject(Error("Could not encode PDF")); else resolve(text.slice(pos+1)); }; reader.readAsDataURL(file); }); }
  fileInput.addEventListener("change", async () => {
    const files=Array.from(fileInput.files || []); if (!files.length) return;
    uploadStatus.textContent="Reading files…"; fileInput.disabled=true;
    try {
      const payload=[];
      for (const file of files) {
        if (!/^[A-Za-z0-9][A-Za-z0-9._ -]{0,119}\.(txt|md|pdf)$/i.test(file.name)) throw Error(`${file.name}: unsupported file name or type.`);
        const pdf=/\.pdf$/i.test(file.name);
        if (file.size > (pdf?5000000:2000000)) throw Error(`${file.name}: file is too large for this local upload.`);
        payload.push(pdf ? {name:file.name,base64:await readPDF(file),role:"teaching"} : {name:file.name,text:await file.text(),role:"teaching"});
      }
      const answer=await post("api/sources", {files:payload});
      for (const source of answer.sources || []) state.selected.add(source.id);
      await refreshSources(); uploadStatus.textContent=`Stored ${answer.count || payload.length} source${(answer.count || payload.length) === 1 ? "" : "s"} locally.`;
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
  function outputLink(path,label) { if (typeof path!=="string" || !/^\/outputs\/[a-f0-9]{32}\//.test(path) || path.includes("\\")) return null; const a=make("a","pb-output-link",label); a.href=route(path); return a; }
  function renderReceipt(run, example=false) {
    output.replaceChildren(); const receipt=run.receipt;
    if (!receipt) return;
    output.append(make("h3", "", receipt.title || "Result"));
    const planned=Array.isArray(run.plan?.route?.sections)?run.plan.route.sections:[];
    if(planned.length){
      const plan=make("details","pb-plan");plan.append(make("summary","",`How this was planned · ${planned.length} section${planned.length===1?"":"s"}`));
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
      sections.forEach((section,index)=>{ const a=make("a","",section.title || `Section ${index+1}`); a.href=`#pb-section-${index}`; sectionBar.append(a); }); output.append(sectionBar);
    }
    const article=make("article","pb-article");
    if (sectionBodies) sections.forEach((section,index)=>{ const block=make("section","pb-output-section"); block.id=`pb-section-${index}`; block.append(make("h4","",section.title || `Section ${index+1}`)); appendMarkdown(block,section.body || section.candidate_body || ""); article.append(block); });
    else if (receipt.candidate_markdown || receipt.markdown) appendMarkdown(article,receipt.candidate_markdown || receipt.markdown);
    else article.append(make("p","","The run returned no readable document text."));
    output.append(article);
    if (receipt.examiner_markdown) {
      const examiner=make("details","pb-review"); examiner.append(make("summary","","Open examiner answer sheet"));
      const body=make("div","pb-examiner"); appendMarkdown(body,receipt.examiner_markdown); examiner.append(body); output.append(examiner);
    }
    if (sections.length) {
      const refs=make("div","pb-source-refs"); refs.append(make("strong","","Source evidence by section"));
      sections.forEach(section=>{
        const evidence=Array.isArray(section.evidence)?section.evidence:[];
        const ids=section.source_ids || section.sources || [];
        if (!evidence.length && (!Array.isArray(ids) || !ids.length)) return;
        const row=make("div","pb-source-ref"); row.append(make("b","",section.title || section.id || "Section"));
        if (Array.isArray(ids) && ids.length) row.append(make("p","",ids.map(sourceLabel).join(", ")));
        evidence.forEach(item=>{const cited=make("p","pb-citation"); cited.append(make("span","",typeof item==="string" ? item : item.quote || item.excerpt || item.text || "Source passage")); const id=typeof item==="object" && item ? item.source_id || item.unit_id : null; if(id)cited.append(make("small","",sourceLabel(id))); row.append(cited);});
        refs.append(row);
      });
      output.append(refs);
    }
    const links=make("div","pb-output-links");
    Object.entries(run.outputs || {}).forEach(([kind,path])=>{ const link=outputLink(path,`Open ${kind.replaceAll("_"," ")}`); if(link) links.append(link); });
    if (links.childNodes.length) output.append(links);
    const findings=receipt.findings || receipt.initial_findings;
    if (findings) { const review=make("details","pb-review"); review.append(make("summary","","Review findings")); const pre=make("pre","",JSON.stringify(findings,null,2)); review.append(pre); output.append(review); }
    if (sections.length && state.local && state.runId && !example) {
      const revision=make("div","pb-revision"); revision.append(make("h4","","Change one section")); revision.append(make("p","","Record what should change. Lamina will make a new run from this project and reuse unaffected work where the inputs allow it."));
      const select=make("select"); select.setAttribute("aria-label","Section to revise"); sections.forEach((section,index)=>{const option=make("option","",section.title || `Section ${index+1}`); option.value=section.id || String(index); select.append(option);});
      const note=make("textarea"); note.rows=3; note.placeholder="What should change in this section?"; note.setAttribute("aria-label","Requested section change");
      const button=make("button","pb-secondary","Revise section"); button.type="button";
      const feedback=make("p","pb-revision-feedback"); feedback.setAttribute("role","status");
      button.addEventListener("click",async()=>{ if(!note.value.trim()){feedback.textContent="Describe the change first.";return;} button.disabled=true; feedback.textContent="Starting a targeted revision…"; try{const answer=await post(`api/projects/${encodeURIComponent(state.runId)}/revise`,{section_notes:{[select.value]:note.value.trim()}}); if(!answer.id) throw Error("Server returned no revision run ID.");state.runId=answer.id; output.replaceChildren();poll(answer.id);}catch(err){feedback.textContent=`Could not revise: ${err.message}`;button.disabled=false;} });
      revision.append(select,note,button,feedback); output.append(revision);
    }
  }
  function renderRun(run, example=false) {
    state.run=run; const wasHidden=activity.hidden; activity.hidden=false; events.replaceChildren();
    activityStatus.textContent=example ? "Recorded example · deterministic adapter · no live model call" : `Project ${run.id || state.runId || ""} · ${run.status || "unknown"}`;
    const records=Array.isArray(run.events)?run.events:[];
    const labels={production_read:"Reading sources",production_route:"Planning the artifact",production_write:"Writing sections",production_review:"Reviewing sections",production_repair:"Repairing flagged sections"};
    const grouped=new Map();
    records.forEach(event=>{const stage=event.stage || event.node || "Work";if(!grouped.has(stage))grouped.set(stage,new Map());grouped.get(stage).set(event.item || "global",event.status || "updated");});
    grouped.forEach((items,stage)=>{const values=[...items.values()];const done=values.filter(status=>status==="completed").length;const failed=values.filter(status=>status==="failed").length;const active=values.filter(status=>status==="started").length;const row=make("div","pb-event");row.append(make("span","pb-event-stage",labels[stage] || stage.replaceAll("production_","")),make("strong","",`${done}/${items.size} complete`));if(active || failed)row.append(make("p","",`${active ? `${active} active` : ""}${active && failed ? " · " : ""}${failed ? `${failed} failed` : ""}`));events.append(row);});
    if(!events.childNodes.length) events.append(make("p","pb-empty",run.status==="queued"?"Queued. Waiting for the first stage update…":"No stage events were reported for this run."));
    if(records.length){const detail=make("details","pb-event-details");detail.append(make("summary","",`Inspect ${records.length} stage events`));const log=make("div","pb-event-log");records.forEach(event=>log.append(make("p","",`${labels[event.stage] || event.stage || "Work"} · ${event.item || "whole project"} · ${event.status || "updated"}`)));detail.append(log);events.append(detail);}
    if(run.error) output.replaceChildren(make("p","pb-error",run.error)); else renderReceipt(run,example);
    if(wasHidden || example) activity.scrollIntoView({behavior:"smooth",block:"start"});
  }
  async function poll(id) {clearTimeout(state.poll);try{const run=await getJSON(`api/runs/${encodeURIComponent(id)}`);renderRun(run);if(["queued","running"].includes(run.status))state.poll=setTimeout(()=>poll(id),1800);else{start.disabled=!state.adapter;setMessage(run.status==="ready"?"Project complete. Open the result and its source evidence below.":run.status==="review"?"Review requested. Inspect the findings below.":`Project ${run.status}.`,run.status==="failed");}}catch(err){start.disabled=false;setMessage(`Could not read project progress: ${err.message}`,true);}}
  start.addEventListener("click",async()=>{
    if(!state.local || !state.adapter){setMessage("Open the local app with a configured adapter to run a project.",true);return;}
    const brief=goal.value.trim();if(!brief){setMessage("Describe the result you want first.",true);goal.focus();return;}
    const selected=Array.from(state.selected).filter(id=>state.sources.some(s=>s.id===id && s.role==="teaching"));if(!selected.length){setMessage("Choose at least one teaching source.",true);return;}
    let chosen;try{chosen=options();}catch(err){setMessage(err.message,true);return;}
    start.disabled=true;setMessage("Starting project…");
    try{const answer=await post("api/projects",{brief,source_ids:selected,options:chosen});if(!answer.id)throw Error("Server returned no project ID.");state.runId=answer.id;poll(answer.id);}catch(err){start.disabled=false;setMessage(`Could not start project: ${err.message}`,true);}
  });
  function openReplay(index) {
    if(!state.example){setMessage("The recorded project is unavailable in this build.",true);return;}
    const fixture=state.example, record=fixture.runs?.[index];
    if(!record?.receipt){setMessage("That recorded result is unavailable.",true);return;}
    const all=Array.isArray(fixture.events)?fixture.events:[];
    const firstWriter=all.find(event=>event.stage==="production_write" && event.status==="started")?.item;
    const first=all.findIndex(event=>event.stage==="production_write" && event.status==="started" && event.item===firstWriter);
    const split=all.findIndex((event,i)=>i>first && event.stage==="production_write" && event.status==="started" && event.item===firstWriter);
    const chosen=split<0?all:(index===0?all.slice(0,split):all.slice(split));
    renderRun({id:record.title,status:record.receipt.status,receipt:record.receipt,plan:fixture.plan,events:chosen},true);
    const info=make("p","pb-replay-note",`${record.title} · ${fixture.label} ${index===1?`${record.receipt.metrics?.cache_hits ?? "?"} cached stage results; ${record.receipt.metrics?.cache_misses ?? "?"} recomputed.`:""}`);
    output.prepend(info);
  }
  replayButton.addEventListener("click",()=>openReplay(0));
  replayRevision.addEventListener("click",()=>openReplay(1));
  async function initialize(){
    try{state.example=await getJSON("production-example.json");}catch{replayButton.disabled=true;replayRevision.disabled=true;replayHeading.lastChild.textContent="The recorded example is unavailable in this build.";}
    try{await refreshSources();}catch{state.local=false;state.adapter=false;start.disabled=true;fileInput.disabled=true;recent.hidden=true;renderSources();setMessage("Hosted preview. Download and run Lamina locally to make a project with your sources.");const badge=document.getElementById("project-mode");if(badge)badge.textContent="HOSTED / RECORDED EXAMPLE";}
  }
  initialize();
})();
