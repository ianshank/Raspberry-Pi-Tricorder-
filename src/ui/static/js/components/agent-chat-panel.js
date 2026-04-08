import { BasePanel } from "./base-panel.js";
import { createElement, humanizeIdentifier } from "./render-utils.js";

const DEFAULT_AGENT_CHAT_PATH = "/ui/agent/chat";
const DEFAULT_AGENT_STREAM_PATH = "/ui/agent/chat/stream";
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

  _isStreamEnabled() {
    return Boolean(this.uiConfig.agent_stream_enabled) &&
      Boolean(this.uiConfig.agent_chat_stream_path);
  }

  _streamPath() {
    const candidate = String(this.uiConfig.agent_chat_stream_path || DEFAULT_AGENT_STREAM_PATH);
    return candidate.startsWith("/") ? candidate : DEFAULT_AGENT_STREAM_PATH;
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
      if (this._isStreamEnabled()) {
        await this._submitQueryStream(query);
      } else {
        await this._submitQueryPost(query);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      this._appendMessage("error", message);
    } finally {
      this._setPending(false);
    }
  }

  async _submitQueryPost(query) {
    const response = await fetch(normalizePath(this.uiConfig.agent_chat_path), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, include_sensor_context: true }),
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
  }

  async _submitQueryStream(query) {
    const url = `${this._streamPath()}?query=${encodeURIComponent(query)}&include_sensor_context=true`;
    const response = await fetch(url);
    if (!response.ok) {
      // Fallback to POST if SSE endpoint unavailable
      return this._submitQueryPost(query);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let accumulated = "";
    let severity = "";
    let msgElement = null;

    const processLine = (line) => {
      if (line.startsWith("event: ")) {
        this._currentEvent = line.slice(7).trim();
      } else if (line.startsWith("data: ")) {
        try {
          const data = JSON.parse(line.slice(6));
          if (this._currentEvent === "node_enter") {
            if (!msgElement) {
              msgElement = this._appendStreamingMessage();
            }
            this._updateStreamStatus(msgElement, data.node || "processing");
          } else if (this._currentEvent === "token") {
            if (!msgElement) {
              msgElement = this._appendStreamingMessage();
            }
            accumulated += data.text || "";
            this._updateStreamContent(msgElement, accumulated);
          } else if (this._currentEvent === "complete") {
            accumulated = data.report || accumulated || "No report generated.";
            severity = data.severity || "";
          } else if (this._currentEvent === "error") {
            throw new Error(data.message || "Stream error");
          }
        } catch (e) {
          if (e.message !== "Stream error") {
            // JSON parse error — ignore partial lines
          } else {
            throw e;
          }
        }
      }
    };

    let buffer = "";
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) {
          processLine(line);
        }
      }
    } finally {
      reader.releaseLock();
    }

    // Remove streaming element and add final message
    if (msgElement && msgElement.parentNode) {
      msgElement.parentNode.removeChild(msgElement);
    }
    this._appendMessage(
      "assistant",
      accumulated || "No report generated.",
      severity ? `SEVERITY: ${severity}` : "",
    );
  }

  _appendStreamingMessage() {
    if (!this.history) return null;
    const msg = createElement("article", "agent-chat-message role-assistant streaming", undefined);
    const status = createElement("p", "agent-chat-stream-status", "Processing...");
    const content = createElement("div", "agent-chat-text markdown", undefined);
    msg.append(status, content);
    this.history.appendChild(msg);
    this.history.scrollTop = this.history.scrollHeight;
    return msg;
  }

  _updateStreamStatus(element, node) {
    if (!element) return;
    const status = element.querySelector(".agent-chat-stream-status");
    if (status) {
      const labels = {
        sensor_monitor: "Monitoring sensors...",
        evidence_gather: "Gathering evidence...",
        plan_tools: "Planning tools...",
        execute_tools: "Executing tools...",
        synthesize_report: "Synthesizing report...",
      };
      status.textContent = labels[node] || `${node}...`;
    }
  }

  _updateStreamContent(element, text) {
    if (!element) return;
    const content = element.querySelector(".agent-chat-text");
    if (content) {
      content.innerHTML = renderMarkdown(text);
      this.history.scrollTop = this.history.scrollHeight;
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
