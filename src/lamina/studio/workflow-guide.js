/* Use cases share their configuration with the local project form. */
(() => {
  'use strict';
  const host = document.getElementById('workflow-explorer');
  if (!host) return;
  const el = (tag, text, cls) => { const node = document.createElement(tag); if (text !== undefined) node.textContent = text; if (cls) node.className = cls; return node; };
  function preview(id) {
    const box = el('div', undefined, 'use-case-preview');
    box.setAttribute('aria-hidden', 'true');
    if (id === 'audio') {
      const card = el('div', undefined, 'preview-audio');
      card.append(el('strong', 'A concept worth explaining'), el('small', 'Chapter → script → audio'));
      const wave = el('div', undefined, 'waveform');
      for (let i=0;i<30;i++) wave.append(el('i'));
      card.append(wave);box.append(card);
    } else if (id === 'assessment') {
      const card = el('div', undefined, 'preview-question');
      card.append(el('small','CANDIDATE SHEET'),el('strong','What would you do next, and why?'),el('div',undefined,'answer-lines'));box.append(card);
    } else {
      const card = el('div', undefined, 'preview-sheet');
      card.append(el('small','REFERENCE GUIDE'),el('strong','Compare the possibilities'));
      const table = el('div',undefined,'preview-table');
      ['When to consider it','What distinguishes it','What to do next'].forEach(text=>table.append(el('span',text)));
      card.append(table);box.append(card);
    }
    return box;
  }
  fetch(new URL('assets/workflow-setups.json', document.baseURI))
    .then(response => { if (!response.ok) throw Error('setups unavailable'); return response.json(); })
    .then(setups => {
      const grid=el('div',undefined,'use-case-grid');
      setups.forEach(setup=>{
        const card=el('article',undefined,'use-case');card.id=`use-case-${setup.id}`;
        const body=el('div',undefined,'use-case-body');
        body.append(el('h3',setup.name),el('p',setup.description),el('p',setup.delivery,'output-line'));
        const actions=el('div',undefined,'use-case-actions');
        const use=el('button','Use this setup','button button-secondary');use.type='button';use.setAttribute('aria-label',`Use ${setup.name.toLowerCase()} setup`);
        use.addEventListener('click',()=>{document.querySelector('.nav-link[data-view="workflows"]').click();window.dispatchEvent(new CustomEvent('lamina:setup',{detail:setup}));});
        const download=el('a','Download JSON');download.download=`${setup.id}-setup.json`;
        download.href='data:application/json;charset=utf-8,'+encodeURIComponent(JSON.stringify({brief:setup.brief,options:setup.options},null,2)+'\n');
        download.setAttribute('aria-label',`Download ${setup.name.toLowerCase()} setup JSON`);
        actions.append(use,download);body.append(actions);card.append(preview(setup.id),body);grid.append(card);
      });
      host.replaceChildren(grid);
    }).catch(()=>{host.replaceChildren(el('p','Use cases could not load. Reload the page to try again.'));});
  const copy=document.getElementById('copy-install');
  copy?.addEventListener('click',async()=>{try{await navigator.clipboard.writeText(document.getElementById('install-command').textContent);copy.textContent='Copied';setTimeout(()=>{copy.textContent='Copy';},1800);}catch{copy.textContent='Select the commands to copy';}});
  document.querySelector('[data-open-replay]')?.addEventListener('click',()=>window.dispatchEvent(new Event('lamina:replay')));
})();
