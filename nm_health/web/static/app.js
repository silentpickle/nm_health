// State
let currentQuery = "";
let currentStatus = "";
let debounceTimeout = null;

// DOM Elements
const searchInput = document.getElementById("search-input");
const searchClear = document.getElementById("search-clear");
const filterPills = document.querySelectorAll(".filter-pills .pill");
const resultsGrid = document.getElementById("results-grid");
const emptyState = document.getElementById("empty-state");
const resultsCountTitle = document.getElementById("results-count-title");
const alertsBanner = document.getElementById("alerts-banner");
const alertsList = document.getElementById("alerts-list");
const btnViewAlerts = document.getElementById("btn-view-alerts");
const alertsClose = document.getElementById("alerts-close");

// Restaurant Modal Elements
const modalBackdrop = document.getElementById("modal-backdrop");
const modalClose = document.getElementById("modal-close");
const modalEstName = document.getElementById("modal-est-name");
const modalEstAddress = document.getElementById("modal-est-address");
const modalBody = document.getElementById("modal-body");

// Reports Archive Modal Elements
const btnViewReports = document.getElementById("btn-view-reports");
const reportsModalBackdrop = document.getElementById("reports-modal-backdrop");
const reportsModalClose = document.getElementById("reports-modal-close");
const reportsModalBody = document.getElementById("reports-modal-body");

// Stats Elements
const statEsts = document.getElementById("stat-establishments");
const statInsps = document.getElementById("stat-inspections");
const statClosures = document.getElementById("stat-closures");
const statPest = document.getElementById("stat-pest");
const statReports = document.getElementById("stat-reports");

// Initialize
document.addEventListener("DOMContentLoaded", () => {
  loadStats();
  performSearch();
  handleHashChange();

  window.addEventListener("hashchange", handleHashChange);

  // Search input with debounce
  searchInput.addEventListener("input", (e) => {
    currentQuery = e.target.value.trim();
    searchClear.classList.toggle("hidden", currentQuery.length === 0);
    clearTimeout(debounceTimeout);
    debounceTimeout = setTimeout(performSearch, 250);
  });

  searchClear.addEventListener("click", () => {
    searchInput.value = "";
    currentQuery = "";
    searchClear.classList.add("hidden");
    performSearch();
  });

  // Filter Pills
  filterPills.forEach((pill) => {
    pill.addEventListener("click", () => {
      filterPills.forEach((p) => p.classList.remove("active"));
      pill.classList.add("active");
      currentStatus = pill.getAttribute("data-status") || "";
      performSearch();
    });
  });

  // Alerts Toggle
  btnViewAlerts.addEventListener("click", toggleAlerts);
  alertsClose.addEventListener("click", () => alertsBanner.classList.add("hidden"));

  // Reports Archive Toggle
  btnViewReports.addEventListener("click", openReportsArchive);
  reportsModalClose.addEventListener("click", () => reportsModalBackdrop.classList.add("hidden"));
  reportsModalBackdrop.addEventListener("click", (e) => {
    if (e.target === reportsModalBackdrop) reportsModalBackdrop.classList.add("hidden");
  });

  // Restaurant Modal Close
  modalClose.addEventListener("click", closeModal);
  modalBackdrop.addEventListener("click", (e) => {
    if (e.target === modalBackdrop) closeModal();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      closeModal();
      reportsModalBackdrop.classList.add("hidden");
    }
  });
});

// Routing
function handleHashChange() {
  const hash = window.location.hash;
  const match = hash.match(/^#\/restaurant\/(\d+)$/);
  if (match) {
    const estId = match[1];
    openEstablishmentDetail(estId, false);
  } else if (!hash) {
    if (!modalBackdrop.classList.contains("hidden")) {
      modalBackdrop.classList.add("hidden");
    }
  }
}

// Helpers
function formatDateTime(isoStr) {
  if (!isoStr) return "N/A";
  try {
    const d = new Date(isoStr);
    if (isNaN(d.getTime())) return isoStr;
    return d.toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit",
      timeZoneName: "short"
    });
  } catch {
    return isoStr;
  }
}

function formatBytes(bytes) {
  if (!bytes) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
}

