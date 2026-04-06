import { BasePanel } from "./base-panel.js";
import { asRecord, createBars, createMetricList, createElement, formatValue } from "./render-utils.js";

function toNumber(value) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export class BioPanel extends BasePanel {
  renderSensor(sensorId, reading, cardBody) {
    cardBody.innerHTML = "";
    const value = asRecord(reading.value);

    if (sensorId.includes("max30102")) {
      const vitals = [
        { label: "HEART RATE", value: toNumber(value.heart_rate_bpm) ?? "N/A" },
        { label: "SPO2", value: toNumber(value.spo2_percent) ?? "N/A" },
        { label: "SIGNAL", value: toNumber(value.ir_avg) ?? "N/A" },
      ];
      cardBody.appendChild(createMetricList(vitals));
      return;
    }

    if (sensorId.includes("mlx90640")) {
      const summary = [
        { label: "MIN TEMP", value: toNumber(value.min_temp_c) ?? "N/A" },
        { label: "AVG TEMP", value: toNumber(value.avg_temp_c) ?? "N/A" },
        { label: "MAX TEMP", value: toNumber(value.max_temp_c) ?? "N/A" },
      ];
      cardBody.appendChild(createMetricList(summary));

      const frame = Array.isArray(value.thermal_frame) ? value.thermal_frame : [];
      const sampled = frame.slice(0, 12).map((entry, idx) => ({
        label: `P${idx + 1}`,
        value: typeof entry === "number" ? entry : 0,
      }));

      if (sampled.length > 0) {
        const maxTemp = Math.max(...sampled.map((item) => item.value), 1);
        cardBody.appendChild(createBars(sampled, maxTemp));
      } else {
        cardBody.appendChild(createElement("p", "", `THERMAL FRAME: ${formatValue(frame.length)} VALUES`));
      }
      return;
    }

    super.renderSensor(sensorId, reading, cardBody);
  }
}
