"""Browser-based workspace control center for the StressLab service."""

from __future__ import annotations

APP_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>StressLab Control Center</title>
  <style>
    :root { --ink:#13242b; --muted:#62757d; --line:#d8e1e4; --paper:#fff; --panel:#f5f8f7; --accent:#0b7d69; --good:#19603a; --good-soft:#e4f4e8; --bad:#b63e36; --bad-soft:#fbe5e2; --warn:#9a5d00; --warn-soft:#fff1dd; }
    * { box-sizing:border-box; }
    body { margin:0; font-family:"Segoe UI","Aptos",sans-serif; color:var(--ink); background:linear-gradient(180deg,#f7faf9 0%,#eef3f2 100%); }
    a { color:var(--accent); text-decoration:none; }
    a:hover { text-decoration:underline; }
    header { padding:2rem 1.4rem 1.2rem; background:rgba(255,255,255,0.88); border-bottom:1px solid rgba(19,36,43,0.08); position:sticky; top:0; z-index:5; backdrop-filter:blur(8px); }
    h1,h2,h3 { margin:0; letter-spacing:-0.02em; }
    p { margin:0.35rem 0 0; color:var(--muted); }
    nav { display:flex; flex-wrap:wrap; gap:0.55rem; margin-top:0.9rem; }
    nav a { padding:0.42rem 0.75rem; border:1px solid var(--line); border-radius:999px; background:var(--paper); font-size:0.92rem; }
    main { max-width:1360px; margin:0 auto; padding:1.25rem; }
    section { margin-top:1rem; background:rgba(255,255,255,0.9); border:1px solid rgba(19,36,43,0.08); border-radius:18px; overflow:hidden; box-shadow:0 12px 28px rgba(19,36,43,0.07); }
    .head { display:flex; justify-content:space-between; align-items:end; gap:1rem; padding:1rem 1.15rem 0.8rem; border-bottom:1px solid rgba(19,36,43,0.08); }
    .body { padding:1rem 1.15rem 1.2rem; }
    .grid { display:grid; gap:0.85rem; }
    .cards { grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); }
    .split { grid-template-columns:1.1fr 0.9fr; }
    .triple { grid-template-columns:repeat(3,1fr); }
    .card, .panel { background:var(--paper); border:1px solid var(--line); border-radius:15px; padding:0.95rem; }
    .metric strong { display:block; font-size:0.78rem; text-transform:uppercase; letter-spacing:0.08em; color:var(--muted); }
    .metric span { display:block; margin-top:0.45rem; font-size:1.42rem; font-weight:700; }
    .toolbar { display:flex; flex-wrap:wrap; gap:0.75rem; margin-bottom:0.9rem; }
    .toolbar > div { flex:1 1 200px; }
    label { display:block; font-size:0.82rem; font-weight:600; color:var(--muted); margin-bottom:0.3rem; }
    input, select, button, textarea { width:100%; padding:0.7rem 0.8rem; border:1px solid var(--line); border-radius:12px; font:inherit; background:var(--paper); color:var(--ink); }
    button { cursor:pointer; background:var(--accent); color:#fff; border-color:var(--accent); font-weight:700; }
    button.alt { background:var(--paper); color:var(--ink); }
    table { width:100%; border-collapse:collapse; font-size:0.93rem; }
    th, td { padding:0.66rem 0.58rem; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }
    th { font-size:0.76rem; text-transform:uppercase; letter-spacing:0.08em; color:var(--muted); background:var(--panel); }
    .pill { display:inline-block; padding:0.24rem 0.55rem; border-radius:999px; font-size:0.78rem; font-weight:700; }
    .good { background:var(--good-soft); color:var(--good); }
    .bad { background:var(--bad-soft); color:var(--bad); }
    .warn { background:var(--warn-soft); color:var(--warn); }
    .neutral { background:var(--panel); color:var(--muted); }
    .mono { font-family:Consolas,"Courier New",monospace; }
    .empty { padding:1rem; border:1px dashed var(--line); border-radius:14px; color:var(--muted); background:rgba(255,255,255,0.6); }
    .links { display:flex; flex-wrap:wrap; gap:0.6rem; margin-top:0.75rem; }
    .thumb { width:100%; max-height:220px; object-fit:contain; border:1px solid var(--line); border-radius:12px; background:#fff; margin-top:0.7rem; }
    .code, .files { min-height:220px; border-radius:14px; padding:0.95rem; overflow:auto; white-space:pre-wrap; }
    .code { background:#16242a; color:#e8f4ef; font:0.84rem Consolas,"Courier New",monospace; }
    .files { background:#f7fafb; border:1px solid var(--line); }
    @media (max-width: 980px) { .split, .triple { grid-template-columns:1fr; } }
  </style>
</head>
<body>
  <header>
    <h1>StressLab Control Center</h1>
    <p>Interactive workspace view for live resilience operations, async jobs, artifact inspection, and side-by-side plan review.</p>
    <nav>
      <a href="#overview">Overview</a>
      <a href="#discovery">Discovery</a>
      <a href="#artifacts">Artifacts</a>
      <a href="#jobs">Jobs</a>
      <a href="#compare">Compare</a>
      <a href="/">API Home</a>
    </nav>
    <div id="auth-banner" class="links"></div>
  </header>
  <main>
    <section id="overview">
      <div class="head">
        <div><h2>Workspace Pulse</h2><p>Recent activity, decision signals, and current watch items.</p></div>
        <div><button id="refresh-all" class="alt">Refresh workspace</button></div>
      </div>
      <div class="body grid">
        <div id="overview-cards" class="grid cards"></div>
        <div class="grid split">
          <div class="panel"><h3>Actionable Plans</h3><div id="plan-list" style="margin-top:0.75rem;"></div></div>
          <div class="panel"><h3>Failure Watchlist</h3><div id="watch-list" style="margin-top:0.75rem;"></div></div>
        </div>
      </div>
    </section>

    <section id="discovery">
      <div class="head">
        <div><h2>Discovery Lab</h2><p>Synthetic study tracking, discovered fragility laws, and research figures from the workspace.</p></div>
      </div>
      <div class="body grid">
        <div id="discovery-cards" class="grid cards"></div>
        <div class="grid split">
          <div class="panel"><h3>Top Symbolic Laws</h3><div id="discovery-symbolic" style="margin-top:0.75rem;"></div></div>
          <div class="panel"><h3>Top Candidate Laws</h3><div id="discovery-candidates" style="margin-top:0.75rem;"></div></div>
        </div>
        <div class="grid split">
          <div class="panel"><h3>Latest Discovery Artifacts</h3><div id="discovery-latest" style="margin-top:0.75rem;"></div></div>
          <div class="panel"><h3>Research Figures</h3><div id="discovery-figures" style="margin-top:0.75rem;"></div></div>
        </div>
      </div>
    </section>

    <section id="artifacts">
      <div class="head">
        <div><h2>Artifact Explorer</h2><p>Filter the registry, inspect a run, and jump into its generated report.</p></div>
      </div>
      <div class="body grid">
        <div class="toolbar">
          <div><label for="registry-filter">Search</label><input id="registry-filter" type="text" placeholder="run id, system, analysis type"></div>
          <div><label for="analysis-filter">Analysis type</label><select id="analysis-filter"></select></div>
          <div><label for="artifact-select">Inspect run</label><select id="artifact-select"></select></div>
        </div>
        <div id="registry-table"></div>
        <div class="grid split">
          <div class="panel"><h3>Artifact Summary</h3><div id="artifact-summary" style="margin-top:0.75rem;"></div><div id="artifact-links" class="links"></div></div>
          <div class="panel"><h3>Available Files</h3><div id="artifact-files" class="files" style="margin-top:0.75rem;"></div></div>
        </div>
        <div class="panel"><h3>Expanded JSON Details</h3><div id="artifact-details" class="code" style="margin-top:0.75rem;"></div></div>
      </div>
    </section>

    <section id="jobs">
      <div class="head">
        <div><h2>Async Job Desk</h2><p>Submit long-running workflows and track them to completion.</p></div>
      </div>
      <div class="body grid">
        <div class="grid split">
          <div class="panel">
            <h3>Submit a Job</h3>
            <form id="job-form" class="grid" style="margin-top:0.75rem;">
              <div class="grid triple">
                <div><label for="job-command">Command</label><select id="job-command"><option value="run">run</option><option value="optimize">optimize</option><option value="generate">generate</option><option value="discover">discover</option><option value="theory">theory</option><option value="research">research</option><option value="evaluate">evaluate</option><option value="casebook">casebook</option><option value="benchmark">benchmark</option></select></div>
                <div><label for="job-spec-path">Spec path</label><input id="job-spec-path" type="text" value="examples/healthcare/ed_basic.yml"></div>
                <div><label for="job-suite">Suite</label><input id="job-suite" type="text" value="starter"></div>
              </div>
              <div class="grid triple">
                <div><label for="job-source-dir">Source dir</label><input id="job-source-dir" type="text" placeholder="generated specs directory"></div>
                <div><label for="job-dataset-source">Dataset source</label><input id="job-dataset-source" type="text" placeholder="discovery run dir or collapse_dataset.csv"></div>
                <div><label for="job-theory-dir">Theory dir</label><input id="job-theory-dir" type="text" placeholder="existing theory analysis directory"></div>
              </div>
              <div class="grid triple">
                <div><label for="job-topology-type">Topology type</label><input id="job-topology-type" type="text" value="mixed"></div>
                <div><label for="job-count">Count</label><input id="job-count" type="number" step="1" placeholder="24"></div>
                <div><label for="job-workers">Workers</label><input id="job-workers" type="number" step="1" placeholder="2"></div>
              </div>
              <div class="grid triple">
                <div><label for="job-min-nodes">Min nodes</label><input id="job-min-nodes" type="number" step="1" placeholder="6"></div>
                <div><label for="job-max-nodes">Max nodes</label><input id="job-max-nodes" type="number" step="1" placeholder="16"></div>
                <div><label for="job-batch-size">Batch size</label><input id="job-batch-size" type="number" step="1" placeholder="100"></div>
              </div>
              <div class="grid triple">
                <div><label for="job-shard-count">Shard count</label><input id="job-shard-count" type="number" step="1" placeholder="1"></div>
                <div><label for="job-shard-index">Shard index</label><input id="job-shard-index" type="number" step="1" placeholder="0"></div>
                <div></div>
              </div>
              <div class="grid triple">
                <div><label for="job-budget">Budget</label><input id="job-budget" type="number" step="0.01" placeholder="2500"></div>
                <div><label for="job-scenario-budget">Scenario budget</label><input id="job-scenario-budget" type="number" step="0.01" placeholder="0.4"></div>
                <div><label for="job-scenario-samples">Scenario samples</label><input id="job-scenario-samples" type="number" step="1" placeholder="3"></div>
              </div>
              <div class="grid triple">
                <div><label for="job-replicates">Replicates</label><input id="job-replicates" type="number" step="1" placeholder="4"></div>
                <div><label for="job-fairness-weight">Fairness weight</label><input id="job-fairness-weight" type="number" step="0.01" placeholder="0.25"></div>
                <div><label for="job-worst-case-budget">Worst-case budget</label><input id="job-worst-case-budget" type="number" step="0.01" placeholder="0.6"></div>
              </div>
              <div class="grid triple">
                <div><label for="job-resume-run-dir">Resume run dir</label><input id="job-resume-run-dir" type="text" placeholder="existing discovery run directory"></div>
                <div><label for="job-options">Extra options JSON</label><input id="job-options" type="text" placeholder='{"expand_policies": true}'></div>
                <div></div>
              </div>
              <div class="grid triple">
                <div><label><input id="job-robust" type="checkbox"> Robust mode</label></div>
                <div><label><input id="job-refresh-registry" type="checkbox" checked> Auto-refresh workspace</label></div>
                <div><button type="submit">Submit job</button></div>
              </div>
            </form>
            <div id="job-submit-status" style="margin-top:0.8rem;color:var(--muted);"></div>
          </div>
          <div class="panel"><h3>Queue Snapshot</h3><div id="job-cards" class="grid cards" style="margin-top:0.75rem;"></div></div>
        </div>
        <div id="jobs-table"></div>
      </div>
    </section>

    <section id="compare">
      <div class="head">
        <div><h2>Decision Compare</h2><p>Read two artifacts side by side from the registry without leaving the browser.</p></div>
      </div>
      <div class="body grid">
        <div class="toolbar">
          <div><label for="compare-left">Left run</label><select id="compare-left"></select></div>
          <div><label for="compare-right">Right run</label><select id="compare-right"></select></div>
        </div>
        <div id="compare-panel" class="grid split"></div>
      </div>
    </section>
  </main>
  <script>
    const state = { registry: [], filtered: [], jobs: [], status: null, board: null, discovery: null, artifact: null, selectedRunId: null, apiToken: "", authRequired: __AUTH_REQUIRED__ };
    const nodes = {};

    document.addEventListener("DOMContentLoaded", () => {
      ["overview-cards","plan-list","watch-list","discovery-cards","discovery-symbolic","discovery-candidates","discovery-latest","discovery-figures","registry-filter","analysis-filter","artifact-select","registry-table","artifact-summary","artifact-links","artifact-files","artifact-details","job-form","job-command","job-spec-path","job-suite","job-source-dir","job-dataset-source","job-theory-dir","job-topology-type","job-count","job-workers","job-min-nodes","job-max-nodes","job-batch-size","job-shard-count","job-shard-index","job-budget","job-scenario-budget","job-scenario-samples","job-replicates","job-fairness-weight","job-worst-case-budget","job-resume-run-dir","job-options","job-robust","job-refresh-registry","job-submit-status","job-cards","jobs-table","compare-left","compare-right","compare-panel","refresh-all","auth-banner"].forEach((id) => nodes[id] = document.getElementById(id));
      const tokenFromUrl = new URLSearchParams(window.location.search).get("token");
      const tokenFromStorage = window.localStorage.getItem("stresslab_api_token") || "";
      state.apiToken = tokenFromUrl || tokenFromStorage;
      if (tokenFromUrl) {
        window.localStorage.setItem("stresslab_api_token", tokenFromUrl);
      }
      renderAuthBanner();
      nodes["refresh-all"].addEventListener("click", () => refreshAll(true));
      nodes["registry-filter"].addEventListener("input", renderRegistry);
      nodes["analysis-filter"].addEventListener("change", renderRegistry);
      nodes["artifact-select"].addEventListener("change", async (event) => { state.selectedRunId = event.target.value || null; await loadArtifact(); });
      nodes["compare-left"].addEventListener("change", renderCompare);
      nodes["compare-right"].addEventListener("change", renderCompare);
      nodes["job-command"].addEventListener("change", syncJobForm);
      nodes["job-form"].addEventListener("submit", submitJob);
      refreshAll();
      window.setInterval(refreshJobs, 2500);
    });

    async function refreshAll(forceRefresh = false) {
      try {
        await Promise.all([loadStatus(forceRefresh), loadBoard(forceRefresh), loadDiscovery(forceRefresh), loadRegistry(forceRefresh), refreshJobs()]);
      } catch (error) {
        nodes["job-submit-status"].textContent = error.message;
        if (!state.registry.length) {
          nodes["registry-table"].innerHTML = empty("Enter a valid API token to load registry data.");
          nodes["artifact-summary"].innerHTML = empty("Artifact data is locked until the API token is provided.");
          nodes["artifact-files"].innerHTML = "";
          nodes["artifact-details"].textContent = "";
        }
      }
      syncJobForm();
    }

    async function loadStatus(forceRefresh = false) {
      state.status = await getJSON(`/status?limit=12${forceRefresh ? "&refresh=1" : ""}`);
      const cards = [
        ["Tracked artifacts", fmtInt(state.status.entry_count)],
        ["Recent entries", fmtInt(state.status.recent_count)],
        ["Failure rate", fmt(state.status.failure_rate)],
        ["Mean resilience", fmt(state.status.mean_resilience_score)],
        ["Mean fairness", fmt(state.status.mean_fairness_score)],
        ["Mean runtime", fmt(state.status.mean_execution_duration, 2)],
      ];
      nodes["overview-cards"].innerHTML = cards.map(([label, value]) => `<div class="card metric"><strong>${esc(label)}</strong><span>${esc(value)}</span></div>`).join("");
    }

    async function loadBoard(forceRefresh = false) {
      state.board = await getJSON(`/board?recent_limit=8&watch_limit=6&plan_limit=6${forceRefresh ? "&refresh=1" : ""}`);
      nodes["plan-list"].innerHTML = renderPanelList(state.board.plans || [], "No optimize or evaluation plans found.", (entry) =>
        `<strong>${esc(entry.system_name || entry.run_id || "unknown")}</strong><div style="color:var(--muted);margin-top:0.25rem;">${esc(entry.analysis_type || "unknown")} | resilience ${esc(fmt(entry.resilience_score))} | fairness ${esc(fmt(entry.fairness_score))}</div><div class="links">${reportLink(entry.run_id, "Report")} ${artifactLink(entry.run_id, "Inspect")}</div>`
      );
      nodes["watch-list"].innerHTML = renderPanelList(state.board.failure_watchlist || [], "No watchlist entries right now.", (entry) =>
        `<strong>${esc(entry.system_name || entry.run_id || "unknown")}</strong><div style="color:var(--muted);margin-top:0.25rem;">${esc(entry.analysis_type || "unknown")} | failure ${esc(boolText(entry.failure_triggered))} | wait ${esc(fmt(entry.mean_wait))}</div><div class="links">${reportLink(entry.run_id, "Report")} ${artifactLink(entry.run_id, "Inspect")}</div>`
      );
    }

    async function loadDiscovery(forceRefresh = false) {
      state.discovery = await getJSON(`/discovery?limit=12${forceRefresh ? "&refresh=1" : ""}`);
      const counts = state.discovery.analysis_type_counts || {};
      const cards = [
        ["Tracked studies", fmtInt(state.discovery.entry_count || 0)],
        ["Generate runs", fmtInt(counts.generate || 0)],
        ["Discover runs", fmtInt(counts.discover || 0)],
        ["Theory runs", fmtInt(counts.theory || 0)],
        ["Research runs", fmtInt(counts.research || 0)],
        ["Symbolic laws", fmtInt((state.discovery.top_symbolic_laws || []).length)],
      ];
      nodes["discovery-cards"].innerHTML = cards.map(([label, value]) => `<div class="card metric"><strong>${esc(label)}</strong><span>${esc(value)}</span></div>`).join("");
      nodes["discovery-symbolic"].innerHTML = renderTable(
        ["formula", "r2", "model_type"],
        (state.discovery.top_symbolic_laws || []).slice(0, 8).map((row) => ({
          formula: `<span class="mono">${esc(row.formula || row.expression || "n/a")}</span>`,
          r2: esc(fmt(row.r2)),
          model_type: esc(row.model_type || "symbolic"),
        }))
      );
      nodes["discovery-candidates"].innerHTML = renderTable(
        ["formula", "r2", "model_type"],
        (state.discovery.top_candidate_laws || []).slice(0, 8).map((row) => ({
          formula: `<span class="mono">${esc(row.formula || "n/a")}</span>`,
          r2: esc(fmt(row.r2)),
          model_type: esc(row.model_type || "candidate"),
        }))
      );
      nodes["discovery-latest"].innerHTML = renderPanelList(
        state.discovery.latest_entries || [],
        "No discovery artifacts found yet.",
        (entry) => `<strong>${esc(entry.analysis_type || "unknown")}</strong><div style="color:var(--muted);margin-top:0.25rem;">${esc(entry.run_id || "unknown")} | ${esc(entry.system_name || "unknown")}</div><div class="links">${reportLink(entry.run_id, "Report")} ${artifactLink(entry.run_id, "Artifact")}</div>`
      );
      const researchRunId = lastSegment(state.discovery.latest_research_run_dir || "");
      nodes["discovery-figures"].innerHTML = renderPanelList(
        state.discovery.research_figures || [],
        "No research figures available yet.",
        (figure) => {
          const href = researchRunId ? `/files/${encodeURIComponent(researchRunId)}/figures/${encodeURIComponent(figure.figure || "")}${authQuery()}` : "#";
          return `<strong>${esc(figure.figure || "figure")}</strong><div style="color:var(--muted);margin-top:0.25rem;">${esc(figure.path || "")}</div><div class="links"><a href="${href}" target="_blank" rel="noreferrer">Open figure</a></div><img class="thumb" src="${href}" alt="${attr(figure.figure || "figure")}">`;
        }
      );
    }

    async function loadRegistry(forceRefresh = false) {
      const payload = await getJSON(`/registry?limit=120${forceRefresh ? "&refresh=1" : ""}`);
      state.registry = Array.isArray(payload.entries) ? payload.entries : [];
      if (!state.selectedRunId && state.registry.length) {
        state.selectedRunId = state.registry[0].run_id;
      }
      populateCompareSelectors();
      renderRegistry();
      await loadArtifact();
    }

    async function refreshJobs() {
      try {
        const payload = await getJSON("/jobs?limit=20");
        state.jobs = Array.isArray(payload.jobs) ? payload.jobs : [];
        const counts = payload.status_counts || {};
        const cards = [["Queued", counts.queued || 0], ["Running", counts.running || 0], ["Succeeded", counts.succeeded || 0], ["Failed", counts.failed || 0]];
        nodes["job-cards"].innerHTML = cards.map(([label, value]) => `<div class="card metric"><strong>${esc(label)}</strong><span>${esc(String(value))}</span></div>`).join("");
        nodes["jobs-table"].innerHTML = renderTable(
          ["job_id", "status", "command", "run_dir", "created_at", "updated_at", "note"],
          state.jobs.map((job) => ({
            job_id: `<span class="mono">${esc(job.job_id)}</span>`,
            status: pill(job.status, job.status === "failed" ? "bad" : (job.status === "succeeded" ? "good" : "warn")),
            command: esc(job.command),
            run_dir: job.run_dir ? `<a href="/reports/${encodeURIComponent(lastSegment(job.run_dir))}${authQuery()}" target="_blank" rel="noreferrer">report</a>` : "<span style='color:var(--muted);'>pending</span>",
            created_at: esc(fmtTime(job.created_at)),
            updated_at: esc(fmtTime(job.updated_at)),
            note: esc(job.error || job.report_path || ""),
          }))
        );
      } catch (error) {
        nodes["job-cards"].innerHTML = empty("Job queue is unavailable until the API token is set.");
        nodes["jobs-table"].innerHTML = empty(error.message);
      }
    }

    async function loadArtifact() {
      if (!state.selectedRunId) {
        renderArtifact(null);
        return;
      }
      state.artifact = await getJSON(`/artifacts/${encodeURIComponent(state.selectedRunId)}?expand=1`);
      renderArtifact(state.artifact);
    }

    function renderRegistry() {
      const filterText = (nodes["registry-filter"].value || "").trim().toLowerCase();
      const currentType = nodes["analysis-filter"].value || "all";
      const types = Array.from(new Set(state.registry.map((entry) => entry.analysis_type || "unknown"))).sort();
      nodes["analysis-filter"].innerHTML = ["all", ...types].map((value) => `<option value="${attr(value)}" ${value === currentType ? "selected" : ""}>${esc(value)}</option>`).join("");
      state.filtered = state.registry.filter((entry) => {
        const haystack = [entry.run_id, entry.analysis_type, entry.system_name].join(" ").toLowerCase();
        return (!filterText || haystack.includes(filterText)) && (currentType === "all" || (entry.analysis_type || "unknown") === currentType);
      });
      if (state.filtered.length && !state.filtered.some((entry) => entry.run_id === state.selectedRunId)) {
        state.selectedRunId = state.filtered[0].run_id;
      }
      nodes["artifact-select"].innerHTML = state.filtered.map((entry) => `<option value="${attr(entry.run_id)}" ${entry.run_id === state.selectedRunId ? "selected" : ""}>${esc(entry.run_id)} | ${esc(entry.analysis_type || "unknown")} | ${esc(entry.system_name || "unknown")}</option>`).join("");
      nodes["registry-table"].innerHTML = renderTable(
        ["run_id", "analysis_type", "system_name", "resilience_score", "fairness_score", "failure_triggered", "timestamp"],
        state.filtered.slice(0, 25).map((entry) => ({
          run_id: `<a href="#artifacts" data-run-id="${attr(entry.run_id)}">${esc(entry.run_id)}</a>`,
          analysis_type: esc(entry.analysis_type || "unknown"),
          system_name: esc(entry.system_name || "unknown"),
          resilience_score: esc(fmt(entry.resilience_score)),
          fairness_score: esc(fmt(entry.fairness_score)),
          failure_triggered: pill(boolText(entry.failure_triggered), entry.failure_triggered ? "bad" : "good"),
          timestamp: esc(fmtTime(entry.timestamp)),
        }))
      );
      nodes["registry-table"].querySelectorAll("[data-run-id]").forEach((node) => node.addEventListener("click", async (event) => {
        event.preventDefault();
        state.selectedRunId = node.getAttribute("data-run-id");
        nodes["artifact-select"].value = state.selectedRunId;
        await loadArtifact();
        window.location.hash = "#artifacts";
      }));
    }

    function renderArtifact(artifact) {
      if (!artifact) {
        nodes["artifact-summary"].innerHTML = empty("Choose an artifact to inspect.");
        nodes["artifact-links"].innerHTML = "";
        nodes["artifact-files"].innerHTML = "";
        nodes["artifact-details"].textContent = "";
        return;
      }
      const summary = artifact.summary || {};
      const rows = [
        ["Run ID", artifact.run_id],
        ["Analysis type", summary.analysis_type || "unknown"],
        ["System", summary.system_name || "unknown"],
        ["Resilience", fmt(summary.resilience_score)],
        ["Fairness", fmt(summary.fairness_score)],
        ["Failure", boolText(summary.failure_triggered)],
        ["Timestamp", fmtTime(summary.timestamp)],
      ];
      nodes["artifact-summary"].innerHTML = rows.map(([label, value]) => `<div style="padding:0.36rem 0;border-bottom:1px solid var(--line);"><strong>${esc(label)}:</strong> ${esc(String(value))}</div>`).join("");
      const authSuffix = state.apiToken ? `&token=${encodeURIComponent(state.apiToken)}` : "";
      nodes["artifact-links"].innerHTML = `${reportLink(artifact.run_id, "Open report")} <a href="/artifacts/${encodeURIComponent(artifact.run_id)}?expand=1${authSuffix}" target="_blank" rel="noreferrer">Open JSON</a> <a href="/bundles/${encodeURIComponent(artifact.run_id)}?include_registry=1${authSuffix}" target="_blank" rel="noreferrer">Download bundle</a>`;
      nodes["artifact-files"].innerHTML = artifact.available_files && artifact.available_files.length ? artifact.available_files.map((value) => `<div>${esc(value)}</div>`).join("") : empty("No files found.");
      nodes["artifact-details"].textContent = JSON.stringify(artifact.details || {}, null, 2);
    }

    function populateCompareSelectors() {
      const options = state.registry.slice(0, 60).map((entry) => `<option value="${attr(entry.run_id)}">${esc(entry.run_id)} | ${esc(entry.system_name || "unknown")}</option>`).join("");
      nodes["compare-left"].innerHTML = `<option value="">Select a run</option>${options}`;
      nodes["compare-right"].innerHTML = `<option value="">Select a run</option>${options}`;
      if (state.registry.length >= 2) {
        if (!nodes["compare-left"].value) {
          nodes["compare-left"].value = state.registry[0].run_id;
        }
        if (!nodes["compare-right"].value) {
          nodes["compare-right"].value = state.registry[1].run_id;
        }
      }
      renderCompare();
    }

    function renderCompare() {
      const left = state.registry.find((entry) => entry.run_id === nodes["compare-left"].value);
      const right = state.registry.find((entry) => entry.run_id === nodes["compare-right"].value);
      if (!left || !right) {
        nodes["compare-panel"].innerHTML = empty("Choose two runs to compare.");
        return;
      }
      nodes["compare-panel"].innerHTML = [left, right].map((entry, index) => {
        const other = index === 0 ? right : left;
        const deltas = [
          ["Resilience", entry.resilience_score, other.resilience_score],
          ["Fairness", entry.fairness_score, other.fairness_score],
          ["Mean wait", entry.mean_wait, other.mean_wait],
          ["Throughput", entry.throughput, other.throughput],
        ];
        return `<div class="panel">
          <h3>${esc(index === 0 ? "Left" : "Right")} | ${esc(entry.system_name || entry.run_id)}</h3>
          <div style="color:var(--muted);margin-top:0.25rem;">${esc(entry.analysis_type || "unknown")} | ${esc(entry.run_id)}</div>
          <div class="links">${reportLink(entry.run_id, "Report")} ${artifactLink(entry.run_id, "Artifact")}</div>
          <div style="margin-top:0.8rem;">
            ${deltas.map(([label, current, baseline]) => {
              const delta = num(current) - num(baseline);
              const signed = Number.isFinite(delta) ? `${delta >= 0 ? "+" : ""}${delta.toFixed(3)}` : "n/a";
              return `<div style="padding:0.42rem 0;border-bottom:1px solid var(--line);"><strong>${esc(label)}:</strong> ${esc(fmt(current))} <span style="color:var(--muted);">| delta ${esc(signed)}</span></div>`;
            }).join("")}
          </div>
        </div>`;
      }).join("");
    }

    function renderAuthBanner() {
      const summary = state.authRequired
        ? (state.apiToken ? "Authenticated browser session" : "API token required for data access")
        : "Open workspace session";
      nodes["auth-banner"].innerHTML = `
        <span class="pill ${attr(state.authRequired ? (state.apiToken ? "good" : "warn") : "neutral")}">${esc(summary)}</span>
        <input id="auth-token-input" type="password" placeholder="Paste StressLab API token" value="${attr(state.apiToken)}" style="max-width:320px;">
        <button id="auth-save" class="alt" style="width:auto;">Save token</button>
        <button id="auth-clear" class="alt" style="width:auto;">Clear</button>
      `;
      document.getElementById("auth-save").addEventListener("click", () => {
        const token = document.getElementById("auth-token-input").value.trim();
        state.apiToken = token;
        if (token) {
          window.localStorage.setItem("stresslab_api_token", token);
        } else {
          window.localStorage.removeItem("stresslab_api_token");
        }
        renderAuthBanner();
        refreshAll();
      });
      document.getElementById("auth-clear").addEventListener("click", () => {
        state.apiToken = "";
        window.localStorage.removeItem("stresslab_api_token");
        renderAuthBanner();
      });
    }

    async function submitJob(event) {
      event.preventDefault();
      try {
        const payload = buildJobPayload();
        nodes["job-submit-status"].textContent = "Submitting job...";
        const created = await postJSON("/jobs", payload);
        nodes["job-submit-status"].innerHTML = `Submitted <span class="mono">${esc(created.job_id)}</span> as ${esc(created.command)}.`;
        await refreshJobs();
        if (nodes["job-refresh-registry"].checked) {
          window.setTimeout(() => refreshAll(true), 900);
        }
      } catch (error) {
        nodes["job-submit-status"].textContent = `Submission failed: ${error.message}`;
      }
    }

    function buildJobPayload() {
      const command = nodes["job-command"].value;
      const payload = { command };
      if (["run", "optimize", "evaluate"].includes(command)) {
        payload.spec_path = nodes["job-spec-path"].value.trim();
      }
      if (command === "discover" && nodes["job-source-dir"].value.trim()) {
        payload.source_dir = nodes["job-source-dir"].value.trim();
      }
      if (["theory", "research"].includes(command)) {
        payload.dataset_source = nodes["job-dataset-source"].value.trim();
      }
      if (command === "research" && nodes["job-theory-dir"].value.trim()) {
        payload.theory_dir = nodes["job-theory-dir"].value.trim();
      }
      if (["casebook", "benchmark"].includes(command) && nodes["job-suite"].value.trim()) {
        payload.suite = nodes["job-suite"].value.trim();
      }
      if (["generate", "discover"].includes(command) && nodes["job-topology-type"].value.trim()) {
        payload.topology_type = nodes["job-topology-type"].value.trim();
      }
      [["count", "job-count"], ["workers", "job-workers"], ["min_nodes", "job-min-nodes"], ["max_nodes", "job-max-nodes"], ["batch_size", "job-batch-size"], ["shard_count", "job-shard-count"], ["shard_index", "job-shard-index"], ["budget", "job-budget"], ["scenario_budget", "job-scenario-budget"], ["scenario_samples", "job-scenario-samples"], ["replicates", "job-replicates"], ["fairness_weight", "job-fairness-weight"], ["worst_case_budget", "job-worst-case-budget"]].forEach(([key, nodeId]) => {
        const raw = nodes[nodeId].value;
        if (raw !== "") {
          payload[key] = raw.includes(".") ? Number.parseFloat(raw) : Number.parseInt(raw, 10);
        }
      });
      if (command === "discover" && nodes["job-resume-run-dir"].value.trim()) {
        payload.resume_run_dir = nodes["job-resume-run-dir"].value.trim();
      }
      if (nodes["job-robust"].checked) {
        payload.robust = true;
      }
      const extra = nodes["job-options"].value.trim();
      if (extra) {
        payload.options = JSON.parse(extra);
      }
      return payload;
    }

    function syncJobForm() {
      const command = nodes["job-command"].value;
      const usesSpec = ["run", "optimize", "evaluate"].includes(command);
      const usesSourceDir = command === "discover";
      const usesDataset = ["theory", "research"].includes(command);
      const usesTheoryDir = command === "research";
      const usesTopology = ["generate", "discover"].includes(command);
      const usesCount = ["generate", "discover"].includes(command);
      const usesWorkers = command === "discover";
      const usesSuite = ["casebook", "benchmark"].includes(command);
      nodes["job-spec-path"].disabled = !usesSpec;
      nodes["job-source-dir"].disabled = !usesSourceDir;
      nodes["job-dataset-source"].disabled = !usesDataset;
      nodes["job-theory-dir"].disabled = !usesTheoryDir;
      nodes["job-topology-type"].disabled = !usesTopology;
      nodes["job-count"].disabled = !usesCount;
      nodes["job-workers"].disabled = !usesWorkers;
      nodes["job-min-nodes"].disabled = !usesCount;
      nodes["job-max-nodes"].disabled = !usesCount;
      nodes["job-batch-size"].disabled = !usesCount;
      nodes["job-shard-count"].disabled = !usesCount;
      nodes["job-shard-index"].disabled = !usesCount;
      nodes["job-suite"].disabled = !usesSuite;
      nodes["job-budget"].disabled = !["optimize", "evaluate"].includes(command);
      nodes["job-scenario-budget"].disabled = !["optimize", "evaluate"].includes(command);
      nodes["job-scenario-samples"].disabled = !["optimize", "evaluate"].includes(command);
      nodes["job-replicates"].disabled = !["evaluate", "casebook"].includes(command);
      nodes["job-fairness-weight"].disabled = !["optimize", "evaluate", "casebook"].includes(command);
      nodes["job-worst-case-budget"].disabled = command !== "discover";
      nodes["job-resume-run-dir"].disabled = command !== "discover";
      nodes["job-robust"].disabled = !["optimize", "evaluate", "casebook"].includes(command);
    }

    function renderPanelList(entries, fallback, formatter) {
      return entries.length ? entries.map((entry) => `<div class="card" style="margin-bottom:0.65rem;">${formatter(entry)}</div>`).join("") : empty(fallback);
    }

    function renderTable(columns, rows) {
      if (!rows.length) {
        return empty("No records available.");
      }
      const head = columns.map((column) => `<th>${esc(column.replaceAll("_", " "))}</th>`).join("");
      const body = rows.map((row) => `<tr>${columns.map((column) => `<td>${row[column] ?? ""}</td>`).join("")}</tr>`).join("");
      return `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
    }

    function reportLink(runId, label) {
      return `<a href="/reports/${encodeURIComponent(runId)}${authQuery()}" target="_blank" rel="noreferrer">${esc(label)}</a>`;
    }

    function artifactLink(runId, label) {
      const authSuffix = state.apiToken ? `&token=${encodeURIComponent(state.apiToken)}` : "";
      return `<a href="/artifacts/${encodeURIComponent(runId)}?expand=1${authSuffix}" target="_blank" rel="noreferrer">${esc(label)}</a>`;
    }

    function pill(value, variant) {
      return `<span class="pill ${attr(variant || "neutral")}">${esc(String(value))}</span>`;
    }

    function empty(message) {
      return `<div class="empty">${esc(message)}</div>`;
    }

    async function getJSON(path) {
      const response = await fetch(withAuthPath(path), { headers: authHeaders() });
      if (!response.ok) {
        if (response.status === 401) {
          throw new Error("Unauthorized. Save a valid API token in the header bar.");
        }
        throw new Error(`Request failed: ${response.status}`);
      }
      return response.json();
    }

    async function postJSON(path, payload) {
      const response = await fetch(withAuthPath(path), { method: "POST", headers: authHeaders({ "Content-Type": "application/json" }), body: JSON.stringify(payload) });
      const data = await response.json();
      if (!response.ok) {
        if (response.status === 401) {
          throw new Error("Unauthorized. Save a valid API token in the header bar.");
        }
        throw new Error(data.error || `Request failed: ${response.status}`);
      }
      return data;
    }

    function authHeaders(base = {}) {
      if (!state.apiToken) {
        return base;
      }
      return { ...base, Authorization: `Bearer ${state.apiToken}` };
    }

    function authQuery() {
      return state.apiToken ? `?token=${encodeURIComponent(state.apiToken)}` : "";
    }

    function fmt(value, digits = 3) {
      const parsed = Number(value);
      return Number.isFinite(parsed) ? parsed.toFixed(digits) : "n/a";
    }

    function fmtInt(value) {
      const parsed = Number(value);
      return Number.isFinite(parsed) ? parsed.toLocaleString() : "0";
    }

    function fmtTime(value) {
      if (!value) {
        return "n/a";
      }
      const parsed = new Date(value);
      return Number.isNaN(parsed.getTime()) ? String(value) : parsed.toLocaleString();
    }

    function boolText(value) {
      if (value === null || value === undefined || value === "") {
        return "unknown";
      }
      return value ? "true" : "false";
    }

    function num(value) {
      const parsed = Number(value);
      return Number.isFinite(parsed) ? parsed : NaN;
    }

    function lastSegment(value) {
      return String(value || "").split(/[\\\\/]/).filter(Boolean).pop() || "";
    }

    function esc(value) {
      return String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#39;");
    }

    function attr(value) {
      return esc(value).replaceAll("`", "");
    }
  </script>
</body>
</html>
"""


def render_workspace_app(*, auth_required: bool = False) -> str:
    """Return a self-contained browser app for the workspace API."""

    return APP_HTML.replace("__AUTH_REQUIRED__", "true" if auth_required else "false")
