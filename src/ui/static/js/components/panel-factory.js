import { BasePanel } from "./base-panel.js";
import { AgentChatPanel } from "./agent-chat-panel.js";
import { AnomalyHistoryPanel } from "./anomaly-history-panel.js";
import { BioPanel } from "./bio-panel.js";
import { EngPanel } from "./eng-panel.js";
import { EnvPanel } from "./env-panel.js";

export function createPanelComponent(panelId, panelConfig, sensorCatalog, uiConfig = {}) {
  const key = String(panelId || "").toLowerCase();

  if (key.includes("history") || key.includes("anomaly-history")) {
    return new AnomalyHistoryPanel(panelId, panelConfig, sensorCatalog, uiConfig);
  }

  if (key.includes("agent") || key.includes("chat") || key.includes("library")) {
    return new AgentChatPanel(panelId, panelConfig, sensorCatalog, uiConfig);
  }

  if (key.includes("bio")) {
    return new BioPanel(panelId, panelConfig, sensorCatalog, uiConfig);
  }
  if (key.includes("env") || key.includes("atmos")) {
    return new EnvPanel(panelId, panelConfig, sensorCatalog, uiConfig);
  }
  if (key.includes("eng") || key.includes("spatial")) {
    return new EngPanel(panelId, panelConfig, sensorCatalog, uiConfig);
  }

  return new BasePanel(panelId, panelConfig, sensorCatalog, uiConfig);
}
