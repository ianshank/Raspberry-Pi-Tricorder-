import { BasePanel } from "./base-panel.js";
import { asRecord, createBars, createMetricList } from "./render-utils.js";

function numericOrNA(value) {
  return typeof value === "number" && Number.isFinite(value) ? value : "N/A";
}

export class EnvPanel extends BasePanel {
  renderSensor(sensorId, reading, cardBody) {
    cardBody.innerHTML = "";
    const value = asRecord(reading.value);

    if (sensorId.includes("bme680")) {
      cardBody.appendChild(
        createMetricList([
          { label: "TEMP C", value: numericOrNA(value.temperature_c) },
          { label: "HUMIDITY", value: numericOrNA(value.humidity_rh) },
          { label: "PRESSURE", value: numericOrNA(value.pressure_hpa) },
          { label: "VOC OHM", value: numericOrNA(value.gas_resistance_ohm) },
        ]),
      );
      return;
    }

    if (sensorId.includes("as7265x")) {
      const spectralChannels = asRecord(value.spectral_channels);
      const entries = Object.entries(spectralChannels)
        .filter(([, channelValue]) => typeof channelValue === "number")
        .sort((a, b) => b[1] - a[1])
        .slice(0, 10)
        .map(([label, channelValue]) => ({ label, value: channelValue }));

      if (entries.length > 0) {
        const maxValue = Math.max(...entries.map((entry) => entry.value), 1);
        cardBody.appendChild(createBars(entries, maxValue));
      } else {
        cardBody.appendChild(createMetricList([{ label: "SPECTRAL", value: "NO DATA" }]));
      }
      return;
    }

    if (sensorId.includes("ads1263")) {
      const channels = asRecord(value.channels);
      const entries = Object.entries(channels)
        .filter(([, channelValue]) => typeof channelValue === "number")
        .map(([label, channelValue]) => ({ label, value: channelValue }));

      if (entries.length > 0) {
        const maxValue = Math.max(...entries.map((entry) => Math.abs(entry.value)), 0.001);
        cardBody.appendChild(createBars(entries, maxValue));
      } else {
        cardBody.appendChild(createMetricList([{ label: "ADC", value: "NO CHANNEL DATA" }]));
      }
      return;
    }

    super.renderSensor(sensorId, reading, cardBody);
  }
}
