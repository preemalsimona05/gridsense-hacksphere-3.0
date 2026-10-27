/* GridSense dashboard. Keep this URL environment-specific for deployment. */
const API_BASE = "https://forecast-api-50047160503.development.catalystappsail.in";
const $ = (id) => document.getElementById(id);
let demandChart;
let batteryChart;
let selectedRows = [];
let selectedFile = null;
let lastForecast = [];
let lastDispatch = [];

const weatherFields = ["ambient_temp_c", "humidity_pct", "solar_irradiance_wm2"];

function showToast(message) {
  const toast = $("toast");
  toast.textContent = message;
  toast.classList.remove("hidden");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.add("hidden"), 5000);
}

function logEvent(message, error = false) {
  const list = $("logList");
  const empty = list.querySelector(".log-empty");
  if (empty) empty.remove();
  const entry = document.createElement("div");
  entry.className = `log-entry${error ? " error" : ""}`;
  entry.innerHTML = `<i></i><span>${escapeHtml(message)}</span><time>${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</time>`;
  list.prepend(entry);
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" })[char]);
}

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, options);
  let body;
  try { body = await response.json(); } catch { body = null; }
  if (!response.ok) throw new Error(body?.error || `Backend returned HTTP ${response.status}`);
  return body;
}

function jsonRequestOptions(body) {
  return {
    method: "POST",
    headers: { "Content-Type": "text/plain;charset=UTF-8" },
    body: JSON.stringify(body)
  };
}

async function checkBackend() {
  const status = $("backendStatus");
  try {
    await request("/");
    status.className = "backend-status online";
    status.innerHTML = '<span class="status-dot"></span><span>Backend online</span>';
  } catch {
    status.className = "backend-status offline";
    status.innerHTML = '<span class="status-dot"></span><span>Backend unavailable</span>';
  }
}

function isoDateTime(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")} ${String(date.getHours()).padStart(2, "0")}:00:00`;
}

function renderManualRows(rows = []) {
  const base = rows.length ? rows : Array.from({ length: 24 }, (_, hour) => ({
    timestamp: isoDateTime(new Date(2025, 0, 1, hour)),
    ambient_temp_c: 20,
    humidity_pct: 60,
    solar_irradiance_wm2: hour >= 7 && hour <= 17 ? 200 : 0
  }));
  $("manualRows").innerHTML = base.slice(0, 24).map((row, index) => `<tr>
    <td><input data-field="timestamp" value="${escapeHtml(row.timestamp || "")}" aria-label="Timestamp ${index + 1}"></td>
    <td><input data-field="ambient_temp_c" type="number" step="0.01" value="${row.ambient_temp_c ?? ""}" aria-label="Temperature ${index + 1}"></td>
    <td><input data-field="humidity_pct" type="number" step="0.01" value="${row.humidity_pct ?? ""}" aria-label="Humidity ${index + 1}"></td>
    <td><input data-field="solar_irradiance_wm2" type="number" step="0.01" value="${row.solar_irradiance_wm2 ?? ""}" aria-label="Solar irradiance ${index + 1}"></td>
  </tr>`).join("");
}

function readManualRows() {
  return [...$("manualRows").querySelectorAll("tr")].map((tr) => {
    const row = {};
    tr.querySelectorAll("input").forEach((input) => { row[input.dataset.field] = input.value; });
    return row;
  });
}

function validateRows(rows) {
  if (!Array.isArray(rows) || rows.length !== 24) throw new Error("Please provide exactly 24 forecast rows.");
  rows.forEach((row, index) => {
    if (!row.timestamp || Number.isNaN(Date.parse(row.timestamp))) throw new Error(`Row ${index + 1}: enter a valid timestamp.`);
    weatherFields.forEach((field) => {
      if (row[field] === "" || row[field] === undefined || !Number.isFinite(Number(row[field]))) throw new Error(`Row ${index + 1}: ${field} must be a number.`);
    });
  });
}

function setSelectedRows(rows) {
  selectedRows = rows;
  $("inputHint").textContent = `${rows.length} hourly rows ready. Run the forecast when you are ready.`;
  $("windowLabel").textContent = rows.length ? `${rows.length} hours` : "—";
}

async function loadSample() {
  try {
    const rows = await request("/api/sample");
    selectedFile = null;
    $("fileChip").classList.add("hidden");
    $("csvInput").value = "";
    setSelectedRows(rows);
    renderManualRows(rows);
    $("manualForm").classList.add("hidden");
    logEvent("Loaded backend sample forecast window");
  } catch (error) { showToast(error.message); logEvent(error.message, true); }
}

function parseCsv(text) {
  const lines = text.trim().split(/\r?\n/).filter(Boolean);
  if (lines.length < 2) throw new Error("The CSV is empty.");
  const headers = lines[0].split(",").map((header) => header.trim());
  return lines.slice(1).map((line) => {
    const values = line.split(",");
    return Object.fromEntries(headers.map((header, index) => [header, values[index]?.trim() ?? ""]));
  });
}

