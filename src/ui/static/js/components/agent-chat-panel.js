import { BasePanel } from "./base-panel.js";
import { createElement, humanizeIdentifier } from "./render-utils.js";

const DEFAULT_AGENT_CHAT_PATH = "/ui/agent/chat";
const CHAT_STORAGE_PREFIX = "tricorder.agent-chat";
const MAX_STORED_MESSAGES = 120;

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

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function applyInlineMarkdown(escapedText) {
  return escapedText
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code>$1</code>");
}

function renderMarkdown(markdownText) {
  const lines = String(markdownText || "").replace(/\r\n/g, "\n").split("\n");
  const html = [];
  let inList = false;

  const closeList = () => {
    if (inList) {
      html.push("</ul>");
      inList = false;
    }
  };

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) {
      closeList();
      continue;
    }

    const escaped = applyInlineMarkdown(escapeHtml(line));

    if (line.startsWith("### ")) {
      closeList();
      html.push(`<h3>${escaped.slice(4)}</h3>`);
      continue;
    }
    if (line.startsWith("## ")) {
      closeList();
      html.push(`<h2>${escaped.slice(3)}</h2>`);
      continue;
    }
    if (line.startsWith("# ")) {
      closeList();
      html.push(`<h1>${escaped.slice(2)}</h1>`);
      continue;
    }
    if (line.startsWith("- ") || line.startsWith("* ")) {
      if (!inList) {
        html.push("<ul>");
        inList = true;
      }
      html.push(`<li>${escaped.slice(2)}</li>`);
      continue;
    }

    closeList();
    html.push(`<p>${escaped}</p>`);
  }

  closeList();
  return html.join("\n");
}

export class AgentChatPanel extends BasePanel {
  constructor(panelId, panelConfig, sensorCatalog, uiConfig = {}) {
    super(panelId, panelConfig, sensorCatalog, uiConfig);
    this.history = null;
    this.input = null;
    this.submitButton = null;
    this.messages = [];
  }

  _storageKey() {
    return `${CHAT_STORAGE_PREFIX}:${this.panelId}`;
  }

  _persistMessages() {
    try {
      const payload = JSON.stringify(this.messages.slice(-MAX_STORED_MESSAGES));
      window.sessionStorage.setItem(this._storageKey(), payload);
    } catch (_error) {
      // Ignore storage quota/unavailable errors.
    }
  }

  _restoreMessages() {
    try {
      const raw = window.sessionStorage.getItem(this._storageKey());
      if (!raw) {
        return;
      }
      const parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) {
        return;
      }

      for (const item of parsed.slice(-MAX_STORED_MESSAGES)) {
        if (!item || typeof item !== "object") {
          continue;
        }
        this._appendMessage(
          String(item.role || "assistant"),
          String(item.text || ""),
          item.meta ? String(item.meta) : "",
          false,
        );
      }
    } catch (_error) {
      // Ignore malformed session payloads.
    }
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
    this._restoreMessages();
    return this.root;
  }

  update(_readings) {
    // Agent chat panel is request/response-driven, not sensor-card-driven.
  }

  setActive(isActive) {
    super.setActive(isActive);
    if (isActive && this.history && this.messages.length === 0) {
      this._restoreMessages();
    }
  }

  async _submitQuery() {
    if (!this.input || !this.submitButton) {
      return;
    }

    const query = this.input.value.trim();
    if (!query) {
      this._appendMessage("error", "Query cannot be empty.");
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

  _appendMessage(role, text, meta = "", persist = true) {
    if (!this.history) {
      return;
    }

    const message = createElement("article", `agent-chat-message role-${role}`, undefined);
    const content = createElement("div", "agent-chat-text", undefined);
    if (role === "assistant") {
      content.classList.add("markdown");
      content.innerHTML = renderMarkdown(text);
    } else {
      content.textContent = text;
    }
    message.appendChild(content);

    if (meta) {
      const metadata = createElement("p", "agent-chat-meta", meta);
      message.appendChild(metadata);
    }

    this.history.appendChild(message);
    this.history.scrollTop = this.history.scrollHeight;

    this.messages.push({ role, text, meta });
    if (this.messages.length > MAX_STORED_MESSAGES) {
      this.messages = this.messages.slice(-MAX_STORED_MESSAGES);
    }
    if (persist) {
      this._persistMessages();
    }
  }
}