// API Calls
async function loadStats() {
  try {
    const res = await fetch("/api/stats");
    const data = await res.json();
    statEsts.textContent = data.total_establishments || "0";
    statInsps.textContent = data.total_inspections || "0";
    statClosures.textContent = data.total_closures || "0";
    statPest.textContent = data.establishments_with_pest_violations || "0";
    statReports.textContent = data.total_reports || "0";
  } catch (err) {
    console.error("Failed to load stats:", err);
  }
}

async function performSearch() {
  try {
    const params = new URLSearchParams();
    if (currentQuery) params.set("q", currentQuery);
    if (currentStatus) params.set("status", currentStatus);

    const res = await fetch(`/api/search?${params.toString()}`);
    const items = await res.json();
    renderResults(items);
  } catch (err) {
    console.error("Failed to search:", err);
  }
}

async function toggleAlerts() {
  if (!alertsBanner.classList.contains("hidden")) {
    alertsBanner.classList.add("hidden");
    return;
  }

  try {
    const res = await fetch("/api/alerts?limit=15");
    const alerts = await res.json();
    renderAlerts(alerts);
    alertsBanner.classList.remove("hidden");
    alertsBanner.scrollIntoView({ behavior: "smooth" });
  } catch (err) {
    console.error("Failed to fetch alerts:", err);
  }
}

async function openEstablishmentDetail(id, updateHash = true) {
  try {
    if (updateHash) {
      window.location.hash = `#/restaurant/${id}`;
    }
    modalBody.innerHTML = "<p class='text-muted'>Loading inspection history and retained PDFs...</p>";
    modalBackdrop.classList.remove("hidden");

    const res = await fetch(`/api/establishments/${id}`);
    const est = await res.json();

    modalEstName.textContent = est.name;
    modalEstAddress.textContent = `${est.normalized_address} (${est.raw_address})`;

    renderModalHistory(est);
  } catch (err) {
    modalBody.innerHTML = "<p class='text-danger'>Error loading details.</p>";
  }
}

function closeModal() {
  modalBackdrop.classList.add("hidden");
  if (window.location.hash.startsWith("#/restaurant/")) {
    history.pushState("", document.title, window.location.pathname + window.location.search);
  }
}

async function openReportsArchive() {
  try {
    reportsModalBody.innerHTML = "<p class='text-muted'>Loading retained PDF reports archive...</p>";
    reportsModalBackdrop.classList.remove("hidden");

    const res = await fetch("/api/reports");
    const reports = await res.json();
    renderReportsArchive(reports);
  } catch (err) {
    reportsModalBody.innerHTML = "<p class='text-danger'>Error loading archive reports.</p>";
  }
}

// Render Functions
function getBadgeClass(status) {
  const s = (status || "").toLowerCase();
  if (s.includes("closure") || s.includes("unsatisfactory")) return "badge-danger";
  if (s.includes("conditional")) return "badge-conditional";
  if (s.includes("approved")) return "badge-approved";
  return "badge-conditional";
}

function renderResults(items) {
  resultsGrid.innerHTML = "";

  if (!items || items.length === 0) {
    emptyState.classList.remove("hidden");
    resultsCountTitle.textContent = "0 Restaurants";
    return;
  }

  emptyState.classList.add("hidden");
  resultsCountTitle.textContent = `${items.length} Restaurant${items.length === 1 ? "" : "s"} Found`;

  items.forEach((item) => {
    const card = document.createElement("div");
    card.className = "est-card";
    card.onclick = () => openEstablishmentDetail(item.id);

    const badgeClass = getBadgeClass(item.latest_status);
    const pestTag = item.has_pest_history
      ? `<span class="pest-tag">⚠ Pest History</span>`
      : "";

    card.innerHTML = `
      <div>
        <div class="est-card-header">
          <h3 class="est-card-title">${escapeHtml(item.name)}</h3>
          <span class="badge ${badgeClass}">${escapeHtml(item.latest_status || "Unknown")}</span>
        </div>
        <p class="est-address">${escapeHtml(item.normalized_address)}</p>
        ${pestTag}
      </div>
      <div class="est-meta-footer">
        <span>Last: ${escapeHtml(item.latest_inspection_date || "N/A")}</span>
        <span>${item.total_inspections} inspection${item.total_inspections === 1 ? "" : "s"} & PDFs →</span>
      </div>
    `;
    resultsGrid.appendChild(card);
  });
}

