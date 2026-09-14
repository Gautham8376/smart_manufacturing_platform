/**
 * AERO-MES 4.0 - Factory Floor Digital Twin Module
 * Renders machine telemetry gauges, material lots, hold gates, and operator cards.
 */

const FactoryTwin = {
  render(data) {
    this.renderMachines(data.machines, data.production_runs, data.operators);
    this.renderMaterials(data.materials);
    this.renderOperators(data.operators);
  },

  renderMachines(machines, runs, operators) {
    const container = document.getElementById("machines-grid");
    if (!container) return;
    container.innerHTML = "";

    machines.forEach(m => {
      let statusClass = "bg-slate-800 text-slate-300 border-slate-700";
      let pulseClass = "";
      if (m.status === "RUNNING") {
        statusClass = "bg-emerald-950/60 text-emerald-300 border-emerald-800";
        pulseClass = "pulse-green";
      } else if (m.status === "WARNING") {
        statusClass = "bg-amber-950/60 text-amber-300 border-amber-800";
        pulseClass = "pulse-amber";
      } else if (m.status === "BLOCKED") {
        statusClass = "bg-rose-950/60 text-rose-300 border-rose-800";
        pulseClass = "pulse-red";
      }

      const activeRun = runs.find(r => r.id === m.current_run_id);
      const assignedOp = operators.find(o => o.active_machine_id === m.id);

      // Vibration gauge %
      const vibPct = Math.min(100, Math.round((m.vibration_mms / m.vib_threshold_critical) * 100));
      let vibColor = "bg-cyan-500";
      if (m.vibration_mms >= m.vib_threshold_critical) vibColor = "bg-rose-500";
      else if (m.vibration_mms >= m.vib_threshold_warning) vibColor = "bg-amber-500";

      // Temp gauge %
      const tempPct = Math.min(100, Math.round((m.temperature_c / m.temp_threshold_critical) * 100));
      let tempColor = "bg-blue-500";
      if (m.temperature_c >= m.temp_threshold_critical) tempColor = "bg-rose-500";
      else if (m.temperature_c >= m.temp_threshold_warning) tempColor = "bg-amber-500";

      const card = document.createElement("div");
      card.className = "bg-slate-900 border border-slate-800 hover:border-slate-700 rounded-xl p-4 shadow-lg flex flex-col justify-between space-y-4 transition";
      card.innerHTML = `
        <div>
          <div class="flex items-start justify-between">
            <div>
              <span class="text-xs font-mono font-bold text-cyan-400">${m.id}</span>
              <h4 class="font-bold text-white text-sm leading-tight">${m.name}</h4>
              <p class="text-2xs text-slate-400 mt-0.5">${m.cell}</p>
            </div>
            <span class="text-2xs font-bold px-2 py-0.5 rounded-full border ${statusClass} ${pulseClass}">
              ${m.status}
            </span>
          </div>

          <!-- Gauges -->
          <div class="mt-3.5 space-y-2.5 text-xs">
            <div>
              <div class="flex justify-between text-2xs mb-1">
                <span class="text-slate-400 flex items-center space-x-1">
                  <i class="fa-solid fa-wave-square text-cyan-400"></i>
                  <span>Vibration</span>
                </span>
                <span class="font-mono font-bold text-slate-200">${m.vibration_mms.toFixed(2)} mm/s <span class="text-slate-500 font-normal">/ ${m.vib_threshold_critical}</span></span>
              </div>
              <div class="gauge-track">
                <div class="gauge-fill ${vibColor}" style="width: ${vibPct}%"></div>
              </div>
            </div>

            <div>
              <div class="flex justify-between text-2xs mb-1">
                <span class="text-slate-400 flex items-center space-x-1">
                  <i class="fa-solid fa-temperature-three-quarters text-blue-400"></i>
                  <span>Temperature</span>
                </span>
                <span class="font-mono font-bold text-slate-200">${m.temperature_c.toFixed(1)}°C <span class="text-slate-500 font-normal">/ ${m.temp_threshold_critical}°</span></span>
              </div>
              <div class="gauge-track">
                <div class="gauge-fill ${tempColor}" style="width: ${tempPct}%"></div>
              </div>
            </div>

            <div>
              <div class="flex justify-between text-2xs mb-1">
                <span class="text-slate-400 flex items-center space-x-1">
                  <i class="fa-solid fa-gauge-high text-indigo-400"></i>
                  <span>Spindle Load</span>
                </span>
                <span class="font-mono font-bold text-slate-200">${m.spindle_load_pct.toFixed(1)}%</span>
              </div>
              <div class="gauge-track">
                <div class="gauge-fill bg-indigo-500" style="width: ${m.spindle_load_pct}%"></div>
              </div>
            </div>
          </div>
        </div>

        <!-- Bindings Footer -->
        <div class="pt-3 border-t border-slate-800/80 space-y-2 text-2xs">
          <div class="flex items-center justify-between text-slate-400">
            <span>Active Run:</span>
            <span class="font-mono font-semibold ${activeRun ? 'text-cyan-300' : 'text-slate-500'}">
              ${activeRun ? `${activeRun.id} (${activeRun.produced_qty}/${activeRun.target_qty})` : 'None (Idle)'}
            </span>
          </div>
          <div class="flex items-center justify-between text-slate-400">
            <span>Operator:</span>
            <span class="font-semibold ${assignedOp ? 'text-indigo-300' : 'text-slate-500'}">
              ${assignedOp ? `${assignedOp.name}` : 'Unassigned'}
            </span>
          </div>
        </div>
      `;
      container.appendChild(card);
    });
  },

  renderMaterials(materials) {
    const tbody = document.getElementById("materials-table-body");
    if (!tbody) return;
    tbody.innerHTML = "";

    materials.forEach(mat => {
      let statusBadge = "bg-slate-800 text-slate-300 border-slate-700";
      if (mat.status === "AVAILABLE") statusBadge = "bg-emerald-950/60 text-emerald-300 border-emerald-800";
      else if (mat.status === "IN_USE") statusBadge = "bg-blue-950/60 text-blue-300 border-blue-800";
      else if (mat.status === "ON_HOLD") statusBadge = "bg-rose-950/60 text-rose-300 border-rose-800";

      const tr = document.createElement("tr");
      tr.className = "hover:bg-slate-800/40 transition";
      tr.innerHTML = `
        <td class="py-2.5 px-3 font-mono font-bold text-white">${mat.lot_id}</td>
        <td class="py-2.5 px-3">
          <div class="font-semibold text-slate-200">${mat.name}</div>
          <div class="text-2xs text-slate-400">${mat.material_code} • ${mat.supplier_name}</div>
        </td>
        <td class="py-2.5 px-3 font-mono text-slate-300">${mat.supplier_lot}</td>
        <td class="py-2.5 px-3">
          <div class="font-mono font-bold text-slate-200">${mat.remaining_qty} / ${mat.initial_qty} ${mat.unit_of_measure}</div>
          <div class="w-24 bg-slate-800 h-1.5 rounded-full overflow-hidden mt-1">
            <div class="bg-cyan-500 h-full rounded-full" style="width: ${(mat.remaining_qty / mat.initial_qty) * 100}%"></div>
          </div>
        </td>
        <td class="py-2.5 px-3">
          <span class="px-2 py-0.5 rounded-full text-2xs font-bold border ${statusBadge}">${mat.status}</span>
          ${mat.hold_reason ? `<div class="text-2xs text-rose-400 mt-0.5 max-w-xs truncate" title="${mat.hold_reason}">Reason: ${mat.hold_reason}</div>` : ''}
        </td>
        <td class="py-2.5 px-3 text-right">
          ${mat.status === "ON_HOLD" ? `
            <button onclick="FactoryTwin.releaseHold('${mat.lot_id}')" class="px-2.5 py-1 bg-emerald-600/80 hover:bg-emerald-600 text-white rounded text-2xs font-semibold transition">
              Release Hold
            </button>
          ` : `
            <button onclick="FactoryTwin.promptHold('${mat.lot_id}')" class="px-2.5 py-1 bg-rose-600/80 hover:bg-rose-600 text-white rounded text-2xs font-semibold transition">
              Put on Hold
            </button>
          `}
        </td>
      `;
      tbody.appendChild(tr);
    });
  },

  renderOperators(operators) {
    const container = document.getElementById("operators-list");
    if (!container) return;
    container.innerHTML = "";

    operators.forEach(op => {
      let statusClass = "bg-slate-800 text-slate-300 border-slate-700";
      if (op.status === "AVAILABLE") statusClass = "bg-emerald-950/60 text-emerald-300 border-emerald-800";
      else if (op.status === "ASSIGNED") statusClass = "bg-blue-950/60 text-blue-300 border-blue-800";

      const item = document.createElement("div");
      item.className = "bg-slate-800/50 border border-slate-700/60 rounded-lg p-3 text-xs flex items-center justify-between";
      item.innerHTML = `
        <div class="space-y-0.5">
          <div class="font-bold text-white flex items-center space-x-2">
            <span>${op.name}</span>
            <span class="text-2xs font-mono text-slate-400 font-normal">(${op.badge_id})</span>
          </div>
          <div class="text-2xs text-slate-400">${op.shift}</div>
          <div class="text-2xs text-cyan-400">Certified: ${op.certified_operations.join(", ")}</div>
        </div>
        <div class="text-right space-y-1">
          <span class="px-2 py-0.5 rounded-full text-2xs font-bold border ${statusClass}">${op.status}</span>
          ${op.active_machine_id ? `<div class="text-2xs text-indigo-300 font-mono">On: ${op.active_machine_id}</div>` : ''}
        </div>
      `;
      container.appendChild(item);
    });
  },

  async promptHold(lotId) {
    const reason = prompt(`Enter QA Hold Reason for Material Lot ${lotId}:`, "QA incoming chemical verification failed");
    if (!reason) return;
    try {
      await API.setMaterialHold(lotId, reason);
      if (window.App) window.App.refresh();
    } catch (err) {
      alert("Error setting hold: " + err.message);
    }
  },

  async releaseHold(lotId) {
    try {
      await API.releaseMaterialHold(lotId);
      if (window.App) window.App.refresh();
    } catch (err) {
      alert("Error releasing hold: " + err.message);
    }
  }
};

window.FactoryTwin = FactoryTwin;
