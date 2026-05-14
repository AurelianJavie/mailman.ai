// popup.js — drives the MailMan.ai popup UI

let selectedEmailId = null;
let selectedEmailData = null;
let emailCache = [];

// ─── Boot ─────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  loadOverview();
  loadEmails();
  loadOTPs();
});

// ─── Tab switching ────────────────────────────────────────────────
window.switchTab = function(name) {
  document.querySelectorAll(".nav-tab").forEach(t => t.classList.remove("active"));
  document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
  document.querySelector(`[data-tab="${name}"]`).classList.add("active");
  document.getElementById(`tab-${name}`).classList.add("active");
};

// ─── Overview tab ─────────────────────────────────────────────────
function loadOverview() {
  chrome.runtime.sendMessage({ type: "GET_STATS" }, ({ stats }) => {
    if (!stats) {
      setOffline();
      return;
    }
    const total = stats.total || 0;
    setText("stat-total",     total);
    setText("stat-important", stats.high_priority || 0);
    setText("stat-spam",      stats.spam || 0);
    setText("stat-promo",     stats.subscriptions || 0);

    const cats = {
      work:   stats.work   || 0,
      travel: stats.travel || 0,
      spam:   stats.spam   || 0,
      promo:  stats.subscriptions || 0,
      otp:    stats.otp    || 0
    };

    const maxVal = Math.max(...Object.values(cats), 1);
    for (const [key, val] of Object.entries(cats)) {
      setText(`cat-${key}`, val);
      const pct = Math.round((val / maxVal) * 100);
      const bar = document.getElementById(`bar-${key}`);
      if (bar) bar.style.width = pct + "%";
    }
  });
}

function setOffline() {
  const dot = document.getElementById("status-dot");
  if (dot) { dot.textContent = "Offline"; dot.classList.add("offline"); }
}

// ─── Inbox tab ────────────────────────────────────────────────────
function loadEmails() {
  // Ask the active Gmail tab's content script for the cached email list
  chrome.tabs.query({ active: true, currentWindow: true }, ([tab]) => {
    if (!tab) { renderEmailList("email-list", []); renderEmailList("summary-email-list", []); return; }
    chrome.tabs.sendMessage(tab.id, { type: "GET_EMAIL_LIST" }, (emails) => {
      emailCache = emails || [];
      renderEmailList("email-list", emailCache, true);
      renderEmailList("summary-email-list", emailCache, false);
    });
  });
}

function renderEmailList(containerId, emails, showBadges) {
  const container = document.getElementById(containerId);
  if (!container) return;
  if (!emails.length) { container.innerHTML = `<div class="loading-msg">No emails found. Open Gmail first.</div>`; return; }

  container.innerHTML = emails.map(e => `
    <button class="email-row" data-id="${e.id}" onclick="selectEmail(this,'${containerId}')">
      <div class="email-avatar" style="background:${avatarColor(e.sender)}">${initials(e.sender)}</div>
      <div class="email-info">
        <div class="email-sender">${esc(shortName(e.sender))}</div>
        <div class="email-subject">${esc(e.subject || "(no subject)")}</div>
      </div>
      ${showBadges ? `<span class="badge ${badgeClass(e)}">${badgeLabel(e)}</span>` : ""}
    </button>
  `).join("");

  // Store email data on buttons for fast retrieval
  container.querySelectorAll(".email-row").forEach((btn, i) => {
    btn._emailData = emails[i];
  });
}

window.selectEmail = function(btn, containerId) {
  document.querySelectorAll(`#${containerId} .email-row`).forEach(r => r.classList.remove("selected"));
  btn.classList.add("selected");
  selectedEmailId   = btn.dataset.id;
  selectedEmailData = btn._emailData;
};

window.summarizeSelected = function() {
  if (!selectedEmailData) { flash("Select an email first."); return; }
  const box  = document.getElementById("inbox-summary-box");
  const body = document.getElementById("inbox-summary-body");
  box.style.display = "block";
  body.textContent = "⏳ Generating summary…";
  chrome.runtime.sendMessage({ type: "SUMMARIZE_EMAIL", payload: selectedEmailData }, ({ summary }) => {
    body.textContent = summary;
  });
};

window.deleteSelected = function() {
  if (!selectedEmailData) { flash("Select an email first."); return; }
  if (!confirm(`Delete "${selectedEmailData.subject}" from Gmail?`)) return;
  chrome.runtime.sendMessage({ type: "DELETE_EMAIL", payload: { id: selectedEmailId } }, ({ success }) => {
    if (success) loadEmails();
    else flash("Could not delete. Check backend.");
  });
};

