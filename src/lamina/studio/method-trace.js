/* Display exported executions. This page does not run a model. */
(() => {
  'use strict';
  const root = document.getElementById('method-trace');
  if (!root) return;
  let example, selectedRun = 0, selectedNode;
  function el(tag, cls, value) {
    const element = document.createElement(tag);
    if (cls) element.className = cls;
    if (value !== undefined) element.textContent = value;
    return element;
  }
  function code(value) {
    const pre = el('pre', 'trace-code');
    pre.append(el('code', '', JSON.stringify(value, null, 2)));
    return pre;
  }
  function render() {
    root.replaceChildren();
    const run = example.runs[selectedRun];
    const receipt = run.receipt;
    const definitions = example.method.nodes;
    selectedNode ||= definitions.at(-1).id;
    const tabs = el('div', 'trace-tabs');
    tabs.setAttribute('role', 'tablist');
    tabs.setAttribute('aria-label', 'Recorded executions');
    ['Initial run', 'Change a source', 'Apply a review note'].forEach((title, index) => {
      const button = el('button', '', `${String(index + 1).padStart(2, '0')}  ${title}`);
      button.type = 'button';
      button.setAttribute('role', 'tab');
      button.setAttribute('aria-selected', String(index === selectedRun));
      button.tabIndex = index === selectedRun ? 0 : -1;
      button.addEventListener('click', () => { selectedRun = index; render(); root.querySelector('[aria-selected="true"]').focus({preventScroll:true}); });
      button.addEventListener('keydown', event => {
        if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
        event.preventDefault();
        selectedRun = (index + (event.key === 'ArrowRight' ? 1 : 2)) % 3;
        render(); root.querySelector('[aria-selected="true"]').focus({preventScroll:true});
      });
      tabs.append(button);
    });
    root.append(tabs);
    const statuses = Object.values(receipt.nodes);
    const executed = statuses.filter(n => n.status === 'executed').length;
    const cached = statuses.filter(n => n.status === 'cached').length;
    const summary = el('div', 'trace-summary');
    summary.append(el('p', 'trace-reason', run.reason));
    summary.append(el('span', 'trace-meta', `${executed} executed / ${cached} reused`));
    root.append(summary);
    const layout = el('div', 'trace-layout');
    const graphWrap = el('div', 'trace-map');
    graphWrap.append(el('div', 'trace-label', 'DEPENDENCY GRAPH'));
    const graph = el('div', 'trace-graph');
    definitions.forEach(definition => {
      const record = receipt.nodes[definition.id];
      const button = el('button', `trace-node${selectedNode === definition.id ? ' selected' : ''}`);
      button.type = 'button'; button.dataset.status = record.status;
      button.setAttribute('aria-pressed', String(selectedNode === definition.id));
      button.setAttribute('aria-label', `${definition.role}: ${record.status === 'cached' ? 'reused' : record.status}`);
      button.append(el('span', 'trace-node-status', record.status === 'cached' ? 'REUSED' : record.status.toUpperCase()), el('strong', '', definition.role), el('code', '', definition.id));
      button.addEventListener('click', () => { selectedNode = definition.id; render(); root.querySelector('.trace-node.selected').focus({preventScroll:true}); });
      graph.append(button);
    });
    graphWrap.append(graph, el('p', 'trace-map-note', 'The readers can run together. The editor starts after both finish.'));
    if (selectedRun === 2) {
      const observation = el('div', 'trace-observation');
      observation.append(el('span', 'trace-label', 'SELECTED OPERATOR OBSERVATION'), el('p', '', example.observation.note));
      graphWrap.append(observation);
    }
    const detail = el('div', 'trace-detail');
    const definition = definitions.find(n => n.id === selectedNode);
    const request = run.requests?.[selectedNode];
    const heading = el('div', 'trace-detail-heading');
    heading.append(el('h3', '', definition.role), el('span', 'trace-meta', receipt.nodes[selectedNode].status === 'cached' ? 'Saved result' : 'Executed in this run'));
    detail.append(heading);
    detail.append(el('p', 'trace-instruction', definition.instructions));
    const inputs = request?.input;
    if (inputs) {
      const packet = {task: inputs.task, dependencies: inputs.dependencies};
      if (inputs.experience?.length) packet.experience = inputs.experience.map(x => ({kind:x.kind, outcome:x.observation.outcome, applicability:x.observation.applicability, note:x.observation.note}));
      detail.append(el('div', 'trace-label', 'WORKER CONTEXT'), code(packet));
    } else detail.append(el('p', '', 'The request record is unavailable.'));
    detail.append(el('div', 'trace-label', 'RETURNED OUTPUT'), code(receipt.results[selectedNode]));
    layout.append(graphWrap, detail); root.append(layout);
    const footer = el('div', 'trace-foot');
    footer.append(el('span', '', 'Recorded execution and cache decisions'));
    const download = el('a', '', 'Execution data'); download.href = 'method-example.json'; footer.append(download); root.append(footer);
  }
  fetch(new URL('method-example.json', document.baseURI), {cache:'no-store'})
    .then(response => { if (!response.ok) throw Error('Execution example unavailable'); return response.json(); })
    .then(data => { example = data; render(); })
    .catch(() => { root.replaceChildren(el('p', 'inline-note', 'The recorded execution could not be loaded. The runnable example is in src/lamina/method_example.py.')); });
})();
