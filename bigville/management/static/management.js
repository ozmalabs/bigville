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
      if (scenario.cast_generation) {
        const capability = scenario.cast_generation;
        const castRow = document.createElement("li");
        castRow.append(text("strong", "Generated cast: "), document.createTextNode(
          `schema v${capability.schema_version} · up to ${capability.max_generated} additional residents · roles ${(capability.roles || []).join(", ")}`));
        list.append(castRow);
      }
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
      select.value = [...select.options].find(option => !option.disabled)?.value || "";
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

  function renderPhysicalSubsystemControls(overrides = {}) {
    const scenario = capabilityCatalog?.scenarios?.find(item => item.id === $("#scenario-id").value);
    const container = $("#physical-subsystem-controls");
    container.replaceChildren();
    const entries = capabilityCatalog?.physical_subsystems || [];
    $("#physical-subsystems-fieldset").hidden = !scenario || !entries.length;
    if (!scenario) return;
    for (const item of entries) {
      const row = document.createElement("div");
      row.className = "subsystem-control-row";
      const label = text("label", item.name.replaceAll("_", " "));
      const select = document.createElement("select");
      select.dataset.subsystem = item.name;
      const scenarioValue = scenario.physical_subsystems?.[item.name] ?? item.default;
      const source = scenario.physical_subsystem_sources?.[item.name] === "scenario_override"
        ? "scenario" : "engine default";
      select.add(new Option(`Inherit · ${scenarioValue ? "on" : "off"} (${source})`, ""));
      select.add(new Option("On", "true"));
      select.add(new Option("Off", "false"));
      if (Object.hasOwn(overrides, item.name)) select.value = String(overrides[item.name]);
      select.addEventListener("change", () => {
        if (!applyingTemplate) { formDirty = true; invalidateReview(); }
      });
      label.htmlFor = `physical-subsystem-${item.name.replace(/[^a-zA-Z0-9_-]/g, "-")}`;
      select.id = label.htmlFor;
      row.append(label, select);
      if (item.description) row.append(text("small", item.description));
      container.append(row);
    }
  }

  function castFeature() {
    const selected = capabilityCatalog?.scenarios?.find(item => item.id === $("#scenario-id").value);
    return selected?.cast_generation || null;
  }

  function addCastGroup(initial = {}) {
    const feature = castFeature();
    if (!feature) return;
    const container = $("#cast-generation-groups");
    const row = document.createElement("fieldset");
    row.className = "cast-group-row";
    const number = container.children.length + 1;
    const legend = document.createElement("legend");
    legend.textContent = `Cast group ${number}`;
    row.append(legend);
    const field = (labelText, control) => {
      const wrapper = document.createElement("label");
      wrapper.className = "field";
      wrapper.append(text("span", labelText), control);
      row.append(wrapper);
      return control;
    };
    const id = field("Group ID", Object.assign(document.createElement("input"), {
      type: "text", value: initial.id || `group-${number}`, maxLength: 24,
    }));
    const count = field("Population", Object.assign(document.createElement("input"), {
      type: "number", min: "1", max: String(feature.max_generated), step: "1",
      value: String(initial.count ?? 2),
    }));
    const role = field("Role", document.createElement("select"));
    for (const value of feature.roles || []) role.add(new Option(value, value));
    role.value = initial.role || feature.roles?.[0] || "";
    const profile = field("Backend profile", document.createElement("select"));
    for (const item of backendProfiles.filter(value => value.available)) {
      profile.add(new Option(`${item.name} · ${item.kind}`, item.id));
    }
    profile.value = initial.backend_profile_id || "simple.default";
    const range = (trait, key, defaultValue) => field(`${trait} ${key}`, Object.assign(document.createElement("input"), {
      type: "number", min: trait === "Age" ? "0" : "0", max: trait === "Age" ? "120" : "1",
      step: "any", value: String(initial.traits?.[trait.toLowerCase()]?.[key] ?? defaultValue),
    }));
    const ageMin = range("Age", "min", 18);
    const ageMax = range("Age", "max", 60);
    const skillMin = range("Skill", "min", 0.1);
    const skillMax = range("Skill", "max", 0.9);
    id.dataset.castField = "id";
    count.dataset.castField = "count";
    role.dataset.castField = "role";
    profile.dataset.castField = "backend_profile_id";
    for (const [control, key] of [[ageMin, "age-min"], [ageMax, "age-max"],
                                  [skillMin, "skill-min"], [skillMax, "skill-max"]]) {
      control.dataset.castField = key;
    }
    const remove = text("button", "Remove group", "text-button");
    remove.type = "button";
    remove.addEventListener("click", () => {
      row.remove();
      updateCastGenerationTotal();
      if (!applyingTemplate) { formDirty = true; invalidateReview(); }
    });
    row.append(remove);
    row.addEventListener("input", () => {
      updateCastGenerationTotal();
      if (!applyingTemplate) { formDirty = true; invalidateReview(); }
    });
    row.addEventListener("change", () => {
      updateCastGenerationTotal();
      if (!applyingTemplate) { formDirty = true; invalidateReview(); }
    });
    container.append(row);
    updateCastGenerationTotal();
  }

  function renderCastGenerationControls(spec = null) {
    const feature = castFeature();
    const fieldset = $("#cast-generation-fieldset");
    const enabled = Boolean(feature && spec);
    fieldset.hidden = !feature || $("#scenario-id").value === "town100";
    $("#enable-cast-generation").checked = enabled;
    $("#cast-generation-editor").hidden = !enabled;
    const container = $("#cast-generation-groups");
    container.replaceChildren();
    if (enabled) {
      for (const group of spec.groups || []) addCastGroup(group);
      if (!container.children.length) addCastGroup();
    }
    updateCastGenerationTotal();
  }

  function updateCastGenerationTotal() {
    const rows = [...$("#cast-generation-groups").children];
    const total = rows.reduce((sum, row) => {
      const value = Number(row.querySelector("[data-cast-field=count]")?.value);
      return sum + (Number.isInteger(value) && value > 0 ? value : 0);
    }, 0);
    $("#cast-generation-total").textContent = rows.length
      ? `${total} generated resident${total === 1 ? "" : "s"} across ${rows.length} group${rows.length === 1 ? "" : "s"}. Scenario capacity: ${castFeature()?.max_generated ?? 0}.`
      : "Add a group to generate residents.";
  }

  function currentCastGeneration() {
    if (!$("#enable-cast-generation").checked) return null;
    const groups = [...$("#cast-generation-groups").children].map(row => {
      const values = Object.fromEntries([...row.querySelectorAll("[data-cast-field]")]
        .map(control => [control.dataset.castField, control.value]));
      return {id: values.id, count: Number(values.count), role: values.role,
        backend_profile_id: values.backend_profile_id,
        traits: {age: {min: Number(values["age-min"]), max: Number(values["age-max"])},
          skill: {min: Number(values["skill-min"]), max: Number(values["skill-max"])}}};
    });
    return {schema_version: 1, groups};
  }

  $("#enable-cast-generation").addEventListener("change", () => {
    const enabled = $("#enable-cast-generation").checked;
    $("#cast-generation-editor").hidden = !enabled;
    if (enabled && !$("#cast-generation-groups").children.length) addCastGroup();
    updateCastGenerationTotal();
    if (!applyingTemplate) { formDirty = true; invalidateReview(); }
  });
  $("#add-cast-group").addEventListener("click", () => {
    addCastGroup();
    formDirty = true;
    invalidateReview();
  });

  $("#scenario-id").addEventListener("change", () => {
    const assignments = Object.fromEntries(
      [...$("#actor-profile-assignments").querySelectorAll("select[data-actor]")]
        .filter(select => select.value).map(select => [select.dataset.actor, select.value]));
    renderActorProfileControls(assignments);
    renderPhysicalSubsystemControls();
    renderCastGenerationControls();
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
      autonomous: $("#run-mode").value !== "human",
      default_backend: selectedProfile?.kind || selectedProfileId,
      ticks_per_period: ticksPerPeriod,
      turn_limit: rawLimit === "" ? null : Number(rawLimit),
      turn_semantics: $("#turn-semantics").value,
      executor: $("#executor").value,
      executor_workers: Number($("#executor-workers").value),
      affordance_mode: $("#affordance-mode").value,
      snapshot_mode: $("#snapshot-mode").value,
      rule_batching: $("#rule-batching").value,
      llm_log: $("#llm-log").checked,
    };
    if (!result.autonomous && $("#human-player").value) result.player = $("#human-player").value;
    if (selectedProfile) result.default_profile_id = selectedProfile.id;
    const actorProfiles = {};
    for (const select of $("#actor-profile-assignments").querySelectorAll("select[data-actor]")) {
      if (select.value) actorProfiles[select.dataset.actor] = select.value;
    }
    if (Object.keys(actorProfiles).length) result.actor_backend_profiles = actorProfiles;
    const physicalSubsystems = {};
    for (const select of $("#physical-subsystem-controls").querySelectorAll("select[data-subsystem]")) {
      if (select.value !== "") physicalSubsystems[select.dataset.subsystem] = select.value === "true";
    }
    if (Object.keys(physicalSubsystems).length) result.physical_subsystems = physicalSubsystems;
    const castGeneration = currentCastGeneration();
    if (castGeneration) result.cast_generation = castGeneration;
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

  function renderHumanPlayerChoices(actors, selected = "") {
    const select = $("#human-player");
    select.replaceChildren(new Option("Choose a player resident", ""));
    for (const actor of actors) {
      const name = typeof actor === "string" ? actor : actor.name;
      if (name) select.add(new Option(name, name));
    }
    if (actors.some(actor => (typeof actor === "string" ? actor : actor.name) === selected)) {
      select.value = selected;
    }
  }

  $("#run-mode").addEventListener("change", () => {
    const human = $("#run-mode").value === "human";
    $("#human-player-fieldset").hidden = !human;
    if (!human) $("#human-player").value = "";
  });
  $("#human-player").addEventListener("change", () => {
    const player = $("#human-player").value;
    for (const select of $("#actor-profile-assignments").querySelectorAll("select[data-actor]")) {
      if (select.dataset.actor === player) select.value = "";
    }
  });

  $("#load-player-cast").addEventListener("click", async () => {
    const draft = currentDraft();
    draft.autonomous = true;
    delete draft.player;
    const button = $("#load-player-cast");
    button.disabled = true;
    $("#validation-status").textContent = "Resolving the cast for player selection…";
    try {
      const data = await requestJson("/run-drafts/preview", {
        method: "POST", body: JSON.stringify(draft),
      });
      renderHumanPlayerChoices(data.cast.actors, "");
      $("#validation-status").textContent = `Choose one of ${data.cast.count} resolved residents as the player.`;
      $("#human-player").focus();
    } catch (error) {
      showActionError(error.message, error.fields);
      $("#validation-status").textContent = "Player choices could not be loaded.";
    } finally {
      button.disabled = false;
    }
  });

  function displayReview(draft, validation, preview) {
    const config = preview.canonical_config;
    const summary = $("#review-summary");
    summary.replaceChildren();
    const rows = [
      ["Run name", draft.name], ["Scenario", draft.scenario_id], ["World seed", draft.seed],
      ["Default backend", config.default_backend],
      ["Run mode", config.autonomous ? "Autonomous" : `Human-controlled · ${config.player}`],
      ["Default profile", `${config.default_profile_id} · revision ${config.default_profile_revision}`],
      ["Ticks per period", draft.ticks_per_period === null ? "Disabled" : draft.ticks_per_period],
      ["Turn limit", draft.turn_limit == null ? "No limit" : draft.turn_limit],
      ["Turn semantics", config.turn_semantics], ["Executor", `${config.executor} · ${config.executor_workers} workers`],
      ["Affordances", config.affordance_mode], ["Snapshots", config.snapshot_mode], ["Rule batching", config.rule_batching],
      ["LLM interaction logs", config.llm_log ? "Enabled" : "Disabled"],
    ];
    if (config.cast_generation_version != null) {
      rows.push(["Generated cast", `${config.generated_cast.length} residents · generator v${config.cast_generation_version}`]);
    }
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
    for (const group of preview.cast.groups || []) {
      const details = document.createElement("details");
      const summary = text("summary", `${group.id} · ${group.role} · ${group.count} · ${group.backend_profile_id}`);
      const members = document.createElement("ul");
      for (const name of group.actors) members.append(text("li", name));
      details.append(summary, members);
      const item = document.createElement("li");
      item.append(details);
      actors.append(item);
    }
    const switches = $("#review-subsystems");
    switches.replaceChildren();
    for (const [name, enabled] of Object.entries(config.physical_subsystems || {})) {
      const source = config.physical_subsystem_sources?.[name] || "engine_default";
      switches.append(text("li", `${name.replaceAll("_", " ")}: ${enabled ? "on" : "off"} · ${source.replaceAll("_", " ")}`));
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
    const comparisonSelect = $("#compare-runs");
    const previousSelection = new Set([...comparisonSelect.selectedOptions].map(option => option.value));
    comparisonSelect.replaceChildren();
    for (const run of runs) {
      const option = new Option(`${run.name} · ${run.scenario_id} · turn ${run.turn}`, run.id);
      option.selected = previousSelection.has(run.id);
      comparisonSelect.add(option);
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

  $("#compare-button").addEventListener("click", async () => {
    const run_ids = [...$("#compare-runs").selectedOptions].map(option => option.value);
    $("#compare-results").replaceChildren();
    $("#compare-status").textContent = "Comparing recorded snapshots…";
    try {
      const comparison = await requestJson("/reports/compare", {
        method: "POST", body: JSON.stringify({run_ids}),
      });
      const table = document.createElement("table");
      table.className = "comparison-table";
      const head = document.createElement("thead");
      const headerRow = document.createElement("tr");
      const metricHeading = text("th", "Metric");
      const unitHeading = text("th", "Unit");
      metricHeading.scope = "col";
      unitHeading.scope = "col";
      headerRow.append(metricHeading, unitHeading);
      for (const item of comparison.runs) {
        const runHeading = text("th", `${item.run.name} · ${item.run.id}`);
        runHeading.scope = "col";
        headerRow.append(runHeading);
      }
      head.append(headerRow);
      const body = document.createElement("tbody");
      for (const [metric, details] of Object.entries(comparison.metrics)) {
        const row = document.createElement("tr");
        const metricName = text("th", metric);
        metricName.scope = "row";
        row.append(metricName, text("td", details.unit));
        for (const value of details.values) row.append(text("td", value.value == null ? `Unavailable: ${value.missing_reason}` : String(value.value)));
        body.append(row);
      }
      table.append(head, body);
      $("#compare-results").append(table);
      $("#compare-status").textContent = comparison.compatible
        ? `Compatible recorded report schema: ${comparison.report_schema}.`
        : "Some reports are missing or use incompatible schemas; affected values are unavailable.";
    } catch (error) {
      $("#compare-status").textContent = error.message || "Comparison could not be loaded.";
    }
  });

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
    $("#run-mode").value = draft.autonomous === false ? "human" : "autonomous";
    $("#human-player-fieldset").hidden = draft.autonomous !== false;
    renderHumanPlayerChoices(draft.player ? [draft.player] : [], draft.player || "");
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
    renderPhysicalSubsystemControls(draft.physical_subsystems || {});
    renderCastGenerationControls(draft.cast_generation || null);
    $("#world-seed").value = String(draft.seed);
    $("#cadence-choice").value = draft.ticks_per_period === "world"
      ? "world" : draft.ticks_per_period === null ? "none" : "custom";
    $("#custom-cadence").value = draft.ticks_per_period == null || draft.ticks_per_period === "world"
      ? "" : String(draft.ticks_per_period);
    $("#custom-cadence").hidden = $("#cadence-choice").value !== "custom";
    $("#turn-limit").value = draft.turn_limit == null ? "" : String(draft.turn_limit);
    $("#turn-semantics").value = draft.turn_semantics || "sequential";
    $("#executor").value = draft.executor || "serial";
    $("#executor-workers").value = String(draft.executor_workers || 4);
    $("#affordance-mode").value = draft.affordance_mode || "auto";
    $("#snapshot-mode").value = draft.snapshot_mode || "auto";
    $("#rule-batching").value = draft.rule_batching || "auto";
    $("#llm-log").checked = draft.llm_log !== false;
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
      controls.append(text("p", record.config?.autonomous === false
        ? "Waiting for the selected player to choose an action."
        : "This run is waiting for human input that this configuration cannot accept.", "run-error"));
    }
  }

  async function renderHumanTurn(record, revision, signal) {
    const panel = $("#human-turn-panel");
    const options = $("#human-action-options");
    options.replaceChildren();
    if (record.config?.autonomous !== false || record.status !== "waiting") {
      panel.hidden = true;
      $("#human-agent-view").textContent = "";
      return;
    }
    panel.hidden = false;
    $("#human-turn-status").textContent = "Loading the player's current agent view…";
    try {
      const prompt = await requestJson(
        `/runs/${encodeURIComponent(record.id)}/player-prompt`, {signal});
      if (revision !== viewRevision) return;
      $("#human-agent-view").textContent = JSON.stringify(prompt.view, null, 2);
      $("#human-turn-status").textContent = prompt.mode === "reaction"
        ? `${prompt.actor} must answer a contested take at turn ${prompt.turn}.`
        : `${prompt.actor} · choose one action for turn ${prompt.turn}.`;
      const choices = prompt.mode === "reaction"
        ? (prompt.reactions || []).map(value => ({selection: value, label: `React: ${value}`}))
        : (prompt.actions || []).map(row => ({selection: row.handle,
            label: [row.action, row.what].filter(Boolean).join(" · ")}));
      for (const choice of choices) {
        const button = text("button", choice.label || choice.selection, "secondary");
        button.type = "button";
        button.addEventListener("click", async () => {
          button.disabled = true;
          $("#human-turn-status").textContent = "Applying your choice…";
          try {
            await requestJson(`/runs/${encodeURIComponent(record.id)}/player-input`, {
              method: "POST", body: JSON.stringify({token: prompt.token,
                turn: prompt.turn, selection: choice.selection}),
            });
            await refreshRunView();
            await refreshRuns(true);
          } catch (error) {
            $("#human-turn-status").textContent = error.message || "Input was rejected.";
            button.disabled = false;
          }
        });
        options.append(button);
      }
      if (!choices.length) $("#human-turn-status").textContent = "No supported player actions are currently available.";
    } catch (error) {
      if (revision !== viewRevision || error.name === "AbortError") return;
      $("#human-turn-status").textContent = error.message || "The player prompt is unavailable.";
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
      await renderHumanTurn(record, revision, signal);
      if (revision !== viewRevision) return;

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
    selectedPerspective = run.config?.autonomous === false ? "agent" : "referee";
    selectedAgent = run.config?.player || agentNames(run)[0] || null;
    $("#perspective-choice").value = selectedPerspective;
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
  $("#capture-report").addEventListener("click", async () => {
    if (!activeRunId) return;
    const button = $("#capture-report");
    button.disabled = true;
    $("#snapshot-status").textContent = "Recording snapshot…";
    try {
      const snapshot = await requestJson(`/runs/${encodeURIComponent(activeRunId)}/report-snapshots`, {
        method: "POST", body: "{}",
      });
      $("#snapshot-status").textContent = `Recorded ${snapshot.id} at turn ${snapshot.run.turn}.`;
    } catch (error) {
      $("#snapshot-status").textContent = error.message || "Report snapshot could not be recorded.";
    } finally {
      button.disabled = false;
    }
  });
  $("#download-reproducibility").addEventListener("click", async () => {
    if (!activeRunId) return;
    try {
      const metadata = await requestJson(`/runs/${encodeURIComponent(activeRunId)}/reproducibility`);
      downloadJson(`bigville-reproducibility-${metadata.run_id}.json`, metadata);
    } catch (error) {
      $("#snapshot-status").textContent = error.message || "Reproducibility metadata is unavailable.";
    }
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
      renderPhysicalSubsystemControls();
      renderCastGenerationControls();
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
