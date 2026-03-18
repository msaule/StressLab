const state = {
  library: null,
  selectedPresetId: null,
  controls: {},
};

const nodes = {};
const CONTROL_ORDER = ["utilization", "coupling", "slack", "shock_intensity"];
const CONTROL_WEIGHTS = {
  utilization: 1.6,
  coupling: 1.0,
  slack: 1.0,
  shock_intensity: 1.1,
};

document.addEventListener("DOMContentLoaded", async () => {
  [
    "demo-claim",
    "demo-stats",
    "preset-list",
    "control-list",
    "match-scenario",
    "reset-controls",
    "match-note",
    "scenario-chip",
    "result-cards",
    "result-figure",
    "figure-title",
    "figure-caption",
    "result-explanation",
    "bottleneck-list",
    "edge-list",
  ].forEach((id) => {
    nodes[id] = document.getElementById(id);
  });

  nodes["match-scenario"].addEventListener("click", renderMatchedScenario);
  nodes["reset-controls"].addEventListener("click", resetControls);

  const response = await fetch("assets/static_demo/scenario_library.json");
  state.library = await response.json();
  state.selectedPresetId = state.library.presets[0].id;
  nodes["demo-claim"].textContent = state.library.claim;
  renderStats();
  renderPresets();
  renderControls();
  renderMatchedScenario();
});

function renderStats() {
  const stats = state.library.flagship_stats;
  const cards = [
    ["Systems", String(stats.systems)],
    ["Families", String(stats.topology_families)],
    ["Transition band", String(stats.shared_transition_band)],
    ["Margin shrink", String(stats.coupling_margin_shrink)],
  ];
  nodes["demo-stats"].innerHTML = cards
    .map(([label, value]) => `
      <div class="card">
        <div class="metric">${escapeHtml(value)}</div>
        <div>${escapeHtml(label)}</div>
      </div>
    `)
    .join("");
}

function currentPreset() {
  return state.library.presets.find((preset) => preset.id === state.selectedPresetId);
}

function renderPresets() {
  nodes["preset-list"].innerHTML = state.library.presets
    .map((preset) => `
      <button class="preset-option ${preset.id === state.selectedPresetId ? "active" : ""}" type="button" data-preset-id="${escapeHtml(preset.id)}">
        <strong>${escapeHtml(preset.label)}</strong>
        <span>${escapeHtml(preset.description)}</span>
      </button>
    `)
    .join("");
  nodes["preset-list"].querySelectorAll("[data-preset-id]").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedPresetId = button.dataset.presetId;
      renderPresets();
      resetControls();
    });
  });
}

function renderControls() {
  const preset = currentPreset();
  state.controls = { ...preset.default_controls };
  nodes["control-list"].innerHTML = CONTROL_ORDER.map((key) => {
    const spec = state.library.controls[key];
    return `
      <div class="slider-group">
        <div class="slider-head">
          <label for="control-${escapeHtml(key)}">${escapeHtml(spec.label)}</label>
          <strong id="value-${escapeHtml(key)}">${Number(state.controls[key]).toFixed(2)}x</strong>
        </div>
        <input id="control-${escapeHtml(key)}" type="range" min="${spec.min}" max="${spec.max}" step="${spec.step}" value="${state.controls[key]}">
      </div>
    `;
  }).join("");

  CONTROL_ORDER.forEach((key) => {
    const input = document.getElementById(`control-${key}`);
    const valueNode = document.getElementById(`value-${key}`);
    input.addEventListener("input", () => {
      state.controls[key] = Number(input.value);
      valueNode.textContent = `${Number(input.value).toFixed(2)}x`;
    });
  });
}

function resetControls() {
  renderControls();
  renderMatchedScenario();
}

