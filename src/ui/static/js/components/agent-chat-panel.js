import { BasePanel } from "./base-panel.js";
import { createElement, humanizeIdentifier } from "./render-utils.js";

const DEFAULT_AGENT_CHAT_PATH = "/ui/agent/chat";

function normalizePath(rawPath) {
  const candidate = String(rawPath || DEFAULT_AGENT_CHAT_PATH);
  return candidate.startsWith("/") ? candidate : DEFAULT_AGENT_CHAT_PATH;
}

function normalizeReply(payload) {
  if (!payload || typeof payload !== "object") {
    return String(payload || "No response received.");
  }
  if (typeof payload.reply === "string" && payload.reply.trim()) {
    return payload.reply;
  }
  if (typeof payload.report === "string" && payload.report.trim()) {
    return payload.report;
  }
  return "No report generated.";
}

export class AgentChatPanel extends BasePanel {
  constructor(panelId, panelConfig, sensorCatalog, uiConfig = {}) {
    super(panelId, panelConfig, sensorCatalog, uiConfig);
    this.history = null;
    this.input = null;
    this.submitButton = null;
  }

  mount(container) {
    this.root = createElement("section", "panel-root agent-panel-root", undefined);
    this.root.id = `panel-${this.panelId}`;

    const title = createElement(
      "h2",
      "panel-title",
      this.panelConfig.label || humanizeIdentifier(this.panelId),
    );

    this.history = createElement("div", "agent-chat-history", undefined);

    const controls = createElement("div", "agent-chat-controls", undefined);
    this.input = createElement("input", "agent-chat-input", undefined);
    this.input.type = "text";
    this.input.placeholder = "ENTER QUERY FOR LIBRARY COMPUTER";

    this.submitButton = createElement("button", "agent-chat-send", "SEND");
    this.submitButton.type = "button";

    this.submitButton.addEventListener("click", () => {
      void this._submitQuery();
    });
    this.input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        void this._submitQuery();
      }
    });

    controls.append(this.input, this.submitButton);
    this.root.append(title, this.history, controls);
    container.appendChild(this.root);
    return this.root;
  }

  update(_readings) {
    // Agent chat panel is request/response-driven, not sensor-card-driven.
  }

  async _submitQuery() {
    if (!this.input || !this.submitButton) {
      return;
    }

    const query = this.input.value.trim();
    if (!query) {
      return;
    }

    this.input.value = "";
    this._appendMessage("user", query);
    this._setPending(true);

    try {
      const response = await fetch(normalizePath(this.uiConfig.agent_chat_path), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          query,
          include_sensor_context: true,
        }),
      });

      const payload = await response.json();
      if (!response.ok) {
        const detail = payload && payload.detail ? payload.detail : `HTTP ${response.status}`;
        throw new Error(String(detail));
      }

      this._appendMessage(
        "assistant",
        normalizeReply(payload),
        payload && payload.severity ? `SEVERITY: ${payload.severity}` : "",
      );
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      this._appendMessage("error", message);
    } finally {
      this._setPending(false);
    }
  }

  _setPending(isPending) {
    if (!this.submitButton || !this.input) {
      return;
    }
    this.submitButton.disabled = isPending;
    this.input.disabled = isPending;
    this.submitButton.textContent = isPending ? "..." : "SEND";
  }

  _appendMessage(role, text, meta = "") {
    if (!this.history) {
      return;
    }

    const message = createElement("article", `agent-chat-message role-${role}`, undefined);
    const content = createElement("p", "agent-chat-text", text);
    message.appendChild(content);

    if (meta) {
      const metadata = createElement("p", "agent-chat-meta", meta);
      message.appendChild(metadata);
    }

    this.history.appendChild(message);
    this.history.scrollTop = this.history.scrollHeight;
  }
}
