/**
 * AERO-MES 4.0 - Master Application Coordinator
 * Connects modular components, coordinates WebSocket events, and handles UI tabs.
 */

const App = {
  data: null,

  async init() {
    // 1. Initialize WebSocket
    WSManager.init();
    WSManager.on("FACTORY_TICK", () => {
      this.refresh();
      if (window.SPCChart) SPCChart.updateData();
    });
    WSManager.on("MATERIAL_HOLD_TRIGGERED", () => this.refresh());
    WSManager.on("RUN_DISPATCHED", () => this.refresh());
    WSManager.on("RUN_COMPLETED", () => this.refresh());
    WSManager.on("ALERT_ACKNOWLEDGED", () => this.refresh());
    WSManager.on("ALERT_RESOLVED", () => this.refresh());

    // 2. Fetch Initial State
    await this.refresh();

    // 3. Initialize SPC Chart
    if (window.SPCChart) SPCChart.init();

    // 4. Preload Default Digital Thread
    if (window.DigitalThread) DigitalThread.load("SN-VALVE-2026-1017");

    // 5. Setup Top-Bar Controls
    this.setupControls();
  },

  async refresh() {
    try {
      this.data = await API.getStatus();
      this.renderTopBar(this.data);
      if (window.FactoryTwin) FactoryTwin.render(this.data);
      if (window.DispatchModule) DispatchModule.render(this.data.production_runs, this.data.active_locks);
      this.renderAlerts(this.data.active_alerts);
    } catch (err) {
      console.error("[App] Refresh error:", err);
    }
  },

  renderTopBar(data) {
    document.getElementById("kpi-availability").innerText = `${data.kpis.machine_availability_pct}%`;
    document.getElementById("kpi-active-runs").innerText = data.kpis.active_runs_count;
    document.getElementById("kpi-blocked-runs").innerText = data.kpis.blocked_runs_count;
    document.getElementById("kpi-alerts-count").innerText = data.kpis.total_alerts;
    document.getElementById("radar-badge").innerText = data.kpis.total_alerts;

    // Simulator button
    const simIcon = document.getElementById("sim-icon");
    const simText = document.getElementById("sim-text");
    const btnToggle = document.getElementById("btn-toggle-sim");
    if (data.simulation_running) {
      simIcon.className = "fa-solid fa-pause";
      simText.innerText = "Running";
      btnToggle.className = "px-2.5 py-1 text-xs font-medium rounded bg-emerald-600 hover:bg-emerald-500 text-white flex items-center space-x-1 transition";
    } else {
      simIcon.className = "fa-solid fa-play";
      simText.innerText = "Paused";
      btnToggle.className = "px-2.5 py-1 text-xs font-medium rounded bg-amber-600 hover:bg-amber-500 text-white flex items-center space-x-1 transition";
    }

    // Check Prompt Freeze alert banner
    const onHoldLot = data.materials.find(m => m.lot_id === "LOT-RESIN-204" && m.status === "ON_HOLD");
    const promptBanner = document.getElementById("prompt-alert-banner");
    if (promptBanner) {
      if (onHoldLot) promptBanner.classList.remove("hidden");
      else promptBanner.classList.add("hidden");
    }
  },

  renderAlerts(alerts) {
    const tbody = document.getElementById("alerts-table-body");
    if (!tbody) return;
    tbody.innerHTML = "";

    alerts.forEach(al => {
      let sevBadge = "bg-amber-950/60 text-amber-300 border-amber-800";
      if (al.severity === "CRITICAL") sevBadge = "bg-rose-950/60 text-rose-300 border-rose-800";

      const tr = document.createElement("tr");
      tr.className = "hover:bg-slate-800/40";
      tr.innerHTML = `
        <td class="py-3 px-3">
          <span class="px-2 py-0.5 rounded-full text-2xs font-bold border ${sevBadge}">${al.severity}</span>
        </td>
        <td class="py-3 px-3 font-mono font-bold text-cyan-400">${al.source_type}: ${al.source_id}</td>
        <td class="py-3 px-3 font-semibold text-white">${al.title}</td>
        <td class="py-3 px-3 text-slate-300">${al.message}</td>
        <td class="py-3 px-3 text-emerald-300 font-medium">${al.recommended_action}</td>
        <td class="py-3 px-3 text-right space-x-1">
          <button onclick="App.resolveAlert('${al.id}')" class="px-2 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded text-2xs transition">
            Resolve
          </button>
        </td>
      `;
      tbody.appendChild(tr);
    });
  },

  async resolveAlert(alertId) {
    try {
      await API.resolveAlert(alertId);
      this.refresh();
    } catch (err) {
      alert("Error resolving alert: " + err.message);
    }
  },

  setupControls() {
    document.getElementById("btn-toggle-sim").addEventListener("click", () => {
      const isRunning = this.data ? this.data.simulation_running : true;
      API.toggleSimulator(!isRunning).then(() => this.refresh());
    });

    ["1x", "2x", "5x"].forEach(speedStr => {
      const speedVal = parseFloat(speedStr);
      document.getElementById(`btn-speed-${speedStr}`).addEventListener("click", () => {
        API.toggleSimulator(undefined, speedVal).then(() => {
          ["1x", "2x", "5x"].forEach(s => {
            const el = document.getElementById(`btn-speed-${s}`);
            if (s === speedStr) {
              el.className = "px-2 py-1 text-xs text-cyan-400 bg-slate-700/60 rounded transition font-mono font-bold";
            } else {
              el.className = "px-2 py-1 text-xs text-slate-400 hover:bg-slate-700 rounded transition font-mono";
            }
          });
        });
      });
    });

    document.getElementById("btn-reset-factory").addEventListener("click", () => {
      Scenarios.trigger("reset");
    });
  },

  switchTab(targetTabId) {
    document.querySelectorAll(".tab-content").forEach(el => el.classList.add("hidden"));
    const target = document.getElementById(targetTabId);
    if (target) target.classList.remove("hidden");

    document.querySelectorAll(".nav-tab").forEach(btn => {
      if (btn.getAttribute("data-target") === targetTabId) {
        btn.classList.add("active");
      } else {
        btn.classList.remove("active");
      }
    });
  }
};

window.App = App;

// Global forwarders for DOM inline attributes
function switchTab(id) { App.switchTab(id); }
function searchUnitStory() { DigitalThread.search(); }
function loadUnitStory(s) { DigitalThread.load(s); }
function executeRCA() { RCAStudio.execute(); }
function triggerScenario(name) { Scenarios.trigger(name); }
function updateChartMachine(id) { SPCChart.selectMachine(id); }
function openDispatchModal(runId, orderNum, reqLot) { DispatchModule.openModal(runId, orderNum, reqLot); }
function submitDispatch(e) { DispatchModule.submitDispatch(e); }
function openNewOrderModal() { DispatchModule.openCreateOrderModal(); }
function submitCreateOrder(e) { DispatchModule.submitCreateOrder(e); }
function closeModal(id) { document.getElementById(id).classList.add("hidden"); }

document.addEventListener("DOMContentLoaded", () => {
  App.init();
});
