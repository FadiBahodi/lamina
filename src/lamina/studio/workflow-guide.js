/* Editable project presets; these are configurations, not generated outputs. */
(() => {
  "use strict";
  const host = document.getElementById("workflow-explorer");
  if (!host) return;
  function el(tag, text, cls) {
    const item = document.createElement(tag);
    if (text !== undefined) item.textContent = text;
    if (cls) item.className = cls;
    return item;
  }
  fetch(new URL("assets/workflow-setups.json", document.baseURI))
    .then(response => { if (!response.ok) throw Error("Project setups unavailable"); return response.json(); })
    .then(setups => {
      const list = el("div", undefined, "procedure-choices");
      setups.forEach(setup => {
        const button = el("button", undefined, "procedure-choice");
        button.type = "button";
        button.append(el("strong", setup.name), el("span", setup.description));
        button.addEventListener("click", () => {
          window.dispatchEvent(new CustomEvent("lamina:setup", {detail:setup}));
          host.closest("details").open = false;
          document.getElementById("production-workbench").scrollIntoView({behavior:"smooth"});
        });
        list.append(button);
      });
      host.replaceChildren(list);
    })
    .catch(error => host.replaceChildren(el("p", error.message + ". Enter your project directly below.")));
})();
