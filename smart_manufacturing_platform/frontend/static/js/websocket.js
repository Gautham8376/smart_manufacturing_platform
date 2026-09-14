/**
 * AERO-MES 4.0 - WebSocket Manager & Event Bus
 * Handles persistent bi-directional communication with server and event dispatching.
 */

const WSManager = {
  socket: null,
  listeners: {},
  reconnectTimer: null,

  init() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws/factory`;

    this.socket = new WebSocket(wsUrl);

    this.socket.onopen = () => {
      this.updateIndicator(true);
      console.log("[WS] Connected to Factory Stream");
    };

    this.socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        this.emit(payload.event || "MESSAGE", payload);
      } catch (err) {
        console.error("[WS] Message parsing error:", err);
      }
    };

    this.socket.onclose = () => {
      this.updateIndicator(false);
      console.warn("[WS] Connection lost. Reconnecting in 2.5s...");
      if (!this.reconnectTimer) {
        this.reconnectTimer = setTimeout(() => {
          this.reconnectTimer = null;
          this.init();
        }, 2500);
      }
    };

    this.socket.onerror = (err) => {
      console.error("[WS] Error observed:", err);
    };
  },

  on(eventName, callback) {
    if (!this.listeners[eventName]) {
      this.listeners[eventName] = [];
    }
    this.listeners[eventName].push(callback);
  },

  emit(eventName, data) {
    if (this.listeners[eventName]) {
      this.listeners[eventName].forEach(cb => {
        try {
          cb(data);
        } catch (e) {
          console.error(`[WS] Error in handler for '${eventName}':`, e);
        }
      });
    }
    // Also emit to universal wildcard listener
    if (this.listeners["*"]) {
      this.listeners["*"].forEach(cb => cb(eventName, data));
    }
  },

  updateIndicator(isConnected) {
    const indicator = document.getElementById("ws-indicator");
    const statusText = document.getElementById("ws-status-text");
    if (!indicator || !statusText) return;

    if (isConnected) {
      indicator.className = "w-2 h-2 rounded-full bg-emerald-400";
      statusText.innerText = "Live";
    } else {
      indicator.className = "w-2 h-2 rounded-full bg-rose-500 animate-ping";
      statusText.innerText = "Reconnecting...";
    }
  }
};

window.WSManager = WSManager;
