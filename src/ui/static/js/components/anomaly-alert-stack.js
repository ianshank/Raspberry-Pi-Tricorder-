import { createElement, formatTimestamp, humanizeIdentifier } from "./render-utils.js";

const DEFAULT_LIMIT = 6;
const DEFAULT_ANOMALY_ACK_PATH = "/ui/anomalies/ack";

function asNumber(value) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function alertScoreLabel(score) {
  const numeric = asNumber(score);
  return numeric === null ? "N/A" : numeric.toFixed(3);
}

function normalizeSeverity(payload) {
  const rawSeverity = payload && payload.severity ? payload.severity : "LOW";
  return String(rawSeverity).toUpperCase();
}

function normalizeAckPath(rawPath) {
  const candidate = String(rawPath || DEFAULT_ANOMALY_ACK_PATH);
  return candidate.startsWith("/") ? candidate : DEFAULT_ANOMALY_ACK_PATH;
}

function affectedSensors(payload) {
  if (!payload || typeof payload !== "object") {
    return [];
  }

  if (Array.isArray(payload.affected_sensors)) {
    return payload.affected_sensors.map((sensorId) => humanizeIdentifier(sensorId));
  }

  const context = payload.context;
  if (!context || typeof context !== "object") {
    return [];
  }

  const sensors = context.sensors;
  if (!Array.isArray(sensors)) {
    return [];
  }

  return sensors.map((sensorId) => humanizeIdentifier(sensorId));
}

export class AnomalyAlertStack {
  constructor(uiConfig = {}, limit = DEFAULT_LIMIT) {
    this.uiConfig = uiConfig || {};
    const configuredLimit = Number(this.uiConfig.anomaly_history_limit);
    this.limit = Number.isFinite(configuredLimit) && configuredLimit > 0
      ? Math.round(configuredLimit)
      : limit;
    this.ackEnabled = this.uiConfig.anomaly_ack_enabled !== false;
    this.ackPath = normalizeAckPath(this.uiConfig.anomaly_ack_path);

    this.root = null;
    this.cardsByAnomalyId = new Map();
  }

  mount(container) {
    this.root = container;
  }

  push(payload) {
    if (!this.root) {
      return;
    }
    if (!payload || typeof payload !== "object") {
      return;
    }

    const severity = normalizeSeverity(payload);
    const isAnomaly = Boolean(payload.is_anomaly);
    if (!isAnomaly) {
      return;
    }

    const anomalyId = typeof payload.anomaly_id === "string" ? payload.anomaly_id.trim() : "";
    if (anomalyId && this.cardsByAnomalyId.has(anomalyId)) {
      this._setAcknowledgedState(
        this.cardsByAnomalyId.get(anomalyId),
        payload,
      );
      return;
    }

    const card = createElement(
      "article",
      `anomaly-alert-card severity-${severity.toLowerCase()}`,
      undefined,
    );
    if (anomalyId) {
      card.dataset.anomalyId = anomalyId;
    }

    const heading = createElement(
      "h3",
      "anomaly-alert-title",
      `${severity} ALERT  SCORE ${alertScoreLabel(payload.anomaly_score)}`,
    );
    const timestamp = createElement(
      "p",
      "anomaly-alert-time",
      formatTimestamp(payload.timestamp),
    );

    card.append(heading, timestamp);

    const sensors = affectedSensors(payload);
    if (sensors.length > 0) {
      card.appendChild(createElement("p", "anomaly-alert-sensors", sensors.join("  |  ")));
    }

    if (this.ackEnabled) {
      const controls = createElement("div", "anomaly-alert-controls", undefined);
      const ackButton = createElement("button", "anomaly-alert-ack", "ACK");
      ackButton.type = "button";
      ackButton.disabled = !anomalyId;
      ackButton.addEventListener("click", () => {
        void this._acknowledgeAnomaly(payload, card, ackButton);
      });
      controls.appendChild(ackButton);
      card.appendChild(controls);
    }

    this._setAcknowledgedState(card, payload);

    this.root.prepend(card);
    if (anomalyId) {
      this.cardsByAnomalyId.set(anomalyId, card);
    }

    while (this.root.children.length > this.limit) {
      const removed = this.root.lastElementChild;
      if (!removed) {
        break;
      }
      if (removed.dataset && removed.dataset.anomalyId) {
        this.cardsByAnomalyId.delete(removed.dataset.anomalyId);
      }
      this.root.removeChild(removed);
    }
  }

  _setAcknowledgedState(card, payload) {
    if (!card || !payload || typeof payload !== "object") {
      return;
    }

    const isAcknowledged = Boolean(payload.acknowledged);
    card.classList.toggle("is-acknowledged", isAcknowledged);

    const ackButton = card.querySelector(".anomaly-alert-ack");
    if (!ackButton) {
      return;
    }

    if (isAcknowledged) {
      ackButton.disabled = true;
      ackButton.textContent = "ACKNOWLEDGED";
      return;
    }

    if (!ackButton.textContent || ackButton.textContent === "ACKNOWLEDGED") {
      ackButton.textContent = "ACK";
    }
    if (!card.dataset.anomalyId) {
      ackButton.disabled = true;
    }
  }

  async _acknowledgeAnomaly(payload, card, button) {
    if (!this.ackEnabled || !button) {
      return;
    }

    const anomalyId = typeof payload?.anomaly_id === "string"
      ? payload.anomaly_id.trim()
      : "";
    if (!anomalyId) {
      button.disabled = true;
      button.textContent = "NO ID";
      return;
    }

    button.disabled = true;
    button.textContent = "...";

    try {
      const response = await fetch(this.ackPath, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          anomaly_id: anomalyId,
          acknowledged_by: "ui",
        }),
      });
      const data = await response.json();
      if (!response.ok) {
        const detail = data && data.detail ? data.detail : `HTTP ${response.status}`;
        throw new Error(String(detail));
      }

      payload.acknowledged = true;
      if (data && data.acknowledgment) {
        payload.acknowledgment = data.acknowledgment;
      }
      this._setAcknowledgedState(card, payload);
    } catch {
      button.disabled = false;
      button.textContent = "RETRY ACK";
    }
  }
}
