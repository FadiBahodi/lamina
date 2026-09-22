/* Public workflow explanations use the same options accepted by Projects. */
(() => {
  'use strict';
  const host = document.getElementById('workflow-explorer');
  if (!host) return;
  const el = (tag, text, cls) => { const node = document.createElement(tag); if(text !== undefined) node.textContent = text; if(cls) node.className = cls; return node; };
  fetch(new URL('assets/workflow-setups.json', document.baseURI))
    .then(response => { if (!response.ok) throw Error('setups unavailable'); return response.json(); })
    .then(setups => {
      const tabs = el('div', undefined, 'workflow-tabs'); tabs.setAttribute('role','tablist'); tabs.setAttribute('aria-label','Workflow examples');
      const panel = el('div', undefined, 'workflow-panel'); panel.id='workflow-panel'; panel.setAttribute('role','tabpanel');
      const buttons = [];
      function show(setup, index) {
        buttons.forEach((button,i) => { button.setAttribute('aria-selected', String(i===index)); button.tabIndex=i===index?0:-1; });
        panel.setAttribute('aria-labelledby',buttons[index].id);
        panel.replaceChildren();
        const intro=el('div',undefined,'workflow-intro'); intro.append(el('h3',setup.title),el('p',setup.description));
        const main=el('div',undefined,'workflow-main');
        const stages=el('ol',undefined,'workflow-stages'); stages.setAttribute('aria-label','Production stages');
        setup.stages.forEach(([title,body],i)=>{const row=el('li');row.append(el('span',String(i+1).padStart(2,'0'),'workflow-number'),el('h4',title),el('p',body));stages.append(row);});
        const reasoning=el('div',undefined,'workflow-reasoning');reasoning.append(el('h4','Why this arrangement'),el('p',setup.decision),el('h4','What each worker receives'),el('p',setup.context),el('h4','When you need a revision'),el('p',setup.revision));
        main.append(stages,reasoning);
        const setupBox=el('aside',undefined,'workflow-setup');setupBox.append(el('span','USE THIS WORKFLOW','section-index'),el('h4','Add your sources'),el('p',setup.inputs),el('h4','Open the result'),el('p',setup.delivery));
        const actions=el('div',undefined,'workflow-actions');
        const use=el('button','Use this setup','button button-primary');use.type='button';use.addEventListener('click',()=>{document.querySelector('.nav-link[data-view="workflows"]').click();window.dispatchEvent(new CustomEvent('lamina:setup',{detail:setup}));});
        const download=el('a','Download setup JSON','button button-secondary');download.download=`${setup.id}-setup.json`;
        download.href='data:application/json;charset=utf-8,'+encodeURIComponent(JSON.stringify({brief:setup.brief,options:setup.options},null,2)+'\n');
        const link=el('a','Run it from Python','text-button');link.href='https://github.com/FadiBahodi/lamina/blob/main/docs/workflow-design.md#reuse-a-setup';
        actions.append(use,download,link);setupBox.append(actions);
        const body=el('div',undefined,'workflow-body');body.append(main,setupBox);panel.append(intro,body);
      }
      setups.forEach((setup,index)=>{
        const button=el('button',setup.name);button.type='button';button.id=`workflow-tab-${setup.id}`;button.setAttribute('role','tab');button.setAttribute('aria-controls','workflow-panel');button.addEventListener('click',()=>show(setup,index));
        button.addEventListener('keydown',e=>{let next=index;if(e.key==='ArrowRight')next=(index+1)%setups.length;else if(e.key==='ArrowLeft')next=(index+setups.length-1)%setups.length;else if(e.key==='Home')next=0;else if(e.key==='End')next=setups.length-1;else return;e.preventDefault();buttons[next].focus();show(setups[next],next);});buttons.push(button);tabs.append(button);
      });
      host.replaceChildren(tabs,panel);show(setups[0],0);
    }).catch(()=>{host.replaceChildren(el('p','The workflow examples could not load. Reload this page or open the design guide on GitHub.'));});
})();
