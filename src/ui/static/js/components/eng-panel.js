import { BasePanel } from "./base-panel.js";
import { asRecord, createBars, createMetricList } from "./render-utils.js";

function numericOrNA(value) {
  return typeof value === "number" && Number.isFinite(value) ? value : "N/A";
}

export class EngPanel extends BasePanel {
  renderSensor(sensorId, reading, cardBody) {
    cardBody.innerHTML = "";
    const value = asRecord(reading.value);

    if (sensorId.includes("hlk_ld2410")) {
      cardBody.appendChild(
        createMetricList([
          { label: "TARGET", value: value.target_state || "unknown" },
          { label: "MOVING ENERGY", value: numericOrNA(value.moving_target_energy) },
          { label: "STILL ENERGY", value: numericOrNA(value.stationary_target_energy) },
        ]),
      );

      const ranges = [
        { label: "MOV", value: typeof value.moving_target_distance_cm === "number" ? value.moving_target_distance_cm : 0 },
        { label: "STILL", value: typeof value.stationary_target_distance_cm === "number" ? value.stationary_target_distance_cm : 0 },
        { label: "DETECT", value: typeof value.detection_distance_cm === "number" ? value.detection_distance_cm : 0 },
      ];
      cardBody.appendChild(createBars(ranges, Math.max(...ranges.map((entry) => entry.value), 1)));
      return;
    }

    if (sensorId.includes("tfmini")) {
      const distance = typeof value.distance_cm === "number" ? value.distance_cm : 0;
      const signal = typeof value.signal_strength === "number" ? value.signal_strength : 0;
      const maxRange = typeof value.max_range_cm === "number" && value.max_range_cm > 0
        ? value.max_range_cm
        : Math.max(distance, 1);

      cardBody.appendChild(
        createMetricList([
          { label: "DISTANCE CM", value: numericOrNA(value.distance_cm) },
          { label: "SIGNAL", value: numericOrNA(value.signal_strength) },
          { label: "TEMPERATURE C", value: numericOrNA(value.temperature_c) },
          { label: "VALID", value: value.valid === false ? "FALSE" : "TRUE" },
        ]),
      );

      cardBody.appendChild(
        createBars(
          [
            { label: "RANGE", value: distance },
            { label: "SIGNAL", value: signal },
          ],
          Math.max(maxRange, signal, 1),
        ),
      );
      return;
    }

    super.renderSensor(sensorId, reading, cardBody);
  }
}
