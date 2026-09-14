/**
 * AERO-MES 4.0 - Interactive Scenarios Module
 * Triggers pre-engineered operational scenarios and coordinates UI transitions.
 */

const Scenarios = {
  async trigger(name) {
    try {
      const res = await API.triggerScenario(name);

      if (window.App) window.App.refresh();

      if (name === "prompt_freeze") {
        window.App.switchTab("tab-twin");
        alert("Prompt Scenario Triggered!\n- Material LOT-RESIN-204 placed ON HOLD\n- Machine INJ-03 is ready\n- Operator OP-103 is waiting\n- Overdue order WO-9013 surfaced\n- Competing run RUN-2026-004 booking BLOCKED");
      } else if (name === "spindle_drift") {
        window.App.switchTab("tab-early-warning");
        alert("Spindle Drift Initiated on CNC-01! Watch the Early Warning Radar detect trend slope before trip threshold.");
      } else if (name === "genealogy_recall") {
        window.App.switchTab("tab-rca");
        RCAStudio.execute();
      } else if (name === "reset") {
        window.App.switchTab("tab-twin");
        alert("Factory baseline restored cleanly.");
      }
    } catch (err) {
      alert("Failed to trigger scenario: " + err.message);
    }
  }
};

window.Scenarios = Scenarios;
