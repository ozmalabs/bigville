(() => {
  "use strict";
  const api = "/api/management/v1/capabilities";
  const status = document.querySelector("#catalog-status");
  const errorPanel = document.querySelector("#catalog-error");
  const errorMessage = document.querySelector("#catalog-error-message");
  const scenarioList = document.querySelector("#scenario-list");
  const backendList = document.querySelector("#backend-list");

  function activatePanel(button) {
    document.querySelectorAll(".nav-item").forEach(item => {
      item.classList.toggle("active", item === button);
      if (item === button) item.setAttribute("aria-current", "page");
      else item.removeAttribute("aria-current");
    });
    document.querySelectorAll(".panel").forEach(panel => {
      panel.hidden = panel.id !== button.getAttribute("aria-controls");
    });
    document.querySelector("#page-title").textContent = button.textContent.trim();
  }

  document.querySelectorAll(".nav-item").forEach(button => {
    button.addEventListener("click", () => activatePanel(button));
  });

  function text(tag, value, className) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    element.textContent = value == null ? "Unknown" : String(value);
    return element;
  }

  function renderScenarios(scenarios) {
    scenarioList.replaceChildren();
    document.querySelector("#scenario-count").textContent = `${scenarios.length} discovered`;
    document.querySelector("#scenario-empty").hidden = scenarios.length !== 0;
    for (const scenario of scenarios) {
      const card = document.createElement("article");
      card.className = "scenario-card";
      const heading = document.createElement("div");
      heading.className = "scenario-title";
      const title = document.createElement("div");
      title.append(text("h3", scenario.name || scenario.id));
      title.append(text("div", scenario.id, "scenario-id"));
      heading.append(title, text("span", scenario.source || "unknown source", "pill"));
      card.append(heading);
      const details = document.createElement("details");
      details.className = "details";
      details.append(text("summary", "Scenario details"));
      const list = document.createElement("ul");
      const hash = scenario.content_hash || `Unknown${scenario.content_hash_reason ? ` · ${scenario.content_hash_reason}` : ""}`;
      for (const [label, value] of [["Type", scenario.type], ["Source file", scenario.source_file || scenario.source], ["Content hash", hash]]) {
        const row = document.createElement("li");
        row.append(text("strong", `${label}: `), document.createTextNode(value == null ? "Unknown" : String(value)));
        list.append(row);
      }
      const subsystems = scenario.physical_subsystems || {};
      const switches = Object.entries(subsystems).map(([name, enabled]) => `${name}: ${enabled ? "on" : "off"}`).join(", ") || "No subsystem details reported";
      const row = document.createElement("li");
      row.append(text("strong", "Physical subsystems: "), document.createTextNode(switches));
      list.append(row);
      details.append(list);
      card.append(details);
      scenarioList.append(card);
    }
  }

  function renderBackends(backends) {
    backendList.replaceChildren();
    document.querySelector("#backend-empty").hidden = backends.length !== 0;
    for (const backend of backends) {
      const card = document.createElement("article");
      card.className = "backend-card";
      const heading = document.createElement("div");
      heading.className = "backend-head";
      heading.append(text("h3", backend.kind || "Unknown backend"));
      const available = backend.available === true;
      const readiness = text("span", available ? "Available" : "Unavailable", `readiness${available ? "" : " unavailable"}`);
      readiness.setAttribute("aria-label", `${backend.kind || "Backend"}: ${available ? "available" : "unavailable"}`);
      heading.append(readiness);
      card.append(heading);
      if (!available) card.append(text("p", backend.reason || "No availability details were provided."));
      backendList.append(card);
    }
  }

  async function loadCatalog() {
    status.hidden = false;
    status.textContent = "Loading capability catalog…";
    errorPanel.hidden = true;
    try {
      const response = await fetch(api, {headers: {Accept: "application/json"}});
      if (!response.ok) throw new Error(`Catalog request returned HTTP ${response.status}.`);
      const catalog = await response.json();
      if (!Array.isArray(catalog.scenarios) || !Array.isArray(catalog.backends)) {
        throw new Error("Catalog response is missing scenario or backend data.");
      }
      renderScenarios(catalog.scenarios);
      renderBackends(catalog.backends);
      const commit = catalog.engine_build && catalog.engine_build.git_commit;
      document.querySelector("#build-label").textContent = commit ? `build ${commit.slice(0, 12)}` : "engine build unknown";
      status.textContent = `Catalog ready · ${catalog.scenarios.length} scenarios · ${catalog.backends.length} backends`;
    } catch (error) {
      status.hidden = true;
      errorMessage.textContent = error instanceof Error ? error.message : "Unexpected catalog error.";
      errorPanel.hidden = false;
    }
  }

  document.querySelector("#retry-button").addEventListener("click", loadCatalog);
  loadCatalog();
})();
