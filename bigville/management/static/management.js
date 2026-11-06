(() => {
  "use strict";
  const API = "/api/management/v1";
  const $ = selector => document.querySelector(selector);
  const status = $("#catalog-status");
  const errorPanel = $("#catalog-error");
  const errorMessage = $("#catalog-error-message");
  const scenarioList = $("#scenario-list");
  const backendList = $("#backend-list");
  const runsPanel = $("#runs-panel");
  const runList = $("#run-list");
  const runsStatus = $("#runs-load-status");
  const form = $("#new-run-form");
  let capabilityCatalog = null;
  let reviewed = null;
  let submissionKey = null;
  let submitting = false;
  let draftRevision = 0;

  function activatePanel(button) {
    document.querySelectorAll(".nav-item").forEach(item => {
      item.classList.toggle("active", item === button);
      if (item === button) item.setAttribute("aria-current", "page");
      else item.removeAttribute("aria-current");
    });
    showPanel(button.getAttribute("aria-controls"), button.textContent.trim());
  }

  function showPanel(panelId, title) {
    document.querySelectorAll(".panel").forEach(panel => {
      panel.hidden = panel.id !== panelId;
    });
    const runsButton = document.querySelector("button[aria-controls='runs-panel']");
    const currentButton = document.querySelector(`button[aria-controls='${panelId}']`) ||
      (panelId === "new-run-panel" ? runsButton : null);
    document.querySelectorAll(".nav-item").forEach(item => {
      item.classList.toggle("active", item === currentButton);
      if (item === currentButton) item.setAttribute("aria-current", "page");
      else item.removeAttribute("aria-current");
    });
    $("#page-title").textContent = title;
    $("#intro-copy").textContent = panelId === "runs-panel"
      ? "Create, find and monitor autonomous simulations."
      : panelId === "new-run-panel"
        ? "Review the resolved configuration before starting a simulation."
        : "Review scenarios and integrations available in this checkout.";
  }

  document.querySelectorAll(".nav-item:not(:disabled)").forEach(button => {
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
    $("#scenario-count").textContent = `${scenarios.length} discovered`;
    $("#scenario-empty").hidden = scenarios.length !== 0;
    const select = $("#scenario-id");
    const selected = select.value;
    select.replaceChildren(new Option("Choose a scenario", ""));
    for (const scenario of scenarios) {
      const option = new Option(`${scenario.name || scenario.id} · ${scenario.id}`, scenario.id);
      select.add(option);

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
    if (scenarios.some(scenario => scenario.id === selected)) select.value = selected;
  }

  function renderBackends(backends) {
    backendList.replaceChildren();
    $("#backend-empty").hidden = backends.length !== 0;
    const simple = backends.find(backend => backend.kind === "simple");
    $("#default-backend").disabled = !simple || simple.available !== true;
    if (!simple || simple.available !== true) {
      setFieldErrors({default_backend: simple?.reason || "Simple backend is unavailable."});
    }
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

  function clearErrors() {
    document.querySelectorAll(".field-error").forEach(element => {
      element.textContent = "";
      element.hidden = true;
    });
    form.querySelectorAll("input,select").forEach(element => element.removeAttribute("aria-describedby"));
    $("#action-error").hidden = true;
  }

  function setFieldErrors(errors) {
    for (const [field, message] of Object.entries(errors || {})) {
      const target = $(`#error-${CSS.escape(field)}`);
      if (target) {
        target.textContent = String(message);
        target.hidden = false;
        const input = $(`[name='${CSS.escape(field)}']`);
        if (input) input.setAttribute("aria-describedby", target.id);
      } else {
        $("#error-review").textContent = String(message);
        $("#error-review").hidden = false;
      }
    }
  }

  function showActionError(message, fields) {
    $("#action-error-message").textContent = message;
    $("#action-error").hidden = false;
    setFieldErrors(fields || {});
  }

  function invalidateReview() {
    draftRevision += 1;
    reviewed = null;
    submissionKey = null;
    $("#review-panel").hidden = true;
    $("#create-start").disabled = true;
    if (!submitting) $("#validate-preview").disabled = false;
    $("#validation-status").textContent = "Changes have not been reviewed.";
    clearErrors();
  }

  function setFormBusy(busy) {
    form.querySelectorAll("input,select,button").forEach(element => {
      element.disabled = busy;
    });
    $("#back-to-runs").disabled = busy;
  }

  for (const input of form.querySelectorAll("input,select")) {
    input.addEventListener("input", invalidateReview);
    input.addEventListener("change", invalidateReview);
  }

  $("#new-run-button").addEventListener("click", () => {
    showPanel("new-run-panel", "New run");
    $("#run-name").focus();
  });
  $("#back-to-runs").addEventListener("click", () => {
    showPanel("runs-panel", "Runs");
    refreshRuns();
    $("#new-run-button").focus();
  });
  $("#cadence-choice").addEventListener("change", event => {
    const custom = $("#custom-cadence");
    custom.hidden = event.target.value !== "custom";
    if (!custom.hidden) custom.focus();
  });
  $("#random-seed").addEventListener("click", () => {
    const seed = crypto.getRandomValues(new Uint32Array(1))[0];
    $("#world-seed").value = String(seed);
    invalidateReview();
    $("#world-seed").focus();
  });

  function currentDraft() {
    const rawSeed = $("#world-seed").value;
    const seed = rawSeed === "" ? null : Number(rawSeed);
    const cadenceChoice = $("#cadence-choice").value;
    let ticksPerPeriod = cadenceChoice;
    if (cadenceChoice === "none") ticksPerPeriod = null;
    else if (cadenceChoice === "custom") ticksPerPeriod = Number($("#custom-cadence").value);
    const rawLimit = $("#turn-limit").value;
    return {
      scenario_id: $("#scenario-id").value,
      name: $("#run-name").value,
      seed,
      autonomous: true,
      default_backend: $("#default-backend").value,
      ticks_per_period: ticksPerPeriod,
      turn_limit: rawLimit === "" ? null : Number(rawLimit),
    };
  }

  async function requestJson(path, options = {}) {
    const response = await fetch(`${API}${path}`, {
      ...options,
      headers: {"Content-Type": "application/json", Accept: "application/json", ...(options.headers || {})},
    });
    let data;
    try { data = await response.json(); }
    catch { throw new Error(`Server returned HTTP ${response.status} without JSON details.`); }
    if (!response.ok) {
      const error = data && data.error ? data.error : {};
      const failure = new Error(error.message || `Request failed (HTTP ${response.status}).`);
      failure.code = error.code;
      failure.fields = error.fields || {};
      failure.status = response.status;
      throw failure;
    }
    return data;
  }

  function displayReview(draft, validation, preview) {
    const config = preview.canonical_config;
    const summary = $("#review-summary");
    summary.replaceChildren();
    const rows = [
      ["Run name", draft.name], ["Scenario", draft.scenario_id], ["World seed", draft.seed],
      ["Default backend", config.default_backend], ["Run mode", "Autonomous"],
      ["Ticks per period", draft.ticks_per_period === null ? "Disabled" : draft.ticks_per_period],
      ["Turn limit", draft.turn_limit == null ? "No limit" : draft.turn_limit],
    ];
    for (const [label, value] of rows) {
      const wrapper = document.createElement("div");
      wrapper.append(text("dt", label), text("dd", value));
      summary.append(wrapper);
    }
    const actors = $("#review-cast");
    actors.replaceChildren();
    for (const actor of preview.cast.actors) {
      const row = document.createElement("li");
      row.textContent = `${actor.name} · ${actor.backend} (${actor.backend_source.replaceAll("_", " ")})`;
      actors.append(row);
    }
    if (preview.cast.truncated) actors.append(text("li", `Showing ${preview.cast.actors.length} of ${preview.cast.count} residents.`));
    if (!preview.cast.count) actors.append(text("li", "No residents in this scenario."));
    const switches = $("#review-subsystems");
    switches.replaceChildren();
    for (const [name, enabled] of Object.entries(config.physical_subsystems || {})) {
      switches.append(text("li", `${name}: ${enabled ? "on" : "off"}`));
    }
    if (!switches.childElementCount) switches.append(text("li", "No subsystem details reported."));
    const map = preview.map;
    $("#map-summary").textContent = map.available
      ? `${map.width} × ${map.height} cells${map.truncated ? " · display truncated" : ""} · ${Object.entries(map.tile_counts).map(([name, count]) => `${name} ${count}`).join(" · ")}`
      : "This scenario has no map.";
    const symbolKeys = Object.keys(map.tile_counts);
    const symbolMap = new Map(symbolKeys.map((key, index) => [key, "ABCDEFGHIJKLMNOPQRSTUVWXYZ"[index % 26]]));
    const rendered = map.grid.map(row => row.map(tile => symbolMap.get(tile) || "?").join("")).join("\n");
    $("#map-grid").textContent = rendered || "No map grid available.";
    $("#map-grid").title = symbolKeys.map(key => `${symbolMap.get(key)} = ${key}`).join(", ");
    $("#config-hash").textContent = preview.configuration_hash;
    $("#review-warning").hidden = validation.warnings.length === 0;
    $("#review-warning").textContent = validation.warnings.join(" ");
    $("#review-panel").hidden = false;
    $("#create-start").disabled = false;
    reviewed = {
      draft: structuredClone(draft),
      configHash: validation.configuration_hash,
      capabilityRevision: validation.capability_revision,
    };
  }

  async function validateAndPreview() {
    if (submitting) return;
    clearErrors();
    invalidateReview();
    const requestRevision = draftRevision;
    const draft = currentDraft();
    $("#validation-status").textContent = "Validating draft…";
    $("#validate-preview").disabled = true;
    try {
      const validation = await requestJson("/run-drafts/validate", {
        method: "POST", body: JSON.stringify(draft),
      });
      if (requestRevision !== draftRevision) return;
      if (!validation.valid) {
        setFieldErrors(validation.errors);
        $("#validation-status").textContent = "Fix the highlighted fields and validate again.";
        return;
      }
      $("#validation-status").textContent = "Building a read-only preview…";
      const preview = await requestJson("/run-drafts/preview", {
        method: "POST", body: JSON.stringify(draft),
      });
      if (requestRevision !== draftRevision) return;
      if (preview.configuration_hash !== validation.configuration_hash ||
          preview.capability_revision !== validation.capability_revision) {
        setFieldErrors({expected_config_hash: "Capabilities changed while previewing. Validate again."});
        $("#validation-status").textContent = "Preview is stale. Validate again.";
        return;
      }
      displayReview(draft, validation, preview);
      $("#validation-status").textContent = "Preview ready. No run has been created yet.";
    } catch (error) {
      if (requestRevision !== draftRevision) return;
      setFieldErrors(error.fields || {});
      showActionError(error.message || "Validation or preview failed.", error.fields);
      $("#validation-status").textContent = "Draft could not be reviewed.";
    } finally {
      if (requestRevision === draftRevision) $("#validate-preview").disabled = false;
    }
  }
  $("#validate-preview").addEventListener("click", validateAndPreview);

  function renderRuns(runs) {
    runList.replaceChildren();
    $("#runs-empty").hidden = runs.length !== 0;
    for (const run of runs) {
      const card = document.createElement("article");
      card.className = "run-card";
      const info = document.createElement("div");
      info.className = "run-info";
      const heading = document.createElement("div");
      heading.className = "backend-head";
      heading.append(text("h3", run.name));
      heading.append(text("span", run.status, `run-status ${run.status}`));
      info.append(heading);
      const config = run.config || {};
      info.append(text("div", `${run.scenario_id} · seed ${config.seed} · turn ${run.turn}`, "run-meta"));
      if (run.error) info.append(text("p", run.error, "run-error"));
      const actions = document.createElement("div");
      actions.className = "run-actions";
      if (run.status === "created") actions.append(commandButton(run.id, "start", "Start"));
      if (["running", "paused", "waiting"].includes(run.status)) actions.append(commandButton(run.id, "stop", "Stop"));
      card.append(info, actions);
      runList.append(card);
    }
  }

  function commandButton(runId, command, label) {
    const button = text("button", label, command === "start" ? "secondary" : "text-button");
    button.type = "button";
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        await requestJson(`/runs/${encodeURIComponent(runId)}/commands`, {
          method: "POST", body: JSON.stringify({command}),
        });
        await refreshRuns();
      } catch (error) {
        showActionError(error.message, error.fields);
      } finally {
        button.disabled = false;
      }
    });
    return button;
  }

  async function refreshRuns(quiet = false) {
    if (!quiet) runsStatus.textContent = "Loading runs…";
    try {
      const response = await requestJson("/runs");
      renderRuns(response.runs || []);
      runsStatus.textContent = response.runs.length ? `${response.runs.length} run${response.runs.length === 1 ? "" : "s"}` : "";
      runsStatus.hidden = response.runs.length === 0;
    } catch (error) {
      runsStatus.hidden = false;
      runsStatus.textContent = `Could not load runs: ${error.message}`;
    }
  }

  function newIdempotencyKey() {
    return typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : Array.from(crypto.getRandomValues(new Uint32Array(4)), value => value.toString(16)).join("");
  }

  async function createAndStart() {
    if (submitting || !reviewed) return;
    submitting = true;
    const submission = structuredClone(reviewed);
    const revisionAtSubmit = draftRevision;
    const button = $("#create-start");
    button.disabled = true;
    setFormBusy(true);
    $("#launch-status").textContent = "Creating run…";
    clearErrors();
    submissionKey ||= newIdempotencyKey();
    try {
      const run = await requestJson("/runs", {
        method: "POST",
        body: JSON.stringify({
          draft: submission.draft,
          idempotency_key: submissionKey,
          expected_config_hash: submission.configHash,
          expected_capability_revision: submission.capabilityRevision,
        }),
      });
      $("#launch-status").textContent = "Run created. Starting…";
      const started = await requestJson(`/runs/${encodeURIComponent(run.id)}/commands`, {
        method: "POST", body: JSON.stringify({command: "start"}),
      });
      if (started.status === "failed") {
        showActionError(started.error || "Run was created but could not start.");
        $("#launch-status").textContent = "Run created but could not start.";
        await refreshRuns();
        return;
      }
      $("#launch-status").textContent = "Run started. Check its status in Runs.";
      reviewed = null;
      submissionKey = null;
      $("#review-panel").hidden = true;
      showPanel("runs-panel", "Runs");
      await refreshRuns();
    } catch (error) {
      if (draftRevision === revisionAtSubmit) {
        setFieldErrors(error.fields || {});
        showActionError(error.message || "Run could not be created.", error.fields);
        $("#launch-status").textContent = "Run was not started. Your draft is still here.";
        if (error.status === 409 || error.fields?.expected_config_hash || error.fields?.expected_capability_revision) {
          reviewed = null;
          submissionKey = null;
          button.disabled = true;
          $("#review-panel").hidden = true;
          $("#validation-status").textContent = "Capabilities changed. Review the draft again before launch.";
        }
      }
    } finally {
      submitting = false;
      setFormBusy(false);
      if (reviewed) button.disabled = false;
    }
  }
  $("#create-start").addEventListener("click", createAndStart);

  async function loadCatalog() {
    status.hidden = false;
    status.textContent = "Loading capability catalog…";
    errorPanel.hidden = true;
    try {
      const catalog = await requestJson("/capabilities");
      if (!Array.isArray(catalog.scenarios) || !Array.isArray(catalog.backends)) {
        throw new Error("Catalog response is missing scenario or backend data.");
      }
      capabilityCatalog = catalog;
      renderScenarios(catalog.scenarios);
      renderBackends(catalog.backends);
      const commit = catalog.engine_build && catalog.engine_build.git_commit;
      $("#build-label").textContent = commit ? `build ${commit.slice(0, 12)}` : "engine build unknown";
      status.textContent = `Catalog ready · ${catalog.scenarios.length} scenarios · ${catalog.backends.length} backends`;
    } catch (error) {
      status.hidden = true;
      errorMessage.textContent = error instanceof Error ? error.message : "Unexpected catalog error.";
      errorPanel.hidden = false;
    }
  }

  $("#retry-button").addEventListener("click", loadCatalog);
  loadCatalog();
  refreshRuns();
  window.setInterval(() => {
    if (!runsPanel.hidden) refreshRuns(true);
  }, 1500);
})();
