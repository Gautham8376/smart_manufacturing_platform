/**
 * AERO-MES 4.0 - Root-Cause Post-Mortem Studio Module
 * Answers the core prompt challenge:
 * "What exactly went wrong — which material, which machine, which operator, which batch, and at what point did the problem begin?"
 */

const RCAStudio = {
  async execute() {
    const container = document.getElementById("rca-results-container");
    if (!container) return;
    container.innerHTML = `<div class="p-8 text-center text-slate-400 text-xs">Analyzing defect distribution and multi-factor correlations...</div>`;

    try {
      const rca = await API.executeRCA();
      this.render(rca);
    } catch (err) {
      container.innerHTML = `<div class="p-8 text-center text-rose-400 text-xs">Failed to run RCA: ${err.message}</div>`;
    }
  },

  render(rca) {
    const container = document.getElementById("rca-results-container");
    if (!container) return;

    const pZero = rca.patient_zero_unit;

    container.innerHTML = `
      <!-- Executive Verdict & Confidence -->
      <div class="bg-gradient-to-br from-slate-900 to-purple-950/40 border border-purple-800/40 rounded-xl p-6 shadow-xl space-y-4">
        <div class="flex flex-wrap items-center justify-between gap-4">
          <div>
            <span class="text-2xs font-bold text-purple-400 uppercase tracking-wider">Automated Root Cause Verdict</span>
            <h3 class="text-lg font-bold text-white mt-0.5">${rca.suspected_root_cause}</h3>
          </div>
          <div class="bg-purple-900/40 border border-purple-700/60 px-4 py-2 rounded-xl text-center">
            <span class="text-2xs text-purple-300 block">Diagnostic Confidence</span>
            <span class="text-xl font-bold text-purple-300 font-mono">${rca.confidence_pct}%</span>
          </div>
        </div>

        <p class="text-xs text-slate-300 leading-relaxed border-t border-purple-900/40 pt-3">
          ${rca.hypothesis_narrative || "Statistical correlation identifies parameter divergence onset."}
        </p>
      </div>

      <!-- Patient Zero Pinpoint Card -->
      ${pZero ? `
        <div class="bg-slate-900 border border-rose-500/40 rounded-xl p-6 shadow-xl space-y-4">
          <div class="flex items-center space-x-2">
            <i class="fa-solid fa-crosshairs text-rose-400 text-base"></i>
            <h4 class="text-sm font-bold text-white">"Patient Zero" Incident Onset</h4>
            <span class="text-2xs bg-rose-950 text-rose-300 px-2 py-0.5 rounded border border-rose-800 font-mono">FIRST OCCURRENCE</span>
          </div>

          <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 text-xs">
            <div class="bg-slate-800/60 p-3 rounded-lg border border-slate-700/60">
              <span class="text-2xs text-slate-400 block">First Defective Unit</span>
              <span class="text-sm font-bold font-mono text-rose-300">${pZero.serial_number}</span>
            </div>

            <div class="bg-slate-800/60 p-3 rounded-lg border border-slate-700/60">
              <span class="text-2xs text-slate-400 block">Exact Moment It Began</span>
              <span class="text-xs font-bold font-mono text-slate-200">${pZero.onset_timestamp.replace("T", " ").slice(0, 19)}</span>
            </div>

            <div class="bg-slate-800/60 p-3 rounded-lg border border-slate-700/60">
              <span class="text-2xs text-slate-400 block">Machine & Cell</span>
              <span class="text-xs font-bold font-mono text-cyan-300">${pZero.machine_id}</span>
            </div>

            <div class="bg-slate-800/60 p-3 rounded-lg border border-slate-700/60">
              <span class="text-2xs text-slate-400 block">Material Batch</span>
              <span class="text-xs font-bold font-mono text-amber-300">${pZero.material_lot_id}</span>
            </div>
          </div>

          <div class="bg-rose-950/30 p-3 rounded-lg border border-rose-800/40 text-xs text-rose-200">
            <span class="font-bold">Defect Code:</span> ${pZero.defect_code} — ${pZero.defect_description}
          </div>
        </div>
      ` : ''}

      <!-- Multi-Factor Correlation Matrix -->
      <div class="grid grid-cols-1 md:grid-cols-3 gap-5">
        
        <!-- By Machine -->
        <div class="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg space-y-3">
          <h5 class="text-xs font-bold text-white flex items-center justify-between">
            <span>Correlation by Machine</span>
            <i class="fa-solid fa-industry text-cyan-400 text-2xs"></i>
          </h5>
          <div class="space-y-2 text-xs">
            ${(rca.correlations.by_machine || []).map(m => `
              <div>
                <div class="flex justify-between text-2xs mb-0.5">
                  <span class="text-slate-300 font-mono">${m.id}</span>
                  <span class="text-slate-400">${m.defects} defects (${m.pct}%)</span>
                </div>
                <div class="gauge-track">
                  <div class="gauge-fill bg-cyan-500" style="width: ${m.pct}%"></div>
                </div>
              </div>
            `).join("")}
          </div>
        </div>

        <!-- By Material -->
        <div class="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg space-y-3">
          <h5 class="text-xs font-bold text-white flex items-center justify-between">
            <span>Correlation by Material</span>
            <i class="fa-solid fa-cubes text-amber-400 text-2xs"></i>
          </h5>
          <div class="space-y-2 text-xs">
            ${(rca.correlations.by_material || []).map(mat => `
              <div>
                <div class="flex justify-between text-2xs mb-0.5">
                  <span class="text-slate-300 font-mono">${mat.id}</span>
                  <span class="text-slate-400">${mat.defects} defects (${mat.pct}%)</span>
                </div>
                <div class="gauge-track">
                  <div class="gauge-fill bg-amber-500" style="width: ${mat.pct}%"></div>
                </div>
              </div>
            `).join("")}
          </div>
        </div>

        <!-- By Operator -->
        <div class="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg space-y-3">
          <h5 class="text-xs font-bold text-white flex items-center justify-between">
            <span>Correlation by Operator</span>
            <i class="fa-solid fa-users text-indigo-400 text-2xs"></i>
          </h5>
          <div class="space-y-2 text-xs">
            ${(rca.correlations.by_operator || []).map(op => `
              <div>
                <div class="flex justify-between text-2xs mb-0.5">
                  <span class="text-slate-300 font-mono">${op.id}</span>
                  <span class="text-slate-400">${op.defects} defects (${op.pct}%)</span>
                </div>
                <div class="gauge-track">
                  <div class="gauge-fill bg-indigo-500" style="width: ${op.pct}%"></div>
                </div>
              </div>
            `).join("")}
          </div>
        </div>

      </div>

      <!-- Targeted Containment Scope -->
      ${rca.quarantine_recommendation ? `
        <div class="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg flex items-center justify-between">
          <div>
            <h4 class="text-sm font-bold text-white flex items-center space-x-2">
              <i class="fa-solid fa-shield-virus text-rose-400"></i>
              <span>Recommended Quarantine Containment</span>
            </h4>
            <p class="text-xs text-slate-300 mt-1">${rca.quarantine_recommendation.containment_action}</p>
          </div>
          <div class="text-right">
            <span class="text-xs font-mono font-bold text-rose-300 bg-rose-950/80 px-3 py-1.5 rounded-lg border border-rose-800">
              ${rca.quarantine_recommendation.count} units exposed
            </span>
          </div>
        </div>
      ` : ''}
    `;
  }
};

window.RCAStudio = RCAStudio;
