function isRecord(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

export function humanizeIdentifier(rawId) {
  return String(rawId || "")
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .toUpperCase();
}

export function normalizeReading(sensorId, payload) {
  if (isRecord(payload) && Object.prototype.hasOwnProperty.call(payload, "value")) {
    return {
      sensor_id: payload.sensor_id || sensorId,
      timestamp: payload.timestamp || null,
      confidence: payload.confidence ?? null,
      value: payload.value,
      metadata: isRecord(payload.metadata) ? payload.metadata : {},
    };
  }

  return {
    sensor_id: sensorId,
    timestamp: null,
    confidence: null,
    value: payload,
    metadata: {},
  };
}

export function formatTimestamp(rawValue) {
  if (!rawValue) {
    return "AWAITING DATA";
  }

  const parsed = new Date(rawValue);
  if (Number.isNaN(parsed.valueOf())) {
    return String(rawValue);
  }

  return parsed.toLocaleTimeString();
}

export function formatValue(value) {
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : value.toFixed(2);
  }
  if (typeof value === "boolean") {
    return value ? "TRUE" : "FALSE";
  }
  if (value === null || value === undefined) {
    return "N/A";
  }
  return String(value);
}

export function createElement(tagName, className, text) {
  const element = document.createElement(tagName);
  if (className) {
    element.className = className;
  }
  if (text !== undefined) {
    element.textContent = text;
  }
  return element;
}

export function createMetricList(metrics) {
  const dl = createElement("dl", "sensor-metrics", undefined);
  for (const metric of metrics) {
    const key = createElement("dt", "", metric.label);
    const value = createElement("dd", "", formatValue(metric.value));
    dl.append(key, value);
  }
  return dl;
}

export function createBars(entries, maxValue) {
  const rows = createElement("div", "bars", undefined);
  const safeEntries = Array.isArray(entries) ? entries : [];
  const largest = maxValue && maxValue > 0
    ? maxValue
    : Math.max(1, ...safeEntries.map((entry) => (typeof entry.value === "number" ? entry.value : 0)));

  for (const entry of safeEntries) {
    const value = typeof entry.value === "number" ? entry.value : 0;
    const percentage = Math.max(0, Math.min(100, (value / largest) * 100));

    const row = createElement("div", "bar-row", undefined);
    const label = createElement("span", "bar-label", String(entry.label));
    const track = createElement("span", "bar-track", undefined);
    const fill = createElement("span", "bar-fill", undefined);
    fill.style.width = `${percentage.toFixed(1)}%`;
    track.appendChild(fill);
    const numeric = createElement("span", "bar-value", formatValue(value));

    row.append(label, track, numeric);
    rows.appendChild(row);
  }

  return rows;
}

export function normalizeColorClass(colorName) {
  const normalized = String(colorName || "golden-tanoi")
    .toLowerCase()
    .replace(/[^a-z0-9-]/g, "");
  return `lcars-${normalized}-bg`;
}

export function asRecord(value) {
  return isRecord(value) ? value : {};
}
