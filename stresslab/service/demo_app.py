"""Frontend V1 browser app for StressLab preset demos."""

from __future__ import annotations

DEMO_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>StressLab Demo</title>
  <style>
    :root {
      --bg:#f5f1e8;
      --panel:#fffdf8;
      --ink:#152534;
      --muted:#56646f;
      --accent:#8f5f3f;
      --accent-dark:#71452b;
      --border:#dfd6c4;
      --shadow:0 10px 30px rgba(21,37,52,0.08);
      --good:#2d6b3f;
      --warn:#9a5d00;
      --bad:#9b2c2c;
    }
    * { box-sizing:border-box; }
    body {
      margin:0;
      font-family:Georgia,"Times New Roman",serif;
      color:var(--ink);
      background:
        radial-gradient(circle at top left, rgba(143,95,63,0.10), transparent 28%),
        linear-gradient(180deg,#f7f3ec 0%,#fefcf8 320px,#ffffff 100%);
    }
    a { color:var(--accent-dark); text-decoration:none; }
    a:hover { text-decoration:underline; }
    .shell { max-width:1240px; margin:0 auto; padding:0 24px 56px; }
    .nav { display:flex; justify-content:space-between; align-items:center; gap:16px; padding:20px 0; flex-wrap:wrap; }
    .brand { font-size:1.18rem; font-weight:700; letter-spacing:0.03em; }
    .nav-links { display:flex; gap:14px; flex-wrap:wrap; font-size:0.95rem; }
    .hero { display:grid; grid-template-columns:1.05fr 1fr; gap:28px; align-items:center; padding:30px 0 16px; }
    .eyebrow { color:var(--accent-dark); text-transform:uppercase; letter-spacing:0.08em; font-size:0.82rem; margin-bottom:10px; }
    h1 { margin:0 0 16px; font-size:clamp(2.2rem,5vw,3.8rem); line-height:1.03; }
    h2 { margin:0 0 12px; font-size:1.72rem; }
    h3 { margin:0 0 8px; font-size:1.1rem; }
    p { margin:0; }
    .lede { font-size:1.08rem; line-height:1.72; color:var(--muted); margin-bottom:18px; }
    .claim, .panel, .card, .preset, .status-card {
      background:var(--panel);
      border:1px solid var(--border);
      border-radius:18px;
      box-shadow:var(--shadow);
    }
    .claim { padding:16px 18px; line-height:1.7; background:linear-gradient(135deg, rgba(143,95,63,0.12), rgba(143,95,63,0.03)); }
    .hero img, .panel img, .figure-card img {
      width:100%;
      display:block;
      border-radius:18px;
      border:1px solid var(--border);
      box-shadow:var(--shadow);
      background:#fff;
    }
    .stats { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:14px; margin:22px 0 8px; }
    .card { padding:18px; }
    .metric { font-size:1.72rem; font-weight:700; margin-top:6px; }
    .section { margin-top:42px; }
    .demo-grid { display:grid; grid-template-columns:360px 1fr; gap:20px; align-items:start; }
    .panel { padding:18px 20px; }
    .preset-list { display:grid; gap:12px; margin-bottom:16px; }
    .preset { padding:14px 15px; cursor:pointer; transition:transform 120ms ease, border-color 120ms ease; }
    .preset:hover { transform:translateY(-1px); }
    .preset.active { border-color:var(--accent); background:rgba(143,95,63,0.08); }
    .small { color:var(--muted); font-size:0.94rem; line-height:1.6; }
    .slider-group { margin-top:12px; }
    .slider-row { display:flex; justify-content:space-between; gap:12px; margin-bottom:4px; font-size:0.92rem; color:var(--muted); }
    input[type="range"] { width:100%; accent-color:var(--accent); }
    button {
      padding:11px 16px;
      border-radius:999px;
      border:1px solid var(--accent);
      background:var(--accent);
      color:#fff;
      font:inherit;
      font-weight:700;
      cursor:pointer;
    }
    button.alt { background:transparent; color:var(--accent-dark); }
    .button-row { display:flex; gap:12px; flex-wrap:wrap; margin-top:18px; }
    .result-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:12px; margin-top:14px; }
    .status-card { padding:16px; }
    .status-card .label { color:var(--muted); font-size:0.82rem; text-transform:uppercase; letter-spacing:0.08em; }
    .status-card .value { margin-top:8px; font-size:1.5rem; font-weight:700; }
    .status-card .sub { margin-top:6px; color:var(--muted); font-size:0.94rem; line-height:1.5; }
    .pill { display:inline-block; padding:0.26rem 0.62rem; border-radius:999px; font-size:0.8rem; font-weight:700; }
    .high { background:#f8d7d4; color:var(--bad); }
    .moderate { background:#fff1dd; color:var(--warn); }
    .low { background:#e4f4e8; color:var(--good); }
    .list { margin:0; padding-left:18px; line-height:1.75; }
    .split { display:grid; grid-template-columns:1.1fr 0.9fr; gap:18px; margin-top:18px; }
    .figure-card { overflow:hidden; }
    .figure-card .copy { padding:16px 18px 18px; }
    .auth { display:flex; flex-wrap:wrap; gap:10px; margin-top:12px; }
    .auth input { flex:1 1 280px; padding:11px 12px; border-radius:12px; border:1px solid var(--border); font:inherit; }
    .muted { color:var(--muted); }
    .mono { font-family:Consolas,"Courier New",monospace; }
    .jobs { display:grid; gap:10px; margin-top:12px; }
    .job-line { border:1px solid var(--border); border-radius:14px; padding:12px 14px; background:#fff; }
    .empty { border:1px dashed var(--border); border-radius:14px; padding:16px; color:var(--muted); background:rgba(255,255,255,0.7); }
    @media (max-width: 980px) {
      .hero, .demo-grid, .split { grid-template-columns:1fr; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <nav class="nav">
      <div class="brand">StressLab Demo</div>
      <div class="nav-links">
        <a href="/demo">Demo</a>
        <a href="/app">Workspace</a>
        <a href="/docs/index.html">Site</a>
        <a href="/docs/main-finding.html">Main Finding</a>
      </div>
    </nav>

    <section class="hero">
      <div>
        <div class="eyebrow">Thin interactive demo</div>
        <h1>Run a live preset stress test in under three minutes.</h1>
        <p class="lede">
          Pick a domain preset, adjust utilization, coupling, slack, and shock intensity, and StressLab will run a real search-plus-optimize workflow behind the scenes. The UI then turns those artifacts into one answer: collapse risk, failure margin, bottlenecks, and best intervention.
        </p>
        <div id="claim" class="claim"></div>
        <div class="auth">
          <input id="token-input" type="password" placeholder="Optional API token">
          <button id="token-save" class="alt">Save token</button>
          <button id="token-clear" class="alt">Clear</button>
        </div>
      </div>
      <div>
        <img src="/demo-assets/main_result.png" alt="StressLab main result">
      </div>
    </section>

    <section class="stats" id="stats"></section>

    <section class="section demo-grid">
      <div class="panel">
        <h2>Preset selector</h2>
        <p class="small">Choose a domain preset, then tune the operational pressure and stress geometry.</p>
        <div id="preset-list" class="preset-list"></div>

        <h3>Controls</h3>
        <div id="controls"></div>
        <div class="button-row">
          <button id="run-demo">Run stress test</button>
          <button id="open-workspace" class="alt" type="button">Open workspace UI</button>
        </div>
        <p id="run-status" class="small" style="margin-top:12px;"></p>
        <div id="job-lines" class="jobs"></div>
      </div>

      <div class="panel">
        <div style="display:flex;justify-content:space-between;align-items:end;gap:12px;flex-wrap:wrap;">
          <div>
            <h2>Live result</h2>
            <p class="small">Real search and optimize artifacts, translated into a demo-ready readout.</p>
          </div>
          <div id="session-pill"></div>
        </div>
        <div id="result-empty" class="empty" style="margin-top:14px;">Run a preset to see collapse risk, failure margin, bottlenecks, and the top intervention.</div>
        <div id="result-body" style="display:none;">
          <div id="result-grid" class="result-grid"></div>
          <div class="split">
            <div class="figure-card">
              <img id="result-figure" alt="Live preset figure">
              <div class="copy">
                <h3 id="figure-title">Representative figure</h3>
                <p id="figure-caption" class="small"></p>
                <div id="report-links" class="button-row"></div>
              </div>
            </div>
            <div class="panel" style="box-shadow:none;">
              <h3>Interpretation</h3>
              <p id="result-explanation" class="small"></p>
              <h3 style="margin-top:16px;">Top bottlenecks</h3>
              <ul id="bottleneck-list" class="list"></ul>
              <h3 style="margin-top:16px;">Critical edges</h3>
              <ul id="edge-list" class="list"></ul>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section class="section split">
      <div class="figure-card">
        <img src="/demo-assets/collapse_overlay.png" alt="Collapse overlay">
        <div class="copy">
          <h3>Main research context</h3>
          <p class="small">The flagship study found a shared utilization-led collapse band across five topology families.</p>
        </div>
      </div>
      <div class="figure-card">
        <img src="/demo-assets/failure_margin.png" alt="Failure margin">
        <div class="copy">
          <h3>Why coupling still matters</h3>
          <p class="small">The follow-up showed that higher coupling mostly compresses the shock margin to failure rather than relocating the threshold much.</p>
        </div>
      </div>
    </section>
  </div>

  <script>
    const state = { presets: [], selectedPreset: null, controls: {}, sessionId: null, token: "", authRequired: __AUTH_REQUIRED__ };
    const nodes = {};

    document.addEventListener("DOMContentLoaded", async () => {
      ["claim","stats","preset-list","controls","run-demo","run-status","job-lines","result-empty","result-body","result-grid","result-figure","figure-title","figure-caption","report-links","result-explanation","bottleneck-list","edge-list","token-input","token-save","token-clear","session-pill","open-workspace"].forEach((id) => nodes[id] = document.getElementById(id));
      const tokenFromUrl = new URLSearchParams(window.location.search).get("token");
      const tokenFromStorage = window.localStorage.getItem("stresslab_api_token") || "";
      state.token = tokenFromUrl || tokenFromStorage;
      nodes["token-input"].value = state.token;
      nodes["token-save"].addEventListener("click", saveToken);
      nodes["token-clear"].addEventListener("click", clearToken);
      nodes["run-demo"].addEventListener("click", runDemo);
      nodes["open-workspace"].addEventListener("click", () => window.location.href = appendToken("/app"));
      await loadPresets();
    });

    async function loadPresets() {
      try {
        const payload = await getJSON("/demo/presets");
        state.presets = payload.presets || [];
        nodes["claim"].textContent = payload.claim || "";
        const stats = payload.flagship_stats || {};
        nodes["stats"].innerHTML = [
          metricCard("Systems", String(stats.systems || "5,000")),
          metricCard("Families", String(stats.topology_families || "5")),
          metricCard("Transition band", String(stats.shared_transition_band || "0.10-0.19")),
          metricCard("Margin shrink", String(stats.coupling_margin_shrink || "39.2%")),
        ].join("");
        state.selectedPreset = state.presets[0]?.id || null;
        renderPresets();
        renderControls(payload.controls || {});
      } catch (error) {
        nodes["run-status"].textContent = error.message;
      }
    }

    function renderPresets() {
      nodes["preset-list"].innerHTML = state.presets.map((preset) => `
        <div class="preset ${preset.id === state.selectedPreset ? "active" : ""}" data-preset="${escAttr(preset.id)}">
          <strong>${esc(preset.label)}</strong>
          <p class="small" style="margin-top:6px;">${esc(preset.description)}</p>
          <p class="small" style="margin-top:6px;"><em>${esc(preset.story || "")}</em></p>
        </div>
      `).join("");
      nodes["preset-list"].querySelectorAll("[data-preset]").forEach((node) => {
        node.addEventListener("click", () => {
          state.selectedPreset = node.getAttribute("data-preset");
          renderPresets();
        });
      });
    }

    function renderControls(controlSpecs) {
      const specs = Object.entries(controlSpecs);
      state.controls = {};
      nodes["controls"].innerHTML = specs.map(([key, spec]) => {
        state.controls[key] = Number(spec.default);
        return `
          <div class="slider-group">
            <div class="slider-row">
              <span>${esc(spec.label)}</span>
              <strong id="value-${escAttr(key)}">${Number(spec.default).toFixed(2)}x</strong>
            </div>
            <input id="control-${escAttr(key)}" type="range" min="${spec.min}" max="${spec.max}" step="${spec.step}" value="${spec.default}">
          </div>
        `;
      }).join("");
      specs.forEach(([key]) => {
        const node = document.getElementById(`control-${key}`);
        const valueNode = document.getElementById(`value-${key}`);
        node.addEventListener("input", () => {
          state.controls[key] = Number(node.value);
          valueNode.textContent = `${Number(node.value).toFixed(2)}x`;
        });
      });
    }

    async function runDemo() {
      if (!state.selectedPreset) {
        nodes["run-status"].textContent = "Choose a preset first.";
        return;
      }
      try {
        nodes["run-status"].textContent = "Submitting live demo session...";
        const payload = await postJSON("/demo/run", { preset_id: state.selectedPreset, controls: state.controls });
        state.sessionId = payload.session_id;
        renderSession(payload);
        pollSession();
      } catch (error) {
        nodes["run-status"].textContent = error.message;
      }
    }

    async function pollSession() {
      if (!state.sessionId) {
        return;
      }
      try {
        const payload = await getJSON(`/demo/sessions/${encodeURIComponent(state.sessionId)}`);
        renderSession(payload);
        if (payload.status === "running") {
          window.setTimeout(pollSession, 1250);
        }
      } catch (error) {
        nodes["run-status"].textContent = error.message;
      }
    }

    function renderSession(payload) {
      nodes["session-pill"].innerHTML = pill(payload.status === "complete" ? "ready" : payload.status, payload.status === "failed" ? "high" : payload.status === "complete" ? "low" : "moderate");
      const searchJob = payload.jobs?.search;
      const optimizeJob = payload.jobs?.optimize;
      nodes["job-lines"].innerHTML = [jobLine("search", searchJob), jobLine("optimize", optimizeJob)].join("");
      if (payload.status === "running") {
        nodes["run-status"].textContent = "Running search and optimize jobs...";
        return;
      }
      if (payload.status === "failed") {
        nodes["run-status"].textContent = payload.error || "Demo session failed.";
        return;
      }
      nodes["run-status"].textContent = `Completed ${payload.preset_label}.`;
      renderResult(payload.result || {});
    }

    function renderResult(result) {
      nodes["result-empty"].style.display = "none";
      nodes["result-body"].style.display = "block";
      const risk = result.collapse_risk || {};
      const margin = result.failure_margin || {};
      const best = result.best_intervention || {};
      const metrics = result.metrics || {};
      nodes["result-grid"].innerHTML = [
        statusCard("Collapse risk", `${fmt(risk.score, 2)}`, `${risk.label || "unknown"} risk`, riskClass(risk.label)),
        statusCard("Failure margin", `${fmt(margin.best_shock_budget, 3)}`, `${margin.label || "unknown"} margin`, riskClassFromMargin(margin.label)),
        statusCard("Best intervention", esc(best.label || "n/a"), `target ${esc(best.target || "system")}`, "low"),
        statusCard("Resilience", `${fmt(metrics.resilience_score, 3)}`, `utilization ${fmt(metrics.utilization, 3)}`, "moderate"),
      ].join("");
      const figure = result.figure || {};
      const figureSrc = appendToken(`/files/${encodeURIComponent(result.optimize_run_id)}/${encodeURIComponent(figure.relative_path || "queue_lengths.png")}`);
      nodes["result-figure"].src = figureSrc;
      nodes["figure-caption"].textContent = figure.caption || "";
      nodes["result-explanation"].textContent = result.explanation || "";
      nodes["report-links"].innerHTML = `
        <a class="button" href="${appendToken(result.reports?.optimize_report || "#")}" target="_blank" rel="noreferrer">Open optimize report</a>
        <a class="button alt" href="${appendToken(result.reports?.search_report || "#")}" target="_blank" rel="noreferrer">Open search report</a>
      `;
      nodes["bottleneck-list"].innerHTML = (result.bottlenecks || []).map((value) => `<li>${esc(value)}</li>`).join("") || "<li>No bottlenecks identified.</li>";
      nodes["edge-list"].innerHTML = (result.critical_edges || []).map((value) => `<li>${esc(value)}</li>`).join("") || "<li>No critical edges identified.</li>";
    }

    function metricCard(label, value) {
      return `<div class="card"><div class="small" style="text-transform:uppercase;letter-spacing:0.08em;">${esc(label)}</div><div class="metric">${esc(value)}</div></div>`;
    }

    function statusCard(label, value, sub, variant) {
      return `<div class="status-card"><div class="label">${esc(label)}</div><div class="value">${value}</div><div class="sub"><span class="pill ${variant}">${esc(sub)}</span></div></div>`;
    }

    function pill(value, variant) {
      return `<span class="pill ${variant}">${esc(value)}</span>`;
    }

    function jobLine(label, job) {
      if (!job) {
        return `<div class="job-line">${esc(label)} job unavailable.</div>`;
      }
      return `<div class="job-line"><strong>${esc(label)}</strong> <span class="pill ${job.status === "failed" ? "high" : job.status === "succeeded" ? "low" : "moderate"}">${esc(job.status)}</span><div class="small" style="margin-top:6px;">${esc(job.job_id || "")}</div></div>`;
    }

    function riskClass(label) {
      if ((label || "").toLowerCase() === "high") return "high";
      if ((label || "").toLowerCase() === "moderate") return "moderate";
      return "low";
    }

    function riskClassFromMargin(label) {
      if ((label || "").toLowerCase() === "thin") return "high";
      if ((label || "").toLowerCase() === "moderate") return "moderate";
      return "low";
    }

    async function getJSON(path) {
      const response = await fetch(appendToken(path), { headers: authHeaders() });
      if (!response.ok) {
        if (response.status === 401) {
          throw new Error("Unauthorized. Save a valid API token for demo actions.");
        }
        throw new Error(`Request failed: ${response.status}`);
      }
      return response.json();
    }

    async function postJSON(path, payload) {
      const response = await fetch(appendToken(path), {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!response.ok) {
        if (response.status === 401) {
          throw new Error("Unauthorized. Save a valid API token for demo actions.");
        }
        throw new Error(data.error || `Request failed: ${response.status}`);
      }
      return data;
    }

    function authHeaders() {
      return state.token ? { Authorization: `Bearer ${state.token}` } : {};
    }

    function appendToken(path) {
      if (!state.token) {
        return path;
      }
      const join = path.includes("?") ? "&" : "?";
      return `${path}${join}token=${encodeURIComponent(state.token)}`;
    }

    function saveToken() {
      state.token = nodes["token-input"].value.trim();
      if (state.token) {
        window.localStorage.setItem("stresslab_api_token", state.token);
      } else {
        window.localStorage.removeItem("stresslab_api_token");
      }
      nodes["run-status"].textContent = state.token ? "Token saved." : "Token cleared.";
    }

    function clearToken() {
      state.token = "";
      nodes["token-input"].value = "";
      window.localStorage.removeItem("stresslab_api_token");
      nodes["run-status"].textContent = "Token cleared.";
    }

    function fmt(value, digits = 3) {
      const parsed = Number(value);
      return Number.isFinite(parsed) ? parsed.toFixed(digits) : "n/a";
    }

    function esc(value) {
      return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#39;");
    }

    function escAttr(value) {
      return esc(value).replaceAll("`", "");
    }
  </script>
</body>
</html>
"""


def render_demo_app(*, auth_required: bool = False) -> str:
    """Return the Frontend V1 demo page."""

    return DEMO_HTML.replace("__AUTH_REQUIRED__", "true" if auth_required else "false")
