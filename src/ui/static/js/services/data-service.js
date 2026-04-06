const DEFAULT_WS_PATH = "/ws/sensors";
const DEFAULT_ANOMALY_WS_PATH = "/ws/anomalies";
const DEFAULT_RECONNECT_INITIAL_MS = 1500;
const DEFAULT_RECONNECT_MAX_MS = 10000;

function toPositiveNumber(value, fallback) {
  const candidate = Number(value);
  return Number.isFinite(candidate) && candidate > 0 ? candidate : fallback;
}

export class DataService {
  constructor(uiConfig) {
    this.uiConfig = uiConfig || {};
    this.socket = null;
    this.anomalySocket = null;

    this.isManualClose = false;
    this.isAnomalyManualClose = false;

    this.reconnectDelayMs = toPositiveNumber(
      this.uiConfig.reconnect_initial_ms,
      DEFAULT_RECONNECT_INITIAL_MS,
    );
    this.anomalyReconnectDelayMs = toPositiveNumber(
      this.uiConfig.reconnect_initial_ms,
      DEFAULT_RECONNECT_INITIAL_MS,
    );
    this.reconnectMaxMs = toPositiveNumber(
      this.uiConfig.reconnect_max_ms,
      DEFAULT_RECONNECT_MAX_MS,
    );

    this.statusListeners = new Set();
    this.anomalyStatusListeners = new Set();
    this.readingListeners = new Set();
    this.anomalyListeners = new Set();
    this.sensorListeners = new Map();
  }

  connect() {
    this.isManualClose = false;
    this._openSensorSocket();
  }

  connectAnomalies() {
    this.isAnomalyManualClose = false;
    this._openAnomalySocket();
  }

  disconnect() {
    this.isManualClose = true;
    if (this.socket) {
      this.socket.close();
    }
  }

  disconnectAnomalies() {
    this.isAnomalyManualClose = true;
    if (this.anomalySocket) {
      this.anomalySocket.close();
    }
  }

  subscribeStatus(listener) {
    this.statusListeners.add(listener);
    return () => this.statusListeners.delete(listener);
  }

  subscribeReadings(listener) {
    this.readingListeners.add(listener);
    return () => this.readingListeners.delete(listener);
  }

  subscribeAnomalies(listener) {
    this.anomalyListeners.add(listener);
    return () => this.anomalyListeners.delete(listener);
  }

  subscribeAnomalyStatus(listener) {
    this.anomalyStatusListeners.add(listener);
    return () => this.anomalyStatusListeners.delete(listener);
  }

  subscribeSensor(sensorId, listener) {
    const key = String(sensorId);
    if (!this.sensorListeners.has(key)) {
      this.sensorListeners.set(key, new Set());
    }
    this.sensorListeners.get(key).add(listener);
    return () => {
      const listeners = this.sensorListeners.get(key);
      if (!listeners) {
        return;
      }
      listeners.delete(listener);
      if (listeners.size === 0) {
        this.sensorListeners.delete(key);
      }
    };
  }

  _buildWsUrl(path, fallbackPath) {
    const wsPath = this._resolveWsPath(path, fallbackPath);
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    return `${protocol}://${window.location.host}${wsPath}`;
  }

  _openSensorSocket() {
    const wsUrl = this._buildWsUrl(this.uiConfig.ws_path, DEFAULT_WS_PATH);

    this._emitStatus("CONNECTING");
    this.socket = new WebSocket(wsUrl);

    this.socket.addEventListener("open", () => {
      this.reconnectDelayMs = toPositiveNumber(
        this.uiConfig.reconnect_initial_ms,
        DEFAULT_RECONNECT_INITIAL_MS,
      );
      this._emitStatus("CONNECTED");
    });

    this.socket.addEventListener("message", (event) => {
      this._handleMessage(event.data);
    });

    this.socket.addEventListener("close", () => {
      this._emitStatus("DISCONNECTED");
      if (!this.isManualClose) {
        this._scheduleSensorReconnect();
      }
    });

    this.socket.addEventListener("error", () => {
      this._emitStatus("ERROR");
    });
  }

  _openAnomalySocket() {
    const wsUrl = this._buildWsUrl(this.uiConfig.anomaly_ws_path, DEFAULT_ANOMALY_WS_PATH);

    this._emitAnomalyStatus("CONNECTING");
    this.anomalySocket = new WebSocket(wsUrl);

    this.anomalySocket.addEventListener("open", () => {
      this.anomalyReconnectDelayMs = toPositiveNumber(
        this.uiConfig.reconnect_initial_ms,
        DEFAULT_RECONNECT_INITIAL_MS,
      );
      this._emitAnomalyStatus("CONNECTED");
    });

    this.anomalySocket.addEventListener("message", (event) => {
      this._handleAnomalyMessage(event.data);
    });

    this.anomalySocket.addEventListener("close", () => {
      this._emitAnomalyStatus("DISCONNECTED");
      if (!this.isAnomalyManualClose) {
        this._scheduleAnomalyReconnect();
      }
    });

    this.anomalySocket.addEventListener("error", () => {
      this._emitAnomalyStatus("ERROR");
    });
  }

  _resolveWsPath(configuredPath, fallbackPath) {
    const candidate = String(configuredPath || fallbackPath);
    return candidate.startsWith("/") ? candidate : fallbackPath;
  }

  _scheduleSensorReconnect() {
    const waitMs = this.reconnectDelayMs;
    this._emitStatus(`RECONNECTING IN ${waitMs}MS`);

    window.setTimeout(() => {
      if (this.isManualClose) {
        return;
      }
      this._openSensorSocket();
      this.reconnectDelayMs = Math.min(waitMs * 2, this.reconnectMaxMs);
    }, waitMs);
  }

  _scheduleAnomalyReconnect() {
    const waitMs = this.anomalyReconnectDelayMs;
    this._emitAnomalyStatus(`RECONNECTING IN ${waitMs}MS`);

    window.setTimeout(() => {
      if (this.isAnomalyManualClose) {
        return;
      }
      this._openAnomalySocket();
      this.anomalyReconnectDelayMs = Math.min(waitMs * 2, this.reconnectMaxMs);
    }, waitMs);
  }

  _emitStatus(status) {
    for (const listener of this.statusListeners) {
      listener(status);
    }
  }

  _emitAnomalyStatus(status) {
    for (const listener of this.anomalyStatusListeners) {
      listener(status);
    }
  }

  _emitAnomaly(payload) {
    for (const listener of this.anomalyListeners) {
      listener(payload);
    }
  }

  _parseJson(rawData, fallback) {
    try {
      return JSON.parse(rawData);
    } catch {
      return fallback;
    }
  }

  _handleMessage(rawData) {
    const payload = this._parseJson(rawData, { timestamp: null, readings: {}, raw: rawData });

    for (const listener of this.readingListeners) {
      listener(payload);
    }

    const readings = payload && typeof payload === "object" ? payload.readings : null;
    if (!readings || typeof readings !== "object") {
      return;
    }

    for (const [sensorId, sensorPayload] of Object.entries(readings)) {
      const listeners = this.sensorListeners.get(sensorId);
      if (!listeners) {
        continue;
      }
      for (const listener of listeners) {
        listener(sensorPayload, payload);
      }
    }
  }

  _handleAnomalyMessage(rawData) {
    const payload = this._parseJson(rawData, { timestamp: null, is_anomaly: false, raw: rawData });
    this._emitAnomaly(payload);
  }
}
