/**
 * AERO-MES 4.0 - Digital Thread ("Every Unit Tells Its Story") Module
 * Reconstructs the full manufacturing genealogy, human touchpoints, and in-process sensor telemetry.
 */

const DigitalThread = {
  async search() {
    const input = document.getElementById("input-search-serial");
    if (!input) return;
    const serial = input.value.trim();
    if (serial) this.load(serial);
  },

  async load(serial) {
    const container = document.getElementById("unit-story-container");
    if (!container) return;
    container.innerHTML = `<div class="p-8 text-center text-slate-400 text-xs">Loading unit story for ${serial}...</div>`;

    try {
      const story = await API.getUnitStory(serial);
      this.render(story);
    } catch (err) {
      container.innerHTML = `<div class="p-8 bg-slate-900 border border-slate-800 rounded-xl text-center text-rose-400 text-xs">${err.message}</div>`;
    }
  },

  render(story) {
    const container = document.getElementById("unit-story-container");
    if (!container) return;

    let statusBadge = "bg-emerald-950/60 text-emerald-300 border-emerald-800";
    if (story.qc_status === "DEFECTIVE") statusBadge = "bg-rose-950/60 text-rose-300 border-rose-800";

    container.innerHTML = `
      <!-- Unit Header & Identity -->
      <div class="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg flex flex-wrap items-center justify-between gap-4">
        <div class="flex items-center space-x-4">
          <div class="barcode-strip w-12 h-12 rounded border border-slate-700 flex items-center justify-center">
            <i class="fa-solid fa-qrcode text-black text-2xl"></i>
          </div>
          <div>
            <div class="flex items-center space-x-2">
              <h3 class="text-base font-bold text-white font-mono">${story.serial_number}</h3>
              <span class="px-2 py-0.5 rounded-full text-2xs font-bold border ${statusBadge}">${story.qc_status}</span>
            </div>
            <p class="text-xs text-slate-400">${story.product_name} (${story.product_sku}) • Order ${story.order_number}</p>
          </div>
        </div>

        <div class="flex items-center space-x-6 text-xs">
          <div>
            <span class="text-slate-400 text-2xs block">Fabricated On</span>
            <span class="text-cyan-300 font-bold font-mono">${story.machine.name} (${story.machine.id})</span>
          </div>
          <div>
            <span class="text-slate-400 text-2xs block">Operator</span>
            <span class="text-indigo-300 font-bold">${story.operator.name}</span>
          </div>
          <div>
            <span class="text-slate-400 text-2xs block">Cycle Time</span>
            <span class="text-slate-200 font-bold font-mono">${story.telemetry.cycle_time_sec}s</span>
          </div>
        </div>
      </div>

      <!-- 5-Stage Story Timeline -->
      <div class="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-lg space-y-4">
        <h4 class="text-sm font-bold text-white flex items-center space-x-2">
          <i class="fa-solid fa-timeline text-cyan-400"></i>
          <span>Unit Manufacturing Lifecycle Storyline</span>
        </h4>
        <p class="text-xs text-slate-400">Chronological digital thread detailing every human touchpoint, machine parameter, and quality gate.</p>

        <div class="mt-6 space-y-6">
          ${story.story_timeline.map(evt => {
            let nodeColor = "bg-emerald-500 border-emerald-950";
            if (evt.status === "WARN") nodeColor = "bg-amber-500 border-amber-950";
            if (evt.status === "FAIL" || evt.status === "ALERT") nodeColor = "bg-rose-500 border-rose-950";

            return `
              <div class="timeline-stem">
                <div class="timeline-node ${nodeColor}"></div>
                <div class="bg-slate-800/50 border border-slate-700/60 rounded-lg p-4 space-y-1 hover:border-slate-600 transition">
                  <div class="flex items-center justify-between text-xs">
                    <span class="font-bold text-white">${evt.title}</span>
                    <span class="font-mono text-slate-400 text-2xs">${evt.stage}</span>
                  </div>
                  <p class="text-xs text-slate-300 leading-relaxed">${evt.details}</p>
                </div>
              </div>
            `;
          }).join("")}
        </div>
      </div>

      <!-- Sensor Snapshot at Fabrication -->
      <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div class="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <span class="text-2xs text-slate-400 block">Vibration at Cut</span>
          <div class="text-base font-bold font-mono ${story.telemetry.vibration_mms > story.telemetry.vib_warning ? 'text-rose-400' : 'text-emerald-400'} mt-1">
            ${story.telemetry.vibration_mms} mm/s
          </div>
          <span class="text-2xs text-slate-500">Warning Limit: ${story.telemetry.vib_warning} mm/s</span>
        </div>

        <div class="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <span class="text-2xs text-slate-400 block">Core Temperature</span>
          <div class="text-base font-bold font-mono ${story.telemetry.temperature_c > story.telemetry.temp_warning ? 'text-rose-400' : 'text-blue-400'} mt-1">
            ${story.telemetry.temperature_c}°C
          </div>
          <span class="text-2xs text-slate-500">Trip Limit: ${story.telemetry.temp_critical}°C</span>
        </div>

        <div class="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <span class="text-2xs text-slate-400 block">Spindle Load</span>
          <div class="text-base font-bold font-mono text-indigo-400 mt-1">
            ${story.telemetry.spindle_load_pct}%
          </div>
          <span class="text-2xs text-slate-500">Nominal: 40-55%</span>
        </div>

        <div class="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <span class="text-2xs text-slate-400 block">Raw Material Heat Lot</span>
          <div class="text-base font-bold font-mono text-amber-400 mt-1">
            ${story.material.supplier_lot}
          </div>
          <span class="text-2xs text-slate-500">${story.material.supplier}</span>
        </div>
      </div>
    `;
  }
};

window.DigitalThread = DigitalThread;