function handleFile(file) {
  if (!file) return;
  if (!file.name.toLowerCase().endsWith(".csv")) { showToast("Please choose a CSV file."); return; }
  selectedFile = file;
  $("fileName").textContent = file.name;
  $("fileChip").classList.remove("hidden");
  const reader = new FileReader();
  reader.onload = () => {
    try { setSelectedRows(parseCsv(reader.result)); logEvent(`Loaded ${file.name}`); }
    catch (error) { showToast(error.message); }
  };
  reader.readAsText(file);
}

function setLoading(loading) {
  $("runForecast").disabled = loading;
  $("runLabel").textContent = loading ? "Running forecast…" : "Run forecast";
  $("runForecast").querySelector(".run-icon").classList.toggle("hidden", loading);
  $("runForecast").querySelector(".button-spinner").classList.toggle("hidden", !loading);
}

function formatTime(value) {
  const date = new Date(value.replace(" ", "T"));
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString([], { weekday: "short", hour: "2-digit", minute: "2-digit" });
}

async function runForecast() {
  const rows = $("manualForm").classList.contains("hidden") ? selectedRows : readManualRows();
  try {
    validateRows(rows);
    setLoading(true);
    let response;
    if (selectedFile && $("manualForm").classList.contains("hidden")) {
      const formData = new FormData();
      formData.append("file", selectedFile);
      response = await request("/api/forecast", { method: "POST", body: formData });
    } else {
      response = await request("/api/forecast", jsonRequestOptions(rows));
    }
    if (!Array.isArray(response) || !response.length) throw new Error("The backend returned no forecast rows.");
    const dispatch = await request("/api/dispatch", jsonRequestOptions(response));
    renderResults(response, dispatch);
    logEvent(`Forecast completed for ${response.length} hours`);
  } catch (error) {
    showToast(error.message);
    logEvent(error.message, true);
  } finally { setLoading(false); }
}

function renderResults(rows, dispatch) {
  lastForecast = rows;
  const dispatchRows = Array.isArray(dispatch) ? dispatch : [];
  lastDispatch = dispatchRows;
  const overloads = rows.filter((row) => Number(row.target_demand_kw) >= 200);
  const storage = dispatchRows.filter((row) => row.mode === "Renewable Storage Mode").length;
  const peak = rows.reduce((best, row) => Number(row.target_demand_kw) > Number(best.target_demand_kw) ? row : best, rows[0]);
  $("peakDemand").textContent = `${Number(peak.target_demand_kw).toFixed(1)} kW`;
  $("peakTime").textContent = `Peak at ${formatTime(peak.timestamp)}`;
  $("storageHours").textContent = storage;
  $("overloadHours").textContent = overloads.length;
  $("rowCount").textContent = `${rows.length} hours`;
  $("windowLabel").textContent = `${formatTime(rows[0].timestamp)} — ${formatTime(rows[rows.length - 1].timestamp)}`;
  $("alertBanner").classList.toggle("hidden", !overloads.length);
  $("alertText").textContent = overloads.length ? overloads.map((row) => `${formatTime(row.timestamp)} (${Number(row.target_demand_kw).toFixed(1)} kW)`).join(" · ") : "";
  const finalSoc = dispatchRows.at(-1);
  $("batteryReserve").textContent = finalSoc ? `${Number(finalSoc.battery_soc_pct).toFixed(0)}%` : "—";
  $("batterySub").textContent = finalSoc ? `${Number(finalSoc.battery_soc_kwh).toFixed(0)} kWh remaining` : "Dispatch simulation";
  $("socPill").textContent = finalSoc ? `${Number(finalSoc.battery_soc_pct).toFixed(0)}% reserve` : "—";
  $("resultsBody").innerHTML = rows.map((row, index) => {
    const dispatchRow = dispatchRows[index] || {};
    const alert = Number(row.target_demand_kw) >= 200 || dispatchRow.overload_alert;
    const storageMode = dispatchRow.mode === "Renewable Storage Mode";
    return `<tr><td class="time-cell">${escapeHtml(formatTime(row.timestamp))}</td><td class="demand-cell">${Number(row.target_demand_kw).toFixed(1)} kW</td><td><span class="mode-badge ${storageMode ? "mode-storage" : "mode-main"}">${storageMode ? "● Renewable Storage Mode" : "● Main Grid Mode"}</span></td><td><span class="state-badge ${alert ? "state-alert" : "state-normal"}">${alert ? "⚠ Critical Overload" : "Normal"}</span></td></tr>`;
  }).join("");
  renderCharts(rows, dispatchRows);
}

