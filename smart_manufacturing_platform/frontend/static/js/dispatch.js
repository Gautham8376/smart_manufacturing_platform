/**
 * AERO-MES 4.0 - Work Order Dispatch & Anti-Collision Module
 * Handles work order scheduling, two-phase resource locking, and collision diagnosis.
 */

const DispatchModule = {
  render(runs, locks) {
    this.renderRuns(runs);
    this.renderLocks(locks);
  },

  renderRuns(runs) {
    const tbody = document.getElementById("runs-table-body");
    if (!tbody) return;
    tbody.innerHTML = "";

    runs.forEach(r => {
      let statusClass = "bg-slate-800 text-slate-300 border-slate-700";
      if (r.status === "RUNNING") statusClass = "bg-emerald-950/60 text-emerald-300 border-emerald-800";
      else if (r.status === "BLOCKED") statusClass = "bg-rose-950/60 text-rose-300 border-rose-800";
      else if (r.status === "COMPLETED") statusClass = "bg-blue-950/60 text-blue-300 border-blue-800";

      const tr = document.createElement("tr");
      tr.className = "hover:bg-slate-800/40 transition";
      tr.innerHTML = `
        <td class="py-3 px-3">
          <div class="font-mono font-bold text-white">${r.id}</div>
          <div class="text-2xs text-slate-400 font-mono">${r.order_number}</div>
        </td>
        <td class="py-3 px-3">
          <div class="font-semibold text-slate-200">${r.product_name}</div>
          <div class="text-2xs text-slate-400 font-mono">${r.product_sku}</div>
        </td>
        <td class="py-3 px-3 font-mono ${r.machine_id ? 'text-cyan-300 font-semibold' : 'text-slate-500'}">
          ${r.machine_id || 'Unassigned'}
        </td>
        <td class="py-3 px-3 ${r.operator_id ? 'text-indigo-300 font-semibold' : 'text-slate-500'}">
          ${r.operator_id || 'Unassigned'}
        </td>
        <td class="py-3 px-3 font-mono ${r.required_material_lot_id ? 'text-amber-300 font-semibold' : 'text-slate-500'}">
          ${r.required_material_lot_id || 'Unassigned'}
        </td>
        <td class="py-3 px-3">
          <div class="flex items-center space-x-2">
            <span class="font-mono font-bold text-white text-2xs">${r.produced_qty}/${r.target_qty}</span>
            <div class="w-16 bg-slate-800 h-1.5 rounded-full overflow-hidden">
              <div class="bg-cyan-500 h-full rounded-full" style="width: ${(r.produced_qty / r.target_qty) * 100}%"></div>
            </div>
          </div>
          ${r.scrap_qty > 0 ? `<div class="text-2xs text-rose-400 mt-0.5">Scrap: ${r.scrap_qty}</div>` : ''}
        </td>
        <td class="py-3 px-3">
          <span class="px-2 py-0.5 rounded-full text-2xs font-bold border ${statusClass}">${r.status}</span>
          ${r.blocked_reason ? `<div class="text-2xs text-rose-400 mt-1 max-w-xs truncate" title="${r.blocked_reason}">${r.blocked_reason}</div>` : ''}
        </td>
        <td class="py-3 px-3 text-slate-300 font-mono text-2xs">${r.due_date}</td>
        <td class="py-3 px-3 text-right space-x-1.5">
          ${r.status === "SCHEDULED" ? `
            <button onclick="DispatchModule.openModal('${r.id}', '${r.order_number}', '${r.required_material_lot_id}')" class="px-2.5 py-1 bg-blue-600 hover:bg-blue-500 text-white rounded text-2xs font-semibold transition">
              Dispatch
            </button>
          ` : ''}
          ${r.status === "RUNNING" ? `
            <button onclick="DispatchModule.completeRun('${r.id}')" class="px-2 py-1 bg-emerald-600 hover:bg-emerald-500 text-white rounded text-2xs font-semibold transition">
              Complete
            </button>
            <button onclick="DispatchModule.abortRun('${r.id}')" class="px-2 py-1 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded text-2xs transition">
              Abort
            </button>
          ` : ''}
          ${r.status === "BLOCKED" ? `
            <button onclick="DispatchModule.abortRun('${r.id}')" class="px-2.5 py-1 bg-rose-600 hover:bg-rose-500 text-white rounded text-2xs font-semibold transition">
              Clear & Abort
            </button>
          ` : ''}
        </td>
      `;
      tbody.appendChild(tr);
    });
  },

  renderLocks(locks) {
    const tbody = document.getElementById("locks-table-body");
    if (!tbody) return;
    tbody.innerHTML = "";

    locks.forEach(l => {
      const tr = document.createElement("tr");
      tr.className = "hover:bg-slate-800/40 text-2xs text-slate-300";
      tr.innerHTML = `
        <td class="py-2 px-3 text-slate-400">#${l.id}</td>
        <td class="py-2 px-3 font-semibold text-cyan-400">${l.resource_type}</td>
        <td class="py-2 px-3 text-white font-bold">${l.resource_id}</td>
        <td class="py-2 px-3 text-blue-300">${l.run_id}</td>
        <td class="py-2 px-3 text-slate-400">${l.acquired_at.split("T")[1].slice(0, 8)}</td>
        <td class="py-2 px-3"><span class="px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800 font-bold">${l.lock_status}</span></td>
        <td class="py-2 px-3 text-slate-400 font-sans">${l.notes}</td>
      `;
      tbody.appendChild(tr);
    });
  },

  openModal(runId, orderNum, reqLot) {
    const currentData = window.App ? window.App.data : null;
    if (!currentData) return;

    document.getElementById("dispatch-run-id").value = runId;
    document.getElementById("dispatch-run-display").value = `${runId} (${orderNum})`;
    document.getElementById("dispatch-error-box").classList.add("hidden");

    // Populate Machines
    const machSelect = document.getElementById("dispatch-machine-select");
    machSelect.innerHTML = currentData.machines.map(m => `
      <option value="${m.id}" ${m.status !== 'IDLE' ? 'disabled' : ''}>
        ${m.id} - ${m.name} (${m.status})
      </option>
    `).join("");

    // Populate Operators
    const opSelect = document.getElementById("dispatch-operator-select");
    opSelect.innerHTML = currentData.operators.map(o => `
      <option value="${o.id}" ${o.status !== 'AVAILABLE' ? 'disabled' : ''}>
        ${o.name} (${o.badge_id}) - ${o.status} [Certs: ${o.certified_operations.join(', ')}]
      </option>
    `).join("");

    // Populate Materials
    const matSelect = document.getElementById("dispatch-material-select");
    matSelect.innerHTML = currentData.materials.map(mat => `
      <option value="${mat.lot_id}" ${mat.lot_id === reqLot ? 'selected' : ''} ${mat.status === 'ON_HOLD' ? 'disabled' : ''}>
        ${mat.lot_id} - ${mat.name} [${mat.status}] (${mat.remaining_qty} ${mat.unit_of_measure})
      </option>
    `).join("");

    document.getElementById("modal-dispatch").classList.remove("hidden");
  },

  async submitDispatch(e) {
    e.preventDefault();
    const runId = document.getElementById("dispatch-run-id").value;
    const machineId = document.getElementById("dispatch-machine-select").value;
    const operatorId = document.getElementById("dispatch-operator-select").value;
    const lotId = document.getElementById("dispatch-material-select").value;

    const errorBox = document.getElementById("dispatch-error-box");
    const errorMsg = document.getElementById("dispatch-error-msg");
    errorBox.classList.add("hidden");

    try {
      const res = await API.dispatchRun({
        run_id: runId,
        machine_id: machineId,
        operator_id: operatorId,
        material_lot_id: lotId
      });

      if (res.status === 409) {
        // Collision prevented!
        errorBox.classList.remove("hidden");
        errorMsg.innerText = res.data.message || "Double-booking collision prevented.";
        return;
      }

      if (!res.ok) {
        errorBox.classList.remove("hidden");
        errorMsg.innerText = res.data.detail || "Dispatch failed.";
        return;
      }

      document.getElementById("modal-dispatch").classList.add("hidden");
      if (window.App) window.App.refresh();
    } catch (err) {
      errorBox.classList.remove("hidden");
      errorMsg.innerText = err.message;
    }
  },

  openCreateOrderModal() {
    const currentData = window.App ? window.App.data : null;
    const matSelect = document.getElementById("new-order-material");
    matSelect.innerHTML = (currentData ? currentData.materials : []).map(mat => `
      <option value="${mat.lot_id}">${mat.lot_id} - ${mat.name} (${mat.status})</option>
    `).join("");
    document.getElementById("modal-create-order").classList.remove("hidden");
  },

  async submitCreateOrder(e) {
    e.preventDefault();
    const payload = {
      order_number: document.getElementById("new-order-num").value,
      product_sku: document.getElementById("new-order-sku").value,
      product_name: document.getElementById("new-order-name").value,
      target_qty: parseInt(document.getElementById("new-order-qty").value),
      required_material_lot_id: document.getElementById("new-order-material").value
    };

    try {
      await API.createRun(payload);
      document.getElementById("modal-create-order").classList.add("hidden");
      if (window.App) window.App.refresh();
    } catch (err) {
      alert("Order creation error: " + err.message);
    }
  },

  async completeRun(runId) {
    try {
      await API.completeRun(runId);
      if (window.App) window.App.refresh();
    } catch (err) {
      alert("Error completing run: " + err.message);
    }
  },

  async abortRun(runId) {
    if (confirm(`Abort run ${runId} and release all locked resources?`)) {
      try {
        await API.abortRun(runId);
        if (window.App) window.App.refresh();
      } catch (err) {
        alert("Error aborting run: " + err.message);
      }
    }
  }
};

window.DispatchModule = DispatchModule;
