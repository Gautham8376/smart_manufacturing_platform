/**
 * AERO-MES 4.0 - Statistical Process Control (SPC) Chart Module
 * Plots real-time vibration and temperature telemetry against threshold limits.
 */

const SPCChart = {
  chart: null,
  selectedMachine: "CNC-01",

  init() {
    const canvas = document.getElementById("spc-telemetry-chart");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");

    this.chart = new Chart(ctx, {
      type: "line",
      data: {
        labels: [],
        datasets: [
          {
            label: "Spindle Vibration (mm/s)",
            data: [],
            borderColor: "#06b6d4",
            backgroundColor: "rgba(6, 182, 212, 0.1)",
            borderWidth: 2,
            tension: 0.25,
            yAxisID: "yVib"
          },
          {
            label: "Core Temperature (°C)",
            data: [],
            borderColor: "#3b82f6",
            backgroundColor: "rgba(59, 130, 246, 0.1)",
            borderWidth: 2,
            tension: 0.25,
            yAxisID: "yTemp"
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: {
            grid: { color: "rgba(51, 65, 85, 0.4)" },
            ticks: { color: "#94a3b8", font: { size: 10 } }
          },
          yVib: {
            type: "linear",
            position: "left",
            min: 0,
            max: 8,
            grid: { color: "rgba(51, 65, 85, 0.4)" },
            ticks: { color: "#06b6d4", font: { size: 10 } }
          },
          yTemp: {
            type: "linear",
            position: "right",
            min: 20,
            max: 100,
            grid: { drawOnChartArea: false },
            ticks: { color: "#3b82f6", font: { size: 10 } }
          }
        },
        plugins: {
          legend: {
            labels: { color: "#cbd5e1", font: { size: 11 } }
          }
        }
      }
    });

    this.updateData();
  },

  async selectMachine(machId) {
    this.selectedMachine = machId;
    await this.updateData();
  },

  async updateData() {
    if (!this.chart) return;
    try {
      const history = await API.getTelemetryHistory(this.selectedMachine);
      this.chart.data.labels = history.map(h => h.timestamp.split("T")[1].slice(0, 8));
      this.chart.data.datasets[0].data = history.map(h => h.vibration_mms);
      this.chart.data.datasets[1].data = history.map(h => h.temperature_c);
      this.chart.update("none");
    } catch (err) {
      console.error("[SPCChart] Update error:", err);
    }
  }
};

window.SPCChart = SPCChart;