function renderMatchedScenario() {
  const preset = currentPreset();
  const match = nearestScenario(preset, state.controls);
  const scenario = match.scenario;
  const result = scenario.result;
  const matchedControls = scenario.controls;
  nodes["match-note"].innerHTML = `
    <p><strong>Matched scenario:</strong> ${escapeHtml(scenario.title)}</p>
    <p class="note">${escapeHtml(scenario.description)}</p>
    <p class="note">Distance to your sliders: ${match.distance.toFixed(3)}. Displaying the nearest real precomputed run for this preset.</p>
    <p class="note">Matched controls: util ${matchedControls.utilization.toFixed(2)}x, coupling ${matchedControls.coupling.toFixed(2)}x, slack ${matchedControls.slack.toFixed(2)}x, shock ${matchedControls.shock_intensity.toFixed(2)}x.</p>
  `;
  nodes["scenario-chip"].textContent = scenario.title;
  renderResultCards(preset, scenario);
  nodes["result-figure"].src = result.figure.path;
  nodes["result-figure"].alt = `${preset.label} scenario figure`;
  nodes["figure-title"].textContent = `${preset.label} · ${scenario.title}`;
  nodes["figure-caption"].textContent = result.figure.caption;
  nodes["result-explanation"].textContent = result.explanation;
  renderList(nodes["bottleneck-list"], result.bottlenecks, "No material bottleneck surfaced in this scenario.");
  renderList(nodes["edge-list"], result.critical_edges, "No route-level stressor dominated this scenario.");
}

function renderResultCards(preset, scenario) {
  const result = scenario.result;
  const riskClass = riskClassName(result.collapse_risk.label);
  const intervention = result.best_intervention;
  nodes["result-cards"].innerHTML = [
    `
      <div class="card demo-card">
        <div class="kicker">Collapse risk</div>
        <div class="metric">${escapeHtml(result.collapse_risk.label)}</div>
        <div class="pill ${riskClass}">score ${Number(result.collapse_risk.score).toFixed(2)}</div>
      </div>
    `,
    `
      <div class="card demo-card">
        <div class="kicker">Failure margin</div>
        <div class="metric">${Number(result.failure_margin.best_shock_budget).toFixed(2)}</div>
        <div>${escapeHtml(result.failure_margin.label)} margin</div>
      </div>
    `,
    `
      <div class="card demo-card">
        <div class="kicker">Best intervention</div>
        <div class="metric demo-intervention">${escapeHtml(intervention ? intervention.label : "None ranked")}</div>
        <div>${escapeHtml(intervention ? `${intervention.target} · cost ${Math.round(intervention.cost)}` : preset.story)}</div>
      </div>
    `,
    `
      <div class="card demo-card">
        <div class="kicker">Operational readout</div>
        <div class="metric">${Number(result.metrics.utilization).toFixed(2)}</div>
        <div>utilization · wait ${Number(result.metrics.mean_wait).toFixed(2)} · throughput ${Number(result.metrics.throughput).toFixed(2)}</div>
      </div>
    `,
  ].join("");
}

function nearestScenario(preset, controls) {
  let best = null;
  for (const scenario of preset.scenarios) {
    const distance = controlDistance(controls, scenario.controls);
    if (!best || distance < best.distance) {
      best = { scenario, distance };
    }
  }
  return best;
}

function controlDistance(left, right) {
  let total = 0;
  for (const key of CONTROL_ORDER) {
    const spec = state.library.controls[key];
    const span = Number(spec.max) - Number(spec.min);
    const delta = span > 0 ? (Number(left[key]) - Number(right[key])) / span : 0;
    total += Math.pow(delta * CONTROL_WEIGHTS[key], 2);
  }
  return Math.sqrt(total);
}

function renderList(node, items, emptyMessage) {
  if (!items || items.length === 0) {
    node.innerHTML = `<li>${escapeHtml(emptyMessage)}</li>`;
    return;
  }
  node.innerHTML = items.map((item) => `<li>${escapeHtml(item)}</li>`).join("");
}

function riskClassName(label) {
  if (label === "High") {
    return "high";
  }
  if (label === "Moderate") {
    return "moderate";
  }
  return "low";
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