function renderCharts(rows, dispatchRows) {
  $("chartEmpty").classList.add("hidden");
  $("batteryEmpty").classList.toggle("hidden", !dispatchRows.length);
  const labels = rows.map((row) => new Date(row.timestamp.replace(" ", "T")).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }));
  const peakIndexes = rows.map((row, index) => ({ hour: new Date(row.timestamp.replace(" ", "T")).getHours(), index })).filter(({ hour }) => hour >= 18 && hour <= 22);
  const gridColor = getComputedStyle(document.documentElement).getPropertyValue("--line");
  const textColor = getComputedStyle(document.documentElement).getPropertyValue("--muted");
  if (demandChart) demandChart.destroy();
  demandChart = new Chart($("demandChart"), { type: "line", data: { labels, datasets: [{ label: "Demand", data: rows.map((row) => row.target_demand_kw), borderColor: "#69e0bb", backgroundColor: "#69e0bb20", fill: true, tension: .35, pointRadius: 2, pointHoverRadius: 5 }] }, options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, annotation: {} }, scales: { x: { grid: { color: gridColor }, ticks: { color: textColor, maxTicksLimit: 12, font: { family: "DM Mono", size: 10 } } }, y: { grid: { color: gridColor }, ticks: { color: textColor, callback: (value) => `${value} kW` } } } }, plugins: [{ id: "thresholds", beforeDraw(chart) { const { ctx, chartArea, scales } = chart; if (peakIndexes.length) { const step = peakIndexes.length > 1 ? scales.x.getPixelForValue(peakIndexes[1].index) - scales.x.getPixelForValue(peakIndexes[0].index) : 14; const start = scales.x.getPixelForValue(peakIndexes[0].index) - step / 2; const end = scales.x.getPixelForValue(peakIndexes.at(-1).index) + step / 2; ctx.save(); ctx.fillStyle = "#6da8ff0d"; ctx.fillRect(Math.max(start, chartArea.left), chartArea.top, Math.min(end, chartArea.right) - Math.max(start, chartArea.left), chartArea.bottom - chartArea.top); ctx.restore(); } }, afterDraw(chart) { const { ctx, chartArea, scales } = chart; [ [160, "#ffb454"], [200, "#ff6b72"] ].forEach(([value, color]) => { const y = scales.y.getPixelForValue(value); ctx.save(); ctx.setLineDash([6, 5]); ctx.strokeStyle = color; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(chartArea.left, y); ctx.lineTo(chartArea.right, y); ctx.stroke(); ctx.fillStyle = color; ctx.font = "10px DM Mono"; ctx.fillText(`${value} kW`, chartArea.right - 38, y - 5); ctx.restore(); }); } }] });
  if (batteryChart) batteryChart.destroy();
  if (dispatchRows.length) batteryChart = new Chart($("batteryChart"), { type: "line", data: { labels, datasets: [{ data: dispatchRows.map((row) => row.battery_soc_pct), borderColor: "#6da8ff", backgroundColor: "#6da8ff20", fill: true, tension: .35, pointRadius: 2 }] }, options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { display: false }, y: { min: 0, max: 100, grid: { color: gridColor }, ticks: { color: textColor, callback: (value) => `${value}%` } } } } });
}

function init() {
  renderManualRows();
  checkBackend();
  setInterval(checkBackend, 30000);
  $("loadSample").addEventListener("click", loadSample);
  $("runForecast").addEventListener("click", runForecast);
  $("manualToggle").addEventListener("click", () => { $("manualForm").classList.toggle("hidden"); $("manualToggle").innerHTML = $("manualForm").classList.contains("hidden") ? "<span>＋</span> Open 24-row weather form" : "<span>−</span> Close weather form"; });
  $("fillManual").addEventListener("click", () => renderManualRows());
  $("csvInput").addEventListener("change", (event) => handleFile(event.target.files[0]));
  $("clearFile").addEventListener("click", () => { selectedFile = null; selectedRows = []; $("fileChip").classList.add("hidden"); $("csvInput").value = ""; });
  ["dragenter", "dragover"].forEach((event) => $("dropZone").addEventListener(event, (e) => { e.preventDefault(); $("dropZone").classList.add("dragging"); }));
  ["dragleave", "drop"].forEach((event) => $("dropZone").addEventListener(event, (e) => { e.preventDefault(); $("dropZone").classList.remove("dragging"); }));
  $("dropZone").addEventListener("drop", (event) => handleFile(event.dataTransfer.files[0]));
  $("dismissAlert").addEventListener("click", () => $("alertBanner").classList.add("hidden"));
  $("clearLog").addEventListener("click", () => { $("logList").innerHTML = '<div class="log-empty">No runs yet. The system is standing by.</div>'; });
  $("themeToggle").addEventListener("click", () => { const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark"; document.documentElement.dataset.theme = next; $("themeToggle").textContent = next === "dark" ? "☼" : "☾"; if (lastForecast.length) renderCharts(lastForecast, lastDispatch); });
}
document.addEventListener("DOMContentLoaded", init);
