import { BasePanel } from "./base-panel.js";
import { createElement, formatTimestamp, humanizeIdentifier } from "./render-utils.js";

const DEFAULT_HISTORY_PATH = "/ui/anomalies/history";
const DEFAULT_PAGE_SIZE = 50;

function normalizePath(rawPath) {
  const candidate = String(rawPath || DEFAULT_HISTORY_PATH);
  return candidate.startsWith("/") ? candidate : DEFAULT_HISTORY_PATH;
}

export class AnomalyHistoryPanel extends BasePanel {
  constructor(panelId, panelConfig, sensorCatalog, uiConfig = {}) {
    super(panelId, panelConfig, sensorCatalog, uiConfig);
    this.historyPath = normalizePath(uiConfig.anomaly_history_path);
    this.pageSize = Number(uiConfig.anomaly_history_page_size) || DEFAULT_PAGE_SIZE;
    this.currentPage = 1;
    this.filters = { acknowledged_by: "", date_from: "", date_to: "" };
    this._data = [];
    this._total = 0;
    this._totalPages = 1;
    this._tableBody = null;
    this._pageInfo = null;
  }

  mount(container) {
    const wrapper = createElement("div", { className: "anomaly-history-panel" });

    // Filter bar
    const filterBar = createElement("div", { className: "history-filter-bar" });
    filterBar.style.cssText = "display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;align-items:center;";

    const opInput = createElement("input", {
      type: "text",
      placeholder: "Operator",
      className: "lcars-input",
    });
    opInput.style.cssText = "width:120px;padding:4px 8px;border-radius:4px;border:1px solid #999;background:#1a1a2e;color:#f5f5f5;";
    opInput.addEventListener("input", () => { this.filters.acknowledged_by = opInput.value; });

    const fromInput = createElement("input", { type: "date", className: "lcars-input" });
    fromInput.style.cssText = "padding:4px 8px;border-radius:4px;border:1px solid #999;background:#1a1a2e;color:#f5f5f5;";
    fromInput.addEventListener("change", () => { this.filters.date_from = fromInput.value ? fromInput.value + "T00:00:00Z" : ""; });

    const toInput = createElement("input", { type: "date", className: "lcars-input" });
    toInput.style.cssText = "padding:4px 8px;border-radius:4px;border:1px solid #999;background:#1a1a2e;color:#f5f5f5;";
    toInput.addEventListener("change", () => { this.filters.date_to = toInput.value ? toInput.value + "T23:59:59Z" : ""; });

    const filterBtn = createElement("button", { textContent: "FILTER" });
    filterBtn.style.cssText = "padding:4px 16px;border-radius:4px;background:#fc6;color:#000;border:none;cursor:pointer;font-weight:bold;";
    filterBtn.addEventListener("click", () => { this.currentPage = 1; this._fetchPage(); });

    const exportBtn = createElement("button", { textContent: "EXPORT CSV" });
    exportBtn.style.cssText = "padding:4px 16px;border-radius:4px;background:#6cf;color:#000;border:none;cursor:pointer;font-weight:bold;margin-left:auto;";
    exportBtn.addEventListener("click", () => this._exportCsv());

    filterBar.append(opInput, fromInput, toInput, filterBtn, exportBtn);

    // Table
    const table = createElement("table");
    table.style.cssText = "width:100%;border-collapse:collapse;font-size:0.85rem;";
    const thead = createElement("thead");
    const headerRow = createElement("tr");
    for (const col of ["Anomaly ID", "Acknowledged By", "Acknowledged At", "Note", "Source"]) {
      const th = createElement("th", { textContent: col });
      th.style.cssText = "text-align:left;padding:6px 8px;border-bottom:2px solid #fc6;color:#fc6;";
      headerRow.appendChild(th);
    }
    thead.appendChild(headerRow);
    this._tableBody = createElement("tbody");
    table.append(thead, this._tableBody);

    // Pagination
    const pagination = createElement("div");
    pagination.style.cssText = "display:flex;justify-content:space-between;align-items:center;margin-top:8px;";
    const prevBtn = createElement("button", { textContent: "PREV" });
    prevBtn.style.cssText = "padding:4px 12px;border-radius:4px;background:#555;color:#fff;border:none;cursor:pointer;";
    prevBtn.addEventListener("click", () => { if (this.currentPage > 1) { this.currentPage--; this._fetchPage(); } });
    this._pageInfo = createElement("span", { textContent: "Page 1 / 1" });
    this._pageInfo.style.color = "#ccc";
    const nextBtn = createElement("button", { textContent: "NEXT" });
    nextBtn.style.cssText = "padding:4px 12px;border-radius:4px;background:#555;color:#fff;border:none;cursor:pointer;";
    nextBtn.addEventListener("click", () => { if (this.currentPage < this._totalPages) { this.currentPage++; this._fetchPage(); } });
    pagination.append(prevBtn, this._pageInfo, nextBtn);

    const scrollWrap = createElement("div");
    scrollWrap.style.cssText = "overflow-y:auto;max-height:calc(100vh - 280px);";
    scrollWrap.appendChild(table);

    wrapper.append(filterBar, scrollWrap, pagination);
    container.appendChild(wrapper);
  }

