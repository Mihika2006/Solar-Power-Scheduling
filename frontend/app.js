/* DSSRES dashboard client: Chart.js + Fetch */
const API = location.protocol === "file:" ? "http://localhost:8000" : "";
const $ = (id) => document.getElementById(id);
let ivChart = null, genChart = null;

Chart.defaults.color = "#8fa0c0";
Chart.defaults.borderColor = "#263454";
Chart.defaults.font.family = "Inter, system-ui, sans-serif";

function setStatus(msg, kind = "") {
  const el = $("status");
  el.textContent = msg;
  el.className = "status " + kind;
}

async function api(path, options) {
  const res = await fetch(API + path, options);
  if (!res.ok) {
    let detail = res.statusText;
    try { const j = await res.json(); detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch (_) {}
    throw new Error(detail);
  }
  return res.json();
}

function renderMaterial(m, control) {
  $("mat-name").textContent = m.label;
  $("m-voc").textContent = m.voc.toFixed(2);
  $("m-jsc").textContent = m.jsc.toFixed(1);
  $("m-ff").textContent = m.ff.toFixed(2);
  $("m-eta").textContent = m.eta.toFixed(2) + "%";
  if (m.key === "Control") {
    $("m-gain").textContent = "Baseline cell for comparison.";
  } else {
    const rel = ((m.eta - control.eta) / control.eta) * 100;
    $("m-gain").textContent = "+" + rel.toFixed(1) + "% efficiency vs undoped control (" + control.eta.toFixed(2) + "%).";
  }
}

function renderIV(selected, control) {
  const toPts = (m) => m.iv.voltage.map((v, i) => ({ x: v, y: m.iv.current[i] }));
  const datasets = [
    { label: control.label, data: toPts(control), borderColor: "#8fa0c0", borderDash: [6, 4], pointRadius: 0, tension: 0.25, showLine: true },
  ];
  if (selected.key !== "Control") {
    datasets.push({ label: selected.label, data: toPts(selected), borderColor: "#f5b942", backgroundColor: "#f5b942", pointRadius: 0, borderWidth: 2.5, tension: 0.25, showLine: true });
    datasets.push({ label: selected.label + " MPP", data: [{ x: selected.iv.mpp.v, y: selected.iv.mpp.j }], borderColor: "#f5b942", backgroundColor: "#f5b942", pointRadius: 6, showLine: false });
  }
  if (ivChart) ivChart.destroy();
  ivChart = new Chart($("ivChart"), {
    type: "scatter",
    data: { datasets },
    options: {
      responsive: true, maintainAspectRatio: false, animation: { duration: 400 },
      scales: {
        x: { type: "linear", min: 0, title: { display: true, text: "Voltage (V)" } },
        y: { min: 0, title: { display: true, text: "Current density (mA/cm²)" } },
      },
      plugins: { legend: { position: "bottom" }, tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${c.parsed.y.toFixed(2)} mA/cm² @ ${c.parsed.x.toFixed(3)} V` } } },
    },
  });
}

function renderGeneration(hourly) {
  const labels = hourly.map((h) => h.label);
  const datasets = [
    { type: "bar", label: "Irrigation Pump (L1)", data: hourly.map((h) => h.irrigation_kw), backgroundColor: "#3b82f6", stack: "loads", yAxisID: "y", order: 3 },
    { type: "bar", label: "Cold Storage (L2)", data: hourly.map((h) => h.cold_storage_kw), backgroundColor: "#22d3ee", stack: "loads", yAxisID: "y", order: 3 },
    { type: "bar", label: "Crop Dryer (L3)", data: hourly.map((h) => h.crop_dryer_kw), backgroundColor: "#a78bfa", stack: "loads", yAxisID: "y", order: 3 },
    { type: "line", label: "Calibrated Power P_pred (kW)", data: hourly.map((h) => h.p_pred_kw), borderColor: "#3ddc97", backgroundColor: "#3ddc97", borderWidth: 2.5, pointRadius: 2, tension: 0.3, stack: "power", yAxisID: "y", order: 1 },
    { type: "line", label: "Forecast G(t) (W/m²)", data: hourly.map((h) => h.g_forecast), borderColor: "#f5b942", backgroundColor: "#f5b942", borderWidth: 2, pointRadius: 0, tension: 0.3, stack: "irr", yAxisID: "y1", order: 2 },
    { type: "line", label: "Observed G (W/m²)", data: hourly.map((h) => h.g_actual), borderColor: "#f5b942", borderDash: [4, 4], borderWidth: 1.5, pointRadius: 0, tension: 0.3, stack: "obs", yAxisID: "y1", order: 2, hidden: true },
  ];
  if (genChart) genChart.destroy();
  genChart = new Chart($("genChart"), {
    data: { labels, datasets },
    options: {
      responsive: true, maintainAspectRatio: false, interaction: { mode: "index", intersect: false }, animation: { duration: 400 },
      scales: {
        x: { stacked: true, title: { display: true, text: "Local solar time" } },
        y: { stacked: true, beginAtZero: true, position: "left", title: { display: true, text: "Power (kW)" } },
        y1: { beginAtZero: true, position: "right", grid: { drawOnChartArea: false }, title: { display: true, text: "Irradiance (W/m²)" } },
      },
      plugins: { legend: { position: "bottom" } },
    },
  });
}

function renderSummary(s, sim) {
  $("s-gen").textContent = s.total_generated_kwh.toFixed(1);
  $("s-saved").textContent = s.grid_saved_pct.toFixed(1) + "%";
  $("s-co2").textContent = s.carbon_reduction_kg.toFixed(1);
  $("s-grid").textContent = s.grid_import_kwh.toFixed(1);
  $("s-note").textContent =
    `Solar served ${s.solar_used_kwh.toFixed(1)} of ${s.farm_demand_kwh.toFixed(1)} kWh daily farm demand; ` +
    `${s.surplus_unused_kwh.toFixed(1)} kWh surplus unused. Control cell would generate ${s.control_generated_kwh.toFixed(1)} kWh ` +
    `(${s.control_grid_saved_pct.toFixed(1)}% grid saved). Emission factor ${s.emission_factor} kg CO₂/kWh. ` +
    `Hours met: irrigation ${s.irrigation_hours_met}, cold storage ${s.cold_storage_hours_met}, dryer ${s.dryer_hours_met}.`;
  const m = sim.model.metrics;
  $("q-rmse").textContent = m.rmse.toFixed(1);
  $("q-mae").textContent = m.mae.toFixed(1);
  $("q-r2").textContent = m.r2.toFixed(3);
  $("q-src").textContent = sim.weather.source;
  $("q-note").textContent =
    `Chronological split: ${m.train_samples} training hours, ${m.test_samples} held-out hours. ${sim.weather.note}`;
}

async function showCurves() {
  const data = await api("/api/iv-curve/" + encodeURIComponent($("dopant").value));
  renderMaterial(data.selected, data.control);
  renderIV(data.selected, data.control);
}

async function runSimulation() {
  const btn = $("run");
  btn.disabled = true;
  setStatus("Fetching weather, training Random Forest and scheduling loads…");
  try {
    const body = {
      dopant: $("dopant").value,
      area_m2: parseFloat($("area").value),
      latitude: parseFloat($("lat").value),
      longitude: parseFloat($("lon").value),
      use_live_weather: $("live").checked,
    };
    if ([body.area_m2, body.latitude, body.longitude].some(Number.isNaN)) throw new Error("Please enter valid numeric area, latitude and longitude.");
    const sim = await api("/api/simulate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    renderMaterial(sim.iv.selected, sim.iv.control);
    renderIV(sim.iv.selected, sim.iv.control);
    renderGeneration(sim.hourly);
    renderSummary(sim.summary, sim);
    $("sim-date").textContent = "(" + sim.date + ")";
    setStatus(sim.weather.synthetic ? "Simulation complete. " + sim.weather.note : "Simulation complete using live NASA POWER data.", sim.weather.synthetic ? "warn" : "ok");
  } catch (err) {
    setStatus("Simulation failed: " + err.message, "error");
  } finally {
    btn.disabled = false;
  }
}

async function init() {
  try {
    const { materials } = await api("/api/materials");
    const sel = $("dopant");
    materials.forEach((m) => {
      const o = document.createElement("option");
      o.value = m.key;
      o.textContent = m.key === "Control" ? "Control (Undoped)" : m.key + "-doped";
      sel.appendChild(o);
    });
    sel.value = "La";
    sel.addEventListener("change", () => showCurves().catch((e) => setStatus(e.message, "error")));
    $("run").addEventListener("click", runSimulation);
    await showCurves();
    await runSimulation();
  } catch (err) {
    setStatus("Cannot reach the backend (" + err.message + "). Start it with: uvicorn main:app --port 8000", "error");
  }
}

init();
