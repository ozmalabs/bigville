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
  let backendProfiles = [];
  let reviewed = null;
  let submissionKey = null;
  let submitting = false;
  let draftRevision = 0;
  let activeRunId = null;
  let activeRunRecord = null;
  let selectedPerspective = "referee";
  let selectedAgent = null;
  let selectedRefereeResident = null;
  let viewRevision = 0;
  let viewController = null;
  let refereeSnapshot = null;
  let formDirty = false;
  let applyingTemplate = false;
  let loadedTemplateRef = null;
  let reportsRevision = 0;
  let reportsData = null;
  let eventsData = null;
  let eventsOffset = 0;
  const eventsLimit = 50;

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
        : panelId === "run-view-panel"
          ? "Observe the current run snapshot and choose a server-built perspective."
          : panelId === "reports-panel"
            ? "Inspect live measurements and events recorded by this run."
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
    const select = $("#default-backend");
    const previous = select.value;
    select.replaceChildren();
    for (const backend of backends) {
      const card = document.createElement("article");
      card.className = "backend-card";
      const heading = document.createElement("div");
      heading.className = "backend-head";
      heading.append(text("h3", `${backend.name} · ${backend.kind}`));
      const available = backend.available === true;
      const readiness = text("span", available ? "Ready" : "Unavailable", `readiness${available ? "" : " unavailable"}`);
      readiness.setAttribute("aria-label", `${backend.name}: ${available ? "ready" : "unavailable"}`);
      heading.append(readiness);
      card.append(heading);
      card.append(text("p", `Profile ${backend.id} · revision ${backend.revision}`));
      if (!available) card.append(text("p", backend.reason || "No availability details were provided."));
      backendList.append(card);
      const option = new Option(`${backend.name} · ${backend.kind}${available ? "" : " · unavailable"}`, backend.id);
      option.disabled = !available;
      select.add(option);
    }
    const simpleOption = [...select.options].find(option => option.value === "simple.default");
    if (simpleOption) simpleOption.value = "simple"; // retain the M01–M09 draft value alias
    if (![...select.options].some(option => option.value === previous && !option.disabled)) {
      select.value = select.options.find(option => !option.disabled)?.value || "";
    } else select.value = previous;
    select.disabled = !select.value;
  }

  function renderActorProfileControls(assignments = {}) {
    const scenarioId = $("#scenario-id").value;
    const scenario = capabilityCatalog?.scenarios?.find(item => item.id === scenarioId);
    const actors = scenario?.actors || [];
    const container = $("#actor-profile-assignments");
    container.replaceChildren();
    const authored = scenarioId && scenarioId !== "town100" && actors.length > 0;
    $("#actor-profile-fieldset").hidden = !authored;
    if (!authored) return;
    for (const actor of actors) {
      const row = document.createElement("div");
      row.className = "actor-profile-row";
      const label = text("label", actor.name);
      const select = document.createElement("select");
      select.dataset.actor = actor.name;
      const inherited = actor.scenario_backend
        ? `Inherit scenario profile (${actor.scenario_backend})`
        : "Inherit default profile";
      select.add(new Option(inherited, ""));
      for (const profile of backendProfiles) {
        if (!profile.available) continue;
        select.add(new Option(`${profile.name} · ${profile.kind}`, profile.id));
      }
      select.value = assignments[actor.name] || "";
      select.addEventListener("change", () => {
        if (applyingTemplate) return;
        formDirty = true;
        invalidateReview();
      });
      label.htmlFor = `actor-profile-${actor.name.replace(/[^a-zA-Z0-9_-]/g, "-")}`;
      select.id = label.htmlFor;
      row.append(label, select);
      container.append(row);
    }
  }

  $("#scenario-id").addEventListener("change", () => {
    const assignments = Object.fromEntries(
      [...$("#actor-profile-assignments").querySelectorAll("select[data-actor]")]
        .filter(select => select.value).map(select => [select.dataset.actor, select.value]));
    renderActorProfileControls(assignments);
  });

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
    $("#save-template").disabled = true;
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
    input.addEventListener("input", () => {
      if (applyingTemplate) return;
      formDirty = true;
      invalidateReview();
    });
    input.addEventListener("change", () => {
      if (applyingTemplate) return;
      formDirty = true;
      invalidateReview();
    });
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
    const selectedProfileId = $("#default-backend").value === "simple"
      ? "simple.default" : $("#default-backend").value;
    const selectedProfile = backendProfiles.find(profile => profile.id === selectedProfileId);
    const result = {
      scenario_id: $("#scenario-id").value,
      name: $("#run-name").value,
      seed,
      autonomous: true,
      default_backend: selectedProfile?.kind || selectedProfileId,
      ticks_per_period: ticksPerPeriod,
      turn_limit: rawLimit === "" ? null : Number(rawLimit),
    };
    if (selectedProfile) result.default_profile_id = selectedProfile.id;
    const actorProfiles = {};
    for (const select of $("#actor-profile-assignments").querySelectorAll("select[data-actor]")) {
      if (select.value) actorProfiles[select.dataset.actor] = select.value;
    }
    if (Object.keys(actorProfiles).length) result.actor_backend_profiles = actorProfiles;
    return result;
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
      ["Default profile", `${config.default_profile_id} · revision ${config.default_profile_revision}`],
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
    const assignments = new Map((preview.profile_assignments || []).map(item => [item.actor, item]));
    for (const actor of preview.cast.actors) {
      const row = document.createElement("li");
      row.append(text("span", `${actor.name} · ${actor.backend} (${actor.backend_source.replaceAll("_", " ")})`));
      const assignment = assignments.get(actor.name);
      if (assignment) row.append(text("small", `${assignment.profile_id} · revision ${assignment.profile_revision}`));
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
    $("#save-template").disabled = false;
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
      const open = text("button", "Open run", "text-button");
      open.type = "button";
      open.addEventListener("click", () => openRun(run));
      actions.append(open);
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
        if (activeRunId === runId && !$("#run-view-panel").hidden) await refreshRunView();
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

  function selectedTemplate() {
    const raw = $("#template-choice").value;
    if (!raw) return null;
    const [id, versionText] = raw.split("|");
    const version = Number(versionText);
    return id && Number.isInteger(version) ? {id, version} : null;
  }

  async function refreshTemplates() {
    try {
      const response = await requestJson("/templates");
      const select = $("#template-choice");
      const previous = select.value;
      select.replaceChildren();
      for (const template of response.templates || []) {
        const details = await requestJson(`/templates/${encodeURIComponent(template.id)}`);
        for (const version of details.versions) {
          const option = new Option(`${template.name} · v${version.version}`, `${template.id}|${version.version}`);
          select.add(option);
        }
      }
      if (!select.options.length) select.add(new Option("No saved templates", ""));
      if ([...select.options].some(option => option.value === previous)) select.value = previous;
      const available = Boolean(selectedTemplate());
      $("#inspect-template").disabled = !available;
      $("#load-template").disabled = !available;
      $("#template-status").textContent = response.templates?.length
        ? `${response.templates.length} template${response.templates.length === 1 ? "" : "s"} · versions are immutable`
        : "No templates saved yet.";
    } catch (error) {
      $("#template-status").textContent = `Templates unavailable: ${error.message}`;
    }
  }

  async function inspectTemplate() {
    const ref = selectedTemplate();
    if (!ref) return;
    try {
      const data = await requestJson(`/templates/${encodeURIComponent(ref.id)}/versions/${ref.version}`);
      $("#template-inspection").textContent = JSON.stringify({
        id: data.id, version: data.version, name: data.name,
        configuration_hash: data.configuration_hash,
        capability_revision: data.capability_revision, draft_schema: data.schema_version,
        draft: data.draft,
      }, null, 2);
      $("#template-inspection").hidden = false;
      $("#template-status").textContent = `Inspecting ${data.name} · version ${data.version}.`;
    } catch (error) {
      $("#template-status").textContent = error.message;
    }
  }

  function applyDraftToForm(draft) {
    applyingTemplate = true;
    $("#run-name").value = draft.name;
    const scenario = $("#scenario-id");
    if (![...scenario.options].some(option => option.value === draft.scenario_id)) {
      scenario.add(new Option(`${draft.scenario_id} · unavailable`, draft.scenario_id));
    }
    scenario.value = draft.scenario_id;
    const profileId = draft.default_profile_id ||
      backendProfiles.find(profile => profile.kind === (draft.default_backend === "cheap" ? "simple" : draft.default_backend) && profile.available)?.id;
    const profileChoice = profileId === "simple.default" ? "simple" : profileId;
    if (profileChoice && [...$("#default-backend").options].some(option => option.value === profileChoice)) {
      $("#default-backend").value = profileChoice;
    }
    renderActorProfileControls(draft.actor_backend_profiles || {});
    $("#world-seed").value = String(draft.seed);
    $("#cadence-choice").value = draft.ticks_per_period === "world"
      ? "world" : draft.ticks_per_period === null ? "none" : "custom";
    $("#custom-cadence").value = draft.ticks_per_period == null || draft.ticks_per_period === "world"
      ? "" : String(draft.ticks_per_period);
    $("#custom-cadence").hidden = $("#cadence-choice").value !== "custom";
    $("#turn-limit").value = draft.turn_limit == null ? "" : String(draft.turn_limit);
    applyingTemplate = false;
    formDirty = false;
    invalidateReview();
    formDirty = false;
  }

  async function loadTemplateIntoDraft() {
    const ref = selectedTemplate();
    if (!ref) return;
    if (formDirty && !window.confirm("Replace this modified draft with the selected template version?")) return;
    const revisionAtLoad = draftRevision;
    $("#template-status").textContent = "Checking template compatibility…";
    try {
      const loaded = await requestJson(`/templates/${encodeURIComponent(ref.id)}/versions/${ref.version}/load`);
      if (revisionAtLoad !== draftRevision) {
        $("#template-status").textContent = "The draft changed while checking this template. Load it again to replace the current draft.";
        return;
      }
      applyDraftToForm(loaded.draft);
      loadedTemplateRef = {id: loaded.id, version: loaded.version,
                           configuration_hash: loaded.configuration_hash};
      $("#template-name").value = loaded.name;
      showPanel("new-run-panel", "New run from template");
      $("#template-status").textContent = `Loaded immutable version ${loaded.version}. Validate and preview it before launch.`;
      await validateAndPreview();
    } catch (error) {
      $("#template-status").textContent = `${error.message}${error.fields ? ` ${JSON.stringify(error.fields)}` : ""}`;
    }
  }

  async function saveReviewedTemplate() {
    if (!reviewed || submitting) return;
    const body = {name: $("#template-name").value.trim() || reviewed.draft.name,
                  draft: structuredClone(reviewed.draft)};
    const sourceTemplate = loadedTemplateRef ? {...loadedTemplateRef} : null;
    const revisionAtSave = draftRevision;
    if (sourceTemplate?.id) body.template_id = sourceTemplate.id;
    $("#save-template").disabled = true;
    $("#template-save-status").textContent = "Saving immutable version…";
    try {
      const saved = await requestJson("/templates", {method: "POST", body: JSON.stringify(body)});
      if (revisionAtSave === draftRevision) {
        loadedTemplateRef = {id: saved.id, version: saved.version,
                             configuration_hash: saved.configuration_hash};
      }
      $("#template-name").value = saved.name;
      $("#template-save-status").textContent = `Saved ${saved.name} · version ${saved.version}.`;
      await refreshTemplates();
      $("#template-choice").value = `${saved.id}|${saved.version}`;
    } catch (error) {
      $("#template-save-status").textContent = error.message;
    } finally {
      $("#save-template").disabled = !reviewed;
    }
  }

  $("#inspect-template").addEventListener("click", inspectTemplate);
  $("#load-template").addEventListener("click", loadTemplateIntoDraft);
  $("#template-choice").addEventListener("change", () => {
    const enabled = Boolean(selectedTemplate());
    $("#inspect-template").disabled = !enabled;
    $("#load-template").disabled = !enabled;
  });
  $("#save-template").addEventListener("click", saveReviewedTemplate);

  function resetRefereePanel() {
    refereeSnapshot = null;
    selectedRefereeResident = null;
    const frame = $("#referee-renderer");
    frame.hidden = true;
    frame.onload = null;
    frame.removeAttribute("src");
    delete frame.dataset.runId;
    $("#referee-view").hidden = true;
    $("#resident-rows").replaceChildren();
    $("#resident-detail").replaceChildren();
    $("#mapless-fallback").hidden = true;
  }

  function agentNames(record) {
    return (record?.resolved_actor_backends || []).map(item => item.actor).filter(Boolean);
  }

  function fillAgentSelector(record) {
    const select = $("#agent-resident");
    const names = agentNames(record);
    const prior = selectedAgent;
    select.replaceChildren();
    for (const name of names) select.add(new Option(name, name));
    if (names.includes(prior)) select.value = prior;
    else {
      selectedAgent = names[0] || null;
      if (selectedAgent) select.value = selectedAgent;
    }
    $("#agent-resident-choice").hidden = selectedPerspective !== "agent";
    select.disabled = names.length === 0;
  }

  function populateResidentDetail(resident) {
    const target = $("#resident-detail");
    target.replaceChildren();
    if (!resident) return;
    const heading = text("h4", `${resident.name} · ${resident.role || "resident"}`);
    const details = document.createElement("dl");
    const position = Array.isArray(resident.position) ? resident.position.join(", ") : "Unknown";
    const fields = [
      ["Status", resident.alive ? "Alive" : "Dead"], ["Health", resident.health],
      ["Life stage", resident.life_stage], ["Position", position],
      ["Energy", resident.energy], ["Hunger", resident.hunger],
      ["Household", resident.household], ["Backend", resident.backend?.kind || "simple"],
    ];
    for (const [label, value] of fields) {
      const item = document.createElement("div");
      item.append(text("dt", label), text("dd", value == null || value === "" ? "Unknown" : value));
      details.append(item);
    }
    target.append(heading, details);
  }

  function renderResidents(snapshot) {
    const rows = $("#resident-rows");
    rows.replaceChildren();
    const residents = snapshot.world?.residents || [];
    if (!residents.length) {
      rows.append(text("tr", ""));
      $("#resident-detail").textContent = "No residents are present in this scenario.";
      return;
    }
    for (const resident of residents) {
      const row = document.createElement("tr");
      const nameCell = document.createElement("td");
      const inspect = text("button", resident.name, "resident-link");
      inspect.type = "button";
      inspect.addEventListener("click", () => {
        selectedRefereeResident = resident.id;
        populateResidentDetail(resident);
      });
      nameCell.append(inspect);
      const position = Array.isArray(resident.position) ? resident.position.join(", ") : "Unknown";
      row.append(nameCell, text("td", resident.role || "Unknown"),
                 text("td", resident.alive ? "Alive" : "Dead"), text("td", position));
      rows.append(row);
    }
    const selected = residents.find(resident => resident.id === selectedRefereeResident) || residents[0];
    selectedRefereeResident = selected.id;
    populateResidentDetail(selected);
  }

  function sendSnapshotToRenderer(snapshot, runId, revision) {
    const frame = $("#referee-renderer");
    if (selectedPerspective !== "referee" || activeRunId !== runId ||
        revision !== viewRevision || !frame.contentWindow) return;
    frame.contentWindow.postMessage({
      type: "management-referee-snapshot", run_id: runId, snapshot,
    }, location.origin);
  }

  function showRefereeSnapshot(response, revision) {
    refereeSnapshot = response.snapshot;
    $("#agent-view").hidden = true;
    $("#referee-view").hidden = false;
    renderResidents(refereeSnapshot);
    const map = refereeSnapshot.world?.map || {};
    const hasMap = Number(map.width) > 0 && Number(map.height) > 0 && Array.isArray(map.grid) && map.grid.length > 0;
    const frame = $("#referee-renderer");
    if (!hasMap) {
      frame.hidden = true;
      frame.removeAttribute("src");
      delete frame.dataset.runId;
      $("#mapless-fallback").hidden = false;
      return;
    }
    $("#mapless-fallback").hidden = true;
    frame.hidden = false;
    if (frame.dataset.runId !== activeRunId) {
      frame.dataset.runId = activeRunId;
      frame.onload = () => sendSnapshotToRenderer(refereeSnapshot, activeRunId, viewRevision);
      frame.src = `/management/renderer.html?run_id=${encodeURIComponent(activeRunId)}`;
    } else {
      sendSnapshotToRenderer(refereeSnapshot, activeRunId, revision);
    }
  }

  function renderRunControls(record) {
    const controls = $("#run-view-controls");
    controls.replaceChildren();
    const commands = {
      created: [["start", "Start"], ["step", "Step"], ["stop", "Stop"]],
      running: [["pause", "Pause"], ["stop", "Stop"]],
      paused: [["resume", "Resume"], ["step", "Step"], ["stop", "Stop"]],
      waiting: [["stop", "Stop"]],
    }[record.status] || [];
    for (const [command, label] of commands) {
      const button = text("button", label, command === "stop" ? "secondary" : "primary");
      button.type = "button";
      button.addEventListener("click", async () => {
        button.disabled = true;
        try {
          const updated = await requestJson(`/runs/${encodeURIComponent(record.id)}/commands`, {
            method: "POST", body: JSON.stringify({command}),
          });
          if (updated.error) showActionError(updated.error);
          await refreshRunView();
          await refreshRuns(true);
        } catch (error) {
          showActionError(error.message, error.fields);
        } finally {
          button.disabled = false;
        }
      });
      controls.append(button);
    }
    if (record.status === "waiting") {
      controls.append(text("p", "This run is waiting for human input. Input handling is not available yet.", "run-error"));
    }
  }

  function renderCheckpoints(record) {
    const list = $("#checkpoint-list");
    list.replaceChildren();
    const checkpoints = record.checkpoints || [];
    const unsupportedBackend = (record.resolved_actor_profiles || [])
      .some(item => !["simple", "cheap"].includes(item.backend)) ||
      (record.resolved_actor_backends || []).some(item => !["simple", "cheap"].includes(item.backend));
    $("#checkpoint-status").textContent = unsupportedBackend
      ? "Unavailable: this run uses provider-owned cognition without a compatible game restore adapter."
      : checkpoints.length
        ? `${checkpoints.length} immutable checkpoint${checkpoints.length === 1 ? "" : "s"}`
        : "No checkpoints saved for this run.";
    $("#create-checkpoint").disabled = ["starting", "waiting"].includes(record.status) ||
      !(record.turn > 0) || unsupportedBackend;
    for (const checkpoint of checkpoints) {
      const item = document.createElement("li");
      item.className = "checkpoint-item";
      const detail = text("span", `Turn ${checkpoint.turn} · ${new Date(checkpoint.created_at).toLocaleString()} · ${checkpoint.id}`);
      const fork = text("button", "Fork", "secondary");
      fork.type = "button";
      fork.addEventListener("click", async () => {
        fork.disabled = true;
        try {
          const child = await requestJson(`/runs/${encodeURIComponent(record.id)}/checkpoints/${encodeURIComponent(checkpoint.id)}/fork`, {
            method: "POST", body: "{}",
          });
          await refreshRuns();
          await openRun(child);
        } catch (error) {
          showActionError(error.message, error.fields);
        } finally {
          fork.disabled = false;
        }
      });
      item.append(detail, fork);
      list.append(item);
    }
  }

  $("#create-checkpoint").addEventListener("click", async event => {
    const button = event.currentTarget;
    if (!activeRunId) return;
    button.disabled = true;
    $("#checkpoint-status").textContent = "Saving checkpoint…";
    try {
      const checkpoint = await requestJson(`/runs/${encodeURIComponent(activeRunId)}/checkpoints`, {
        method: "POST", body: "{}",
      });
      $("#checkpoint-status").textContent = `Saved checkpoint at turn ${checkpoint.turn}.`;
      await refreshRunView();
    } catch (error) {
      $("#checkpoint-status").textContent = error.message;
    } finally {
      button.disabled = false;
    }
  });

  async function refreshRunView() {
    if (!activeRunId || $("#run-view-panel").hidden) return;
    const revision = ++viewRevision;
    if (viewController) viewController.abort();
    viewController = new AbortController();
    const signal = viewController.signal;
    $("#run-view-error").hidden = true;
    $("#run-view-status").textContent = "Refreshing";
    try {
      const record = await requestJson(`/runs/${encodeURIComponent(activeRunId)}`, {signal});
      if (revision !== viewRevision) return;
      activeRunRecord = record;
      $("#run-view-heading").textContent = record.name;
      $("#run-view-status").textContent = record.status;
      $("#run-view-status").className = `run-status ${record.status}`;
      const config = record.config || {};
      $("#run-view-meta").textContent = `${record.scenario_id} · seed ${config.seed} · turn ${record.turn}`;
      if (record.error) {
        $("#run-view-error").textContent = record.error;
        $("#run-view-error").hidden = false;
      }
      renderRunControls(record);
      renderCheckpoints(record);
      fillAgentSelector(record);

      if (selectedPerspective === "agent") {
        $("#referee-view").hidden = true;
        $("#agent-view").hidden = false;
        $("#agent-view-content").textContent = "";
        if (!selectedAgent) {
          $("#agent-view-status").textContent = "No resident is available for agent view.";
          return;
        }
        $("#agent-view-status").textContent = `Loading ${selectedAgent}'s view…`;
        const data = await requestJson(
          `/runs/${encodeURIComponent(activeRunId)}/views/agent?actor=${encodeURIComponent(selectedAgent)}`,
          {signal},
        );
        if (revision !== viewRevision) return;
        $("#agent-view-content").textContent = JSON.stringify(data.view, null, 2);
        $("#agent-view-status").textContent = `${data.actor} · resident perspective · turn ${data.run.turn}`;
        return;
      }

      $("#agent-view").hidden = true;
      $("#referee-view").hidden = false;
      const data = await requestJson(`/runs/${encodeURIComponent(activeRunId)}/views/referee`, {signal});
      if (revision !== viewRevision) return;
      showRefereeSnapshot(data, revision);
      $("#run-view-status").textContent = `${data.run.status} · turn ${data.run.turn}`;
      $("#run-view-meta").textContent = `${record.scenario_id} · seed ${config.seed} · turn ${data.run.turn}`;
    } catch (error) {
      if (revision !== viewRevision || error.name === "AbortError") return;
      $("#run-view-error").textContent = error.message || "Run view is unavailable.";
      $("#run-view-error").hidden = false;
      if (selectedPerspective === "agent") {
        $("#agent-view").hidden = false;
        $("#agent-view-status").textContent = "Resident perspective is unavailable.";
      } else {
        resetRefereePanel();
      }
      $("#run-view-status").textContent = activeRunRecord?.status || "Unavailable";
    }
  }

  function clearAgentPerspective() {
    $("#agent-view-content").textContent = "";
    $("#agent-view-status").textContent = "Choose a resident to load their agent view.";
    $("#agent-view").hidden = true;
  }

  async function openRun(run) {
    if (viewController) viewController.abort();
    viewRevision += 1;
    resetRefereePanel();
    clearAgentPerspective();
    activeRunId = run.id;
    activeRunRecord = run;
    selectedPerspective = "referee";
    selectedAgent = agentNames(run)[0] || null;
    $("#perspective-choice").value = "referee";
    $("#agent-resident-choice").hidden = true;
    showPanel("run-view-panel", run.name);
    await refreshRunView();
  }

  function downloadJson(filename, value) {
    const blob = new Blob([JSON.stringify(value, null, 2) + "\n"], {type: "application/json"});
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.append(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  function eventQuery() {
    const params = new URLSearchParams({offset: String(eventsOffset), limit: String(eventsLimit)});
    const kind = $("#event-kind-filter").value.trim();
    const actor = $("#event-actor-filter").value.trim();
    if (kind) params.set("kind", kind);
    if (actor) params.set("actor", actor);
    return params.toString();
  }

  async function refreshReportEvents() {
    if (!activeRunId || $("#reports-panel").hidden) return;
    const revision = ++reportsRevision;
    const id = encodeURIComponent(activeRunId);
    $("#report-error").hidden = true;
    $("#reports-run-status").textContent = "Loading";
    try {
      const [report, events] = await Promise.all([
        requestJson(`/runs/${id}/report`),
        requestJson(`/runs/${id}/events?${eventQuery()}`),
      ]);
      if (revision !== reportsRevision || id !== encodeURIComponent(activeRunId)) return;
      reportsData = report;
      eventsData = events;
      $("#reports-heading").textContent = report.run.name;
      $("#reports-run-status").textContent = `${report.run.status} · turn ${report.run.turn}`;
      $("#report-provenance").textContent = `Live state · captured ${report.captured_at} · turn ${report.run.turn}`;
      $("#report-json").textContent = JSON.stringify(report.report, null, 2);
      $("#download-report").disabled = false;
      $("#events-provenance").textContent = `Recorded world history · as of turn ${events.run.turn}; this is not a reconstructed timeline.`;
      const list = $("#event-list");
      list.replaceChildren();
      for (const event of events.events) {
        const row = document.createElement("li");
        const kind = event.kind || "Unclassified event";
        row.append(text("strong", kind));
        row.append(text("pre", JSON.stringify(event, null, 2), "artifact-event"));
        list.append(row);
      }
      if (!events.events.length) list.append(text("li", "No recorded events match these filters.", "empty"));
      const pagination = events.pagination;
      const first = pagination.total ? pagination.offset + 1 : 0;
      const last = pagination.offset + events.events.length;
      $("#events-page-status").textContent = `${first}–${last} of ${pagination.total}`;
      $("#events-previous").disabled = pagination.offset === 0;
      $("#events-next").disabled = pagination.next_offset === null;
      $("#download-events").disabled = false;
    } catch (error) {
      if (revision !== reportsRevision) return;
      $("#report-error").textContent = error.message || "Report and event data are unavailable.";
      $("#report-error").hidden = false;
      $("#reports-run-status").textContent = activeRunRecord?.status || "Unavailable";
      $("#download-report").disabled = true;
      $("#download-events").disabled = true;
    }
  }

  $("#open-reports").addEventListener("click", () => {
    if (selectedPerspective !== "referee") return;
    eventsOffset = 0;
    showPanel("reports-panel", activeRunRecord?.name || "Run report");
    refreshReportEvents();
  });
  $("#back-from-reports").addEventListener("click", () => {
    reportsRevision += 1;
    showPanel("run-view-panel", activeRunRecord?.name || "Run");
    refreshRunView();
  });
  $("#apply-event-filter").addEventListener("click", () => {
    eventsOffset = 0;
    refreshReportEvents();
  });
  $("#events-previous").addEventListener("click", () => {
    eventsOffset = Math.max(0, eventsOffset - eventsLimit);
    refreshReportEvents();
  });
  $("#events-next").addEventListener("click", () => {
    eventsOffset += eventsLimit;
    refreshReportEvents();
  });
  $("#download-report").addEventListener("click", () => {
    if (reportsData) downloadJson(`bigville-report-${reportsData.run.id}.json`, reportsData);
  });
  $("#download-events").addEventListener("click", () => {
    if (eventsData) downloadJson(`bigville-events-${eventsData.run.id}-${eventsData.pagination.offset}.json`, eventsData);
  });

  $("#back-from-run-view").addEventListener("click", () => {
    if (viewController) viewController.abort();
    viewRevision += 1;
    activeRunId = null;
    activeRunRecord = null;
    resetRefereePanel();
    clearAgentPerspective();
    showPanel("runs-panel", "Runs");
    refreshRuns();
  });

  $("#perspective-choice").addEventListener("change", () => {
    selectedPerspective = $("#perspective-choice").value;
    if (viewController) viewController.abort();
    viewRevision += 1;
    if (selectedPerspective === "agent") {
      resetRefereePanel();
      $("#agent-view").hidden = false;
      $("#agent-resident-choice").hidden = false;
    } else {
      clearAgentPerspective();
      $("#agent-resident-choice").hidden = true;
    }
    refreshRunView();
  });

  $("#agent-resident").addEventListener("change", () => {
    selectedAgent = $("#agent-resident").value || null;
    if (selectedPerspective === "agent") refreshRunView();
  });

  function newIdempotencyKey() {
    return typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : Array.from(crypto.getRandomValues(new Uint32Array(4)), value => value.toString(16)).join("");
  }

  async function createAndStart() {
    if (submitting || !reviewed) return;
    submitting = true;
    const submission = structuredClone(reviewed);
    if (loadedTemplateRef) submission.template = {id: loadedTemplateRef.id, version: loadedTemplateRef.version};
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
          ...(submission.template ? {template: submission.template} : {}),
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
      loadedTemplateRef = null;
      formDirty = false;
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
      const [catalog, profileCatalog] = await Promise.all([
        requestJson("/capabilities"), requestJson("/backend-profiles"),
      ]);
      if (!Array.isArray(catalog.scenarios) || !Array.isArray(catalog.backends) ||
          !Array.isArray(profileCatalog.profiles)) {
        throw new Error("Catalog response is missing scenario or backend profile data.");
      }
      capabilityCatalog = catalog;
      backendProfiles = profileCatalog.profiles;
      renderScenarios(catalog.scenarios);
      renderBackends(backendProfiles);
      renderActorProfileControls();
      const commit = catalog.engine_build && catalog.engine_build.git_commit;
      $("#build-label").textContent = commit ? `build ${commit.slice(0, 12)}` : "engine build unknown";
      status.textContent = `Catalog ready · ${catalog.scenarios.length} scenarios · ${backendProfiles.length} backend profiles`;
    } catch (error) {
      status.hidden = true;
      errorMessage.textContent = error instanceof Error ? error.message : "Unexpected catalog error.";
      errorPanel.hidden = false;
    }
  }

  $("#retry-button").addEventListener("click", loadCatalog);
  loadCatalog();
  refreshRuns();
  refreshTemplates();
  window.setInterval(() => {
    if (!runsPanel.hidden) refreshRuns(true);
    else if (!$("#run-view-panel").hidden) refreshRunView();
  }, 1500);
})();