function renderAlerts(alerts) {
  alertsList.innerHTML = "";
  if (!alerts || alerts.length === 0) {
    alertsList.innerHTML = "<p class='text-muted'>No critical action alerts on record.</p>";
    return;
  }

  alerts.forEach((alert) => {
    const mini = document.createElement("div");
    mini.className = "alert-card-mini";
    mini.onclick = () => openEstablishmentDetail(alert.establishment_id);

    const badgeClass = getBadgeClass(alert.inspection_status);
    const viols = alert.violations || [];
    const notes = viols.map(v => v.observation || v.item_title).filter(Boolean).slice(0, 2);

    mini.innerHTML = `
      <div class="alert-card-top">
        <span>${escapeHtml(alert.establishment_name)} (${escapeHtml(alert.normalized_address)})</span>
        <span class="badge ${badgeClass}">${escapeHtml(alert.inspection_status)}</span>
      </div>
      <p class="text-muted" style="font-size: 0.8rem; margin: 0.25rem 0;">
        ${escapeHtml(alert.inspection_date)} • ${escapeHtml(alert.inspection_type)}
      </p>
      ${notes.length ? `<div style="font-size: 0.82rem; color: #475569; margin-top: 0.35rem;">“${escapeHtml(notes.join(' • '))}”</div>` : ""}
    `;
    alertsList.appendChild(mini);
  });
}

function renderModalHistory(est) {
  let html = "";

  // Permits Summary
  if (est.permits && est.permits.length > 0) {
    html += `<div style="background: #f1f5f9; padding: 0.75rem 1rem; border-radius: 8px; font-size: 0.85rem;">
      <strong>Permits on File:</strong><br/>
      ${est.permits.map(p => `• Permit #${escapeHtml(p.permit_number)}: ${escapeHtml(p.permit_type)} (${escapeHtml(p.operational_status)})`).join("<br/>")}
    </div>`;
  }

  html += `<h3 style="font-size: 1.15rem; font-weight: 700; margin-top: 0.75rem;">Chronological Inspection Records & Retained PDFs</h3>`;

  if (!est.inspections || est.inspections.length === 0) {
    html += `<p class="text-muted">No inspection records found.</p>`;
    modalBody.innerHTML = html;
    return;
  }

  html += `<div class="timeline">`;
  est.inspections.forEach((insp) => {
    const badgeClass = getBadgeClass(insp.inspection_status);
    let bulletClass = "bullet-success";
    if (badgeClass === "badge-danger") bulletClass = "bullet-danger";
    else if (badgeClass === "badge-conditional") bulletClass = "bullet-warning";

    const viols = insp.violations || [];
    const pageNum = insp.detail_page || insp.summary_page || 1;
    const pageParam = insp.detail_page ? `#page=${insp.detail_page}` : "";
    const pdfUrl = insp.report_filename ? `/api/pdf/${encodeURIComponent(insp.report_filename)}${pageParam}` : null;
    const dlUrl = insp.report_filename ? `/api/pdf/${encodeURIComponent(insp.report_filename)}?download=true` : null;

    html += `
      <div class="timeline-item">
        <div class="timeline-bullet ${bulletClass}"></div>
        <div class="timeline-card">
          <div class="timeline-top">
            <span class="timeline-date">Inspection Date: ${escapeHtml(insp.inspection_date)}</span>
            <span class="badge ${badgeClass}">${escapeHtml(insp.inspection_status)}</span>
          </div>
          
          <div class="timeline-meta">
            ${escapeHtml(insp.inspection_type)} • Inspection ID: <strong>${escapeHtml(insp.inspection_id_num)}</strong>
          </div>

          <!-- Retained PDF Box -->
          ${insp.report_filename ? `
            <div class="retained-pdf-box">
              <div class="retained-pdf-header">
                <span>📄 Retained Weekly PDF Report</span>
                <span class="badge badge-approved" style="font-size: 0.7rem;">Verified Ingested Copy</span>
              </div>
              <div class="retained-pdf-details">
                <div>📅 <strong>Week Covered:</strong> ${escapeHtml(insp.week_start || "")} - ${escapeHtml(insp.week_end || "")}</div>
                <div>📥 <strong>Downloaded / Retained On:</strong> ${escapeHtml(formatDateTime(insp.report_downloaded_at))}</div>
                <div>📑 <strong>Appears on:</strong> Page ${escapeHtml(pageNum)} of report</div>
                <div>💾 <strong>File Size:</strong> ${escapeHtml(formatBytes(insp.report_file_size))}</div>
              </div>
              <div style="font-size: 0.72rem; color: #64748b; margin-top: 0.2rem;">
                🔒 SHA-256 Checksum: <span class="hash-code">${escapeHtml((insp.report_sha256 || "").substring(0, 20))}...</span>
              </div>
              <div class="retained-pdf-actions">
                <a href="${pdfUrl}" target="_blank" class="btn-pdf-view">
                  🔍 View Retained PDF at Page ${pageNum}
                </a>
                <a href="${dlUrl}" class="btn-pdf-dl">
                  ⬇️ Download PDF (${formatBytes(insp.report_file_size)})
                </a>
              </div>
            </div>
          ` : `
            <p class="text-muted" style="font-size: 0.8rem; margin: 0.5rem 0;">(No archived PDF record linked)</p>
          `}

          <!-- Violations -->
          <div style="margin-top: 0.75rem;">
            ${viols.length === 0 ? `<p class="text-muted" style="font-size: 0.85rem;">✔ No violations cited during this inspection.</p>` : `
              <strong style="font-size: 0.88rem; color: #1e293b;">Cited Violations (${viols.length}):</strong>
              ${viols.map((v) => `
                <div class="violation-box ${v.is_pest ? 'pest-violation' : ''}">
                  <div class="violation-title">
                    ${v.is_pest ? '<span class="text-danger">⚠ [PEST WARNING] </span>' : ''}
                    ${escapeHtml(v.category)}: ${escapeHtml(v.item_title)}
                  </div>
                  ${v.observation ? `<p class="violation-obs"><strong>Inspector Observation:</strong> ${escapeHtml(v.observation)}</p>` : ''}
                </div>
              `).join("")}
            `}
          </div>

        </div>
      </div>
    `;
  });
  html += `</div>`;

  modalBody.innerHTML = html;
}

