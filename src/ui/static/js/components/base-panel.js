import {
  asRecord,
  createElement,
  formatTimestamp,
  humanizeIdentifier,
  normalizeColorClass,
  normalizeReading,
} from "./render-utils.js";

export class BasePanel {
  constructor(panelId, panelConfig, sensorCatalog, uiConfig = {}) {
    this.panelId = panelId;
    this.panelConfig = panelConfig || {};
    this.sensorCatalog = sensorCatalog || {};
    this.uiConfig = uiConfig || {};
    this.sensorCards = new Map();
    this.root = null;
  }

  mount(container) {
    this.root = createElement("section", "panel-root", undefined);
    this.root.id = `panel-${this.panelId}`;

    const title = createElement(
      "h2",
      "panel-title",
      this.panelConfig.label || humanizeIdentifier(this.panelId),
    );
    this.root.appendChild(title);

    const sensors = Array.isArray(this.panelConfig.sensors)
      ? this.panelConfig.sensors
      : [];

    if (sensors.length === 0) {
      const empty = createElement("p", "", "No sensors configured for this panel.");
      this.root.appendChild(empty);
    }

    for (const rawSensorId of sensors) {
      const sensorId = String(rawSensorId);
      this.root.appendChild(this._createSensorCard(sensorId));
    }

    container.appendChild(this.root);
    return this.root;
  }

  setActive(isActive) {
    if (!this.root) {
      return;
    }
    this.root.classList.toggle("is-active", Boolean(isActive));
  }

  update(readings) {
    const safeReadings = asRecord(readings);
    for (const [sensorId, refs] of this.sensorCards.entries()) {
      const normalized = normalizeReading(sensorId, safeReadings[sensorId]);
      refs.timestamp.textContent = formatTimestamp(normalized.timestamp);
      this.renderSensor(sensorId, normalized, refs.body);
    }
  }

  renderSensor(sensorId, reading, cardBody) {
    cardBody.innerHTML = "";
    const block = createElement("pre", "raw-json", JSON.stringify(reading.value, null, 2));
    cardBody.appendChild(block);
  }

  _createSensorCard(sensorId) {
    const sensorMeta = this.sensorCatalog[sensorId] || {};
    const displayName = sensorMeta.label || humanizeIdentifier(sensorId);

    const card = createElement("article", "sensor-card", undefined);
    const header = createElement("header", "sensor-card-header", undefined);
    header.classList.add(normalizeColorClass(this.panelConfig.color));

    const title = createElement("span", "", displayName);
    const timestamp = createElement("span", "timestamp", "AWAITING DATA");
    header.append(title, timestamp);

    const body = createElement("div", "sensor-card-body", undefined);
    card.append(header, body);

    this.sensorCards.set(sensorId, {
      body,
      timestamp,
    });

    return card;
  }
}