  update(_readings) {
    // No sensor data needed for this panel
  }

  setActive(isActive) {
    super.setActive(isActive);
    if (isActive) {
      this._fetchPage();
    }
  }

  async _fetchPage() {
    const params = new URLSearchParams({
      page: String(this.currentPage),
      page_size: String(this.pageSize),
    });
    if (this.filters.acknowledged_by) params.set("acknowledged_by", this.filters.acknowledged_by);
    if (this.filters.date_from) params.set("date_from", this.filters.date_from);
    if (this.filters.date_to) params.set("date_to", this.filters.date_to);

    try {
      const resp = await fetch(`${this.historyPath}?${params}`);
      if (!resp.ok) return;
      const data = await resp.json();
      this._data = data.items || [];
      this._total = data.total || 0;
      this._totalPages = data.total_pages || 1;
      this._renderRows();
      this._renderPagination();
    } catch (err) {
      // Silently fail -- panel will show empty
    }
  }

  _renderRows() {
    if (!this._tableBody) return;
    // Clear existing rows safely via DOM removal
    while (this._tableBody.firstChild) {
      this._tableBody.removeChild(this._tableBody.firstChild);
    }
    if (this._data.length === 0) {
      const row = createElement("tr");
      const cell = createElement("td", { textContent: "No records found.", colSpan: 5 });
      cell.style.cssText = "padding:12px;text-align:center;color:#888;";
      row.appendChild(cell);
      this._tableBody.appendChild(row);
      return;
    }
    for (const item of this._data) {
      const row = createElement("tr");
      row.style.borderBottom = "1px solid #333";
      for (const key of ["anomaly_id", "acknowledged_by", "acknowledged_at", "note", "operator_source"]) {
        const td = createElement("td");
        td.style.cssText = "padding:6px 8px;color:#ddd;";
        td.textContent = item[key] || "";
        row.appendChild(td);
      }
      this._tableBody.appendChild(row);
    }
  }

  _renderPagination() {
    if (this._pageInfo) {
      this._pageInfo.textContent = `Page ${this.currentPage} / ${this._totalPages} (${this._total} total)`;
    }
  }

  _exportCsv() {
    if (!this._data.length) return;
    const headers = ["anomaly_id", "acknowledged_by", "acknowledged_at", "note", "operator_source"];
    const rows = [headers.join(",")];
    for (const item of this._data) {
      const cells = headers.map((h) => {
        const val = String(item[h] || "").replace(/"/g, '""');
        return `"${val}"`;
      });
      rows.push(cells.join(","));
    }
    const csv = rows.join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = createElement("a", { href: url, download: "anomaly-history.csv" });
    a.style.display = "none";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }
}