// ─── OTP tab ──────────────────────────────────────────────────────
function loadOTPs() {
  chrome.runtime.sendMessage({ type: "GET_OTPS" }, ({ otps }) => {
    const list = document.getElementById("otp-list");
    if (!otps || !otps.length) {
      list.innerHTML = `<div class="loading-msg">No OTP emails found in your inbox.</div>`;
      return;
    }
    list.innerHTML = otps.map((o, i) => `
      <div class="otp-item" id="otp-item-${i}">
        <div class="otp-service-icon" style="background:${serviceColor(o.service)}">${o.service.charAt(0).toUpperCase()}</div>
        <div class="otp-details">
          <div class="otp-service-name">${esc(o.service)}</div>
          <div class="otp-code-display">${formatOTP(o.code)}</div>
          <div class="otp-expires">⏱ ${o.expires || "expires soon"}</div>
        </div>
        <div class="otp-btns">
          <button class="icon-btn" onclick="doCopyOTP('${o.code}', this)" title="Copy code">📋</button>
          <button class="icon-btn trash" onclick="doDeleteOTP('${o.emailId}', ${i})" title="Delete">🗑</button>
        </div>
      </div>
    `).join("");
  });
}

window.doCopyOTP = function(code, btn) {
  chrome.runtime.sendMessage({ type: "COPY_OTP", code }, () => {
    showToast();
    btn.textContent = "✓";
    setTimeout(() => btn.textContent = "📋", 2000);
  });
};

window.doDeleteOTP = function(emailId, idx) {
  if (!confirm("Delete this OTP email from Gmail?")) return;
  chrome.runtime.sendMessage({ type: "DELETE_EMAIL", payload: { id: emailId } }, ({ success }) => {
    if (success) {
      const item = document.getElementById(`otp-item-${idx}`);
      if (item) { item.style.opacity = "0"; setTimeout(() => item.remove(), 350); }
    }
  });
};

// ─── Summary tab ──────────────────────────────────────────────────
// Uses a second email list rendered by loadEmails()
// We hook clicks on summary-email-list rows here

document.addEventListener("click", e => {
  const row = e.target.closest("#summary-email-list .email-row");
  if (!row || !row._emailData) return;
  document.querySelectorAll("#summary-email-list .email-row").forEach(r => r.classList.remove("selected"));
  row.classList.add("selected");
  const box   = document.getElementById("summary-result-box");
  const label = document.getElementById("summary-sender-label");
  const body  = document.getElementById("summary-result-body");
  box.style.display = "block";
  label.textContent = shortName(row._emailData.sender);
  body.textContent  = "⏳ Analyzing…";
  chrome.runtime.sendMessage({ type: "SUMMARIZE_EMAIL", payload: row._emailData }, ({ summary }) => {
    body.textContent = summary;
  });
});

// ─── Helpers ──────────────────────────────────────────────────────
function setText(id, val) { const el = document.getElementById(id); if (el) el.textContent = val; }
function esc(str) { return String(str).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;"); }
function shortName(sender) { return (sender || "Unknown").replace(/<.*>/, "").trim() || sender; }
function initials(sender) { const n = shortName(sender); const w = n.split(" "); return (w[0][0] + (w[1] ? w[1][0] : "")).toUpperCase().slice(0,2); }

const AVATAR_COLORS = ["linear-gradient(135deg,#4a90d9,#1a5aaa)","linear-gradient(135deg,#f5a040,#c06010)","linear-gradient(135deg,#d04060,#901030)","linear-gradient(135deg,#3ab870,#1a7840)","linear-gradient(135deg,#9060d0,#5030a0)","linear-gradient(135deg,#3090c0,#106080)"];
function avatarColor(sender) { let h = 0; for (const c of (sender||"")) h = (h * 31 + c.charCodeAt(0)) % AVATAR_COLORS.length; return AVATAR_COLORS[h]; }
function serviceColor(s) { return avatarColor(s); }

function badgeClass(e) {
  if (e.is_phishing)    return "badge-phishing";
  if (e.is_spam)        return "badge-spam";
  if (e.category === "otp")    return "badge-otp";
  if (e.category === "travel") return "badge-ticket";
  if (e.category === "work")   return "badge-work";
  if (e.is_subscription)       return "badge-promo";
  if (e.priority === 1)        return "badge-important";
  return "badge-promo";
}
function badgeLabel(e) {
  if (e.is_phishing)    return "PHISHING";
  if (e.is_spam)        return "SPAM";
  if (e.category === "otp")    return "OTP";
  if (e.category === "travel") return "TICKET";
  if (e.category === "work")   return "WORK";
  if (e.is_subscription)       return "PROMO";
  if (e.priority === 1)        return "IMPORTANT";
  return "PROMO";
}
function formatOTP(code) { return code.replace(/(\d{3})(\d{3})/, "$1 $2"); }

function showToast() {
  const t = document.getElementById("copy-toast");
  t.classList.remove("hidden");
  setTimeout(() => t.classList.add("hidden"), 2500);
}

function flash(msg) { alert(msg); }