function renderReportsArchive(reports) {
  reportsModalBody.innerHTML = "";
  if (!reports || reports.length === 0) {
    reportsModalBody.innerHTML = "<p class='text-muted'>No reports have been archived yet.</p>";
    return;
  }

  const container = document.createElement("div");
  container.style.display = "flex";
  container.style.flexDirection = "column";
  container.style.gap = "1rem";

  reports.forEach((rep) => {
    const card = document.createElement("div");
    card.className = "report-archive-card";
    const pdfUrl = `/api/pdf/${encodeURIComponent(rep.filename)}`;
    const dlUrl = `/api/pdf/${encodeURIComponent(rep.filename)}?download=true`;

    card.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem;">
        <div>
          <h4 style="font-size: 1.05rem; font-weight: 700; color: #0f172a;">
            ${escapeHtml(rep.filename)}
          </h4>
          <p style="font-size: 0.85rem; color: #475569; margin-top: 0.15rem;">
            Report Week: <strong>${escapeHtml(rep.week_start || "N/A")}</strong> to <strong>${escapeHtml(rep.week_end || "N/A")}</strong>
          </p>
        </div>
        <span class="badge badge-approved">Retained & Archived</span>
      </div>

      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 0.4rem; font-size: 0.82rem; color: #334155; margin-top: 0.5rem; background: #f8fafc; padding: 0.75rem; border-radius: 6px;">
        <div>📥 <strong>Downloaded / Ingested:</strong> ${escapeHtml(formatDateTime(rep.downloaded_at))}</div>
        <div>🏪 <strong>Establishments Covered:</strong> ${rep.total_establishments || 0}</div>
        <div>📋 <strong>Total Inspections:</strong> ${rep.total_inspections || 0}</div>
        <div>💾 <strong>File Size:</strong> ${escapeHtml(formatBytes(rep.file_size))}</div>
        <div style="grid-column: 1 / -1;">
          🔒 <strong>SHA-256 Hash:</strong> <span class="hash-code">${escapeHtml(rep.sha256_hash)}</span>
        </div>
      </div>

      <div class="retained-pdf-actions" style="margin-top: 0.5rem;">
        <a href="${pdfUrl}" target="_blank" class="btn-pdf-view">
          🔍 View Full PDF Report
        </a>
        <a href="${dlUrl}" class="btn-pdf-dl">
          ⬇️ Download PDF (${formatBytes(rep.file_size)})
        </a>
      </div>
    `;
    container.appendChild(card);
  });

  reportsModalBody.appendChild(container);
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
