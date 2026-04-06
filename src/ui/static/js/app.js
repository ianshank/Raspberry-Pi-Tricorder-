import { AnomalyAlertStack } from "./components/anomaly-alert-stack.js";
import { createPanelComponent } from "./components/panel-factory.js";
import { humanizeIdentifier, normalizeColorClass } from "./components/render-utils.js";
import { DataService } from "./services/data-service.js";

const navRoot = document.querySelector("#panel-nav");
const panelHost = document.querySelector("#panel-host");
const alertRoot = document.querySelector("#alert-stack");
const modeTitle = document.querySelector("#mode-title");
const statusIndicator = document.querySelector("#status-indicator");
const stardate = document.querySelector("#stardate");
const appTitle = document.querySelector("#app-title");

const panelInstances = new Map();

function uiConfigUrl() {
  return new URL("./config.json", window.location.href).toString();
}

async function fetchUiConfig() {
  const response = await fetch(uiConfigUrl());
  if (!response.ok) {
    throw new Error(`Unable to fetch UI config (${response.status})`);
  }
  return response.json();
}

function orderedPanelKeys(uiConfig) {
  const panels = uiConfig?.panels && typeof uiConfig.panels === "object" ? uiConfig.panels : {};
  const available = Object.keys(panels);
  const ordered = Array.isArray(uiConfig.panel_order)
    ? uiConfig.panel_order.filter((key) => available.includes(key))
    : [];
  return ordered.length > 0 ? ordered : available;
}

function statusClassFor(state) {
  const normalized = String(state || "").toUpperCase();
  if (normalized.includes("CONNECTED")) {
    return "status-ok";
  }
  if (normalized.includes("ERROR") || normalized.includes("DISCONNECTED")) {
    return "status-error";
  }
  return "status-waiting";
}

function setStatus(state) {
  if (!statusIndicator) {
    return;
  }
  statusIndicator.textContent = String(state || "WAITING");
  statusIndicator.classList.remove("status-ok", "status-error", "status-waiting");
  statusIndicator.classList.add(statusClassFor(state));
}

function renderClock() {
  if (!stardate) {
    return;
  }
  const now = new Date();
  stardate.textContent = `UTC ${now.toISOString().replace("T", " ").slice(0, 19)}`;
}

function activatePanel(panelId, label) {
  for (const [instanceId, panel] of panelInstances.entries()) {
    panel.setActive(instanceId === panelId);
  }

  for (const button of navRoot?.querySelectorAll(".panel-nav-button") || []) {
    button.classList.toggle("is-active", button.dataset.panelId === panelId);
  }

  if (modeTitle) {
    modeTitle.textContent = label;
  }
}

function buildNavigation(uiConfig, panelKeys) {
  if (!navRoot) {
    return;
  }
  navRoot.innerHTML = "";

  for (const panelId of panelKeys) {
    const panelConfig = uiConfig.panels[panelId] || {};
    const colorClass = normalizeColorClass(panelConfig.color);
    const label = panelConfig.label || humanizeIdentifier(panelId);

    const button = document.createElement("button");
    button.type = "button";
    button.dataset.panelId = panelId;
    button.className = `lcars-element button right-rounded panel-nav-button ${colorClass}`;
    button.textContent = label;
    button.addEventListener("click", () => activatePanel(panelId, label));
    navRoot.appendChild(button);
  }
}

function mountPanels(uiConfig, panelKeys) {
  if (!panelHost) {
    return;
  }
  panelHost.innerHTML = "";
  panelInstances.clear();

  for (const panelId of panelKeys) {
    const panelConfig = uiConfig.panels[panelId] || {};
    const panel = createPanelComponent(panelId, panelConfig, uiConfig.sensor_catalog || {}, uiConfig);
    panel.mount(panelHost);
    panelInstances.set(panelId, panel);
  }
}

function startDataFlow(uiConfig) {
  const dataService = new DataService(uiConfig);
  dataService.subscribeStatus((state) => {
    setStatus(state);
  });
  dataService.subscribeReadings((payload) => {
    const readings = payload && typeof payload === "object" ? payload.readings : {};
    for (const panel of panelInstances.values()) {
      panel.update(readings);
    }
  });
  dataService.connect();
  return dataService;
}

function startAnomalyFlow(dataService, alertStack) {
  if (!dataService || !alertStack) {
    return;
  }

  dataService.subscribeAnomalies((payload) => {
    alertStack.push(payload);
  });
  dataService.connectAnomalies();
}

function startClockTicker() {
  renderClock();
  window.setInterval(renderClock, 1000);
}

async function boot() {
  setStatus("CONNECTING");

  try {
    const uiConfig = await fetchUiConfig();
    const panelKeys = orderedPanelKeys(uiConfig);
    const firstPanel = panelKeys.length > 0 ? panelKeys[0] : "";
    const firstLabel = firstPanel
      ? uiConfig.panels[firstPanel]?.label || humanizeIdentifier(firstPanel)
      : "";

    if (appTitle) {
      appTitle.textContent = uiConfig.project_name || "TRICORDER";
      if (firstPanel) {
        appTitle.setAttribute("href", `#${firstPanel}`);
        appTitle.addEventListener("click", (event) => {
          event.preventDefault();
          activatePanel(firstPanel, firstLabel);
        });
      }
    }

    buildNavigation(uiConfig, panelKeys);
    mountPanels(uiConfig, panelKeys);

    const alertStack = new AnomalyAlertStack(uiConfig);
    if (alertRoot) {
      alertStack.mount(alertRoot);
    }

    if (firstPanel) {
      activatePanel(firstPanel, firstLabel);
    } else {
      setStatus("NO PANELS CONFIGURED");
    }

    startClockTicker();
    const dataService = startDataFlow(uiConfig);
    startAnomalyFlow(dataService, alertStack);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    setStatus(`BOOT ERROR: ${message}`);
    if (panelHost) {
      panelHost.textContent = message;
    }
  }
}

void boot();
