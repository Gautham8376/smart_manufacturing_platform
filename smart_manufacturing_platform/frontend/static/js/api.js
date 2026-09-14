/**
 * AERO-MES 4.0 - API Client Layer
 * Handles all REST API communications with the FastAPI backend.
 */

const API = {
  // Factory Status & Overview
  async getStatus() {
    const res = await fetch("/api/status");
    if (!res.ok) throw new Error(`Failed to fetch factory status (${res.status})`);
    return await res.json();
  },

  // Machines
  async getMachines() {
    const res = await fetch("/api/machines");
    if (!res.ok) throw new Error(`Failed to fetch machines (${res.status})`);
    return await res.json();
  },

  // Materials & Quality Holds
  async getMaterials() {
    const res = await fetch("/api/materials");
    if (!res.ok) throw new Error(`Failed to fetch materials (${res.status})`);
    return await res.json();
  },

  async setMaterialHold(lotId, holdReason) {
    const res = await fetch("/api/materials/hold", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lot_id: lotId, hold_reason: holdReason })
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Failed to set material hold");
    }
    return await res.json();
  },

  async releaseMaterialHold(lotId) {
    const res = await fetch("/api/materials/release", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lot_id: lotId })
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Failed to release material hold");
    }
    return await res.json();
  },

  // Operators
  async getOperators() {
    const res = await fetch("/api/operators");
    if (!res.ok) throw new Error(`Failed to fetch operators (${res.status})`);
    return await res.json();
  },

  // Production Runs & Anti-Collision Dispatch
  async getRuns() {
    const res = await fetch("/api/runs");
    if (!res.ok) throw new Error(`Failed to fetch runs (${res.status})`);
    return await res.json();
  },

  async createRun(payload) {
    const res = await fetch("/api/runs/create", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Failed to create work order");
    }
    return await res.json();
  },

  async dispatchRun(payload) {
    const res = await fetch("/api/runs/dispatch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    return {
      status: res.status,
      ok: res.ok,
      data: data
    };
  },

  async completeRun(runId) {
    const res = await fetch(`/api/runs/${runId}/complete`, { method: "POST" });
    if (!res.ok) throw new Error(`Failed to complete run ${runId}`);
    return await res.json();
  },

  async abortRun(runId) {
    const res = await fetch(`/api/runs/${runId}/abort`, { method: "POST" });
    if (!res.ok) throw new Error(`Failed to abort run ${runId}`);
    return await res.json();
  },

  // Locks & Alerts
  async getLocks() {
    const res = await fetch("/api/locks");
    if (!res.ok) throw new Error(`Failed to fetch locks (${res.status})`);
    return await res.json();
  },

  async getAlerts() {
    const res = await fetch("/api/alerts");
    if (!res.ok) throw new Error(`Failed to fetch alerts (${res.status})`);
    return await res.json();
  },

  async resolveAlert(alertId) {
    const res = await fetch(`/api/alerts/${alertId}/resolve`, { method: "POST" });
    if (!res.ok) throw new Error(`Failed to resolve alert ${alertId}`);
    return await res.json();
  },

  // Digital Thread & RCA
  async getUnitStory(serialNumber) {
    const res = await fetch(`/api/trace/unit/${serialNumber}`);
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || `Unit ${serialNumber} not found`);
    }
    return await res.json();
  },

  async traceMaterial(lotId) {
    const res = await fetch(`/api/trace/material/${lotId}`);
    if (!res.ok) throw new Error(`Failed to trace material lot ${lotId}`);
    return await res.json();
  },

  async executeRCA(payload = {}) {
    const res = await fetch("/api/trace/rca", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (!res.ok) throw new Error("Failed to execute root-cause analysis");
    return await res.json();
  },

  // Telemetry History for SPC
  async getTelemetryHistory(machineId = "CNC-01") {
    const res = await fetch(`/api/telemetry/history?machine_id=${machineId}`);
    if (!res.ok) throw new Error(`Failed to fetch telemetry history for ${machineId}`);
    return await res.json();
  },

  // Simulator & Scenarios
  async toggleSimulator(running, speed) {
    const body = {};
    if (running !== undefined) body.running = running;
    if (speed !== undefined) body.speed = speed;
    const res = await fetch("/api/simulator/toggle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });
    if (!res.ok) throw new Error("Failed to toggle simulator");
    return await res.json();
  },

  async triggerScenario(scenarioName) {
    const res = await fetch("/api/simulator/scenario", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scenario_name: scenarioName })
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Failed to trigger scenario");
    }
    return await res.json();
  }
};

window.API = API;
