// popup.js — MailMan.ai popup controller

let selectedEmailId   = null;
let selectedEmailData = null;
let emailCache        = [];

// ─── Boot ─────────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  checkStatus();
  loadOverview();
  loadOTPs();

  // Wire up tab buttons (nav-tab elements use data-tab attribute)
  document.querySelectorAll(".nav-tab").forEach(btn => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  });

  // Wire summary-email-list click via delegation
  document.getElementById("summary-email-list")
    ?.addEventListener("click", onSummaryEmailClick);
});

// ─── Online / Offline indicator ───────────────────────────────────────────────
function checkStatus() {
  chrome.runtime.sendMessage({ type: "CHECK_STATUS" }, (res) => {
    if (chrome.runtime.lastError) return;
    setStatus(res?.online ?? false);
  });
}

function setStatus(online) {
  const dot   = document.getElementById("status-dot");
  const label = document.getElementById("status-label");
  if (dot)   { dot.className   = "status-dot " + (online ? "online" : "offline"); }
  if (label) { label.textContent = online ? "Online" : "Offline"; }
}

// ─── Tab switching ────────────────────────────────────────────────────────────
window.switchTab = function(name) {
  document.querySelectorAll(".nav-tab").forEach(t => t.classList.remove("active"));
  document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));

  const btn = document.querySelector(`.nav-tab[data-tab="${name}"]`);
  const pane = document.getElementById(`tab-${name}`);
  if (btn)  btn.classList.add("active");
  if (pane) pane.classList.add("active");

  // Lazy-load inbox tab only when the user clicks it (needs Gmail tab to be open)
  if (name === "inbox" || name === "summary") {
    if (!emailCache.length) loadEmails();
  }
};

// ─── Overview tab ─────────────────────────────────────────────────────────────
function loadOverview() {
  chrome.runtime.sendMessage({ type: "GET_STATS" }, (res) => {
    if (chrome.runtime.lastError) { setStatus(false); return; }
    const { stats, online } = res || {};
    setStatus(!!online);

    if (!stats) return;

    setText("stat-total",     stats.total        || 0);
    setText("stat-important", stats.high_priority || 0);
    setText("stat-spam",      stats.spam          || 0);
    setText("stat-promo",     stats.subscriptions || 0);

    const cats = {
      work:   stats.work          || 0,
      travel: stats.travel        || 0,
      spam:   stats.spam          || 0,
      promo:  stats.subscriptions || 0,
      otp:    stats.otp           || 0
    };
    const maxVal = Math.max(...Object.values(cats), 1);
    for (const [key, val] of Object.entries(cats)) {
      setText(`cat-${key}`, val);
      const bar = document.getElementById(`bar-${key}`);
      if (bar) bar.style.width = Math.round((val / maxVal) * 100) + "%";
    }
  });
}

// ─── Inbox tab ────────────────────────────────────────────────────────────────
function loadEmails() {
  chrome.tabs.query({ url: "https://mail.google.com/*" }, (tabs) => {
    if (!tabs || !tabs.length) {
      showNoGmailMsg("email-list");
      showNoGmailMsg("summary-email-list");
      return;
    }

    const gmailTab = tabs[0];

    // PING first — confirm content script is alive before sending GET_EMAIL_LIST
    chrome.tabs.sendMessage(gmailTab.id, { type: "PING" }, (pingRes) => {
      if (chrome.runtime.lastError || !pingRes?.pong) {
        // Content script not ready (page still loading, or wrong tab)
        showNoGmailMsg("email-list");
        showNoGmailMsg("summary-email-list");
        return;
      }

      chrome.tabs.sendMessage(gmailTab.id, { type: "GET_EMAIL_LIST" }, (emails) => {
        if (chrome.runtime.lastError) {
          showNoGmailMsg("email-list");
          showNoGmailMsg("summary-email-list");
          return;
        }
        emailCache = emails || [];
        renderEmailList("email-list",         emailCache, true);
        renderEmailList("summary-email-list", emailCache, false);
      });
    });
  });
}

function showNoGmailMsg(containerId) {
  const el = document.getElementById(containerId);
  if (el) el.innerHTML = `<div class="loading-msg">Open Gmail in a tab first.</div>`;
}

function renderEmailList(containerId, emails, showBadges) {
  const container = document.getElementById(containerId);
  if (!container) return;

  if (!emails.length) {
    container.innerHTML = `<div class="loading-msg">No emails found.</div>`;
    return;
  }

  container.innerHTML = emails.map((e, i) => `
    <button class="email-row" data-index="${i}">
      <div class="email-avatar" style="background:${avatarColor(e.sender)}">${initials(e.sender)}</div>
      <div class="email-info">
        <div class="email-sender">${esc(shortName(e.sender))}</div>
        <div class="email-subject">${esc(e.subject || "(no subject)")}</div>
      </div>
      ${showBadges ? `<span class="badge ${badgeClass(e)}">${badgeLabel(e)}</span>` : ""}
    </button>
  `).join("");

  // Attach email data directly to DOM nodes (survives re-renders)
  container.querySelectorAll(".email-row").forEach((btn, i) => {
    btn._emailData = emails[i];
    btn.addEventListener("click", () => onEmailRowClick(btn, containerId));
  });
}

function onEmailRowClick(btn, containerId) {
  document.querySelectorAll(`#${containerId} .email-row`).forEach(r => r.classList.remove("selected"));
  btn.classList.add("selected");
  selectedEmailId   = btn._emailData?.id;
  selectedEmailData = btn._emailData;
}

// ─── Inbox actions ────────────────────────────────────────────────────────────
window.summarizeSelected = function() {
  if (!selectedEmailData) { flash("Select an email first."); return; }
  const box  = document.getElementById("inbox-summary-box");
  const body = document.getElementById("inbox-summary-body");
  if (box)  box.style.display = "block";
  if (body) body.textContent  = "⏳ Generating summary…";

  chrome.runtime.sendMessage({ type: "SUMMARIZE_EMAIL", payload: selectedEmailData }, (res) => {
    if (body) body.textContent = res?.summary || "No summary returned.";
  });
};

window.deleteSelected = function() {
  if (!selectedEmailData) { flash("Select an email first."); return; }
  if (!confirm(`Delete "${selectedEmailData.subject}" from Gmail?`)) return;
  chrome.runtime.sendMessage({ type: "DELETE_EMAIL", payload: { id: selectedEmailId } }, (res) => {
    if (res?.success) loadEmails();
    else flash("Could not delete. Check backend.");
  });
};

// ─── OTP tab ──────────────────────────────────────────────────────────────────
function loadOTPs() {
  chrome.runtime.sendMessage({ type: "GET_OTPS" }, (res) => {
    if (chrome.runtime.lastError) return;
    const otps = res?.otps || [];
    const list = document.getElementById("otp-list");
    if (!list) return;

    if (!otps.length) {
      list.innerHTML = `<div class="loading-msg">No OTP emails found in your inbox.</div>`;
      return;
    }

    list.innerHTML = otps.map((o, i) => `
      <div class="otp-item" id="otp-item-${i}">
        <div class="otp-service-icon" style="background:${serviceColor(o.service)}">${(o.service||"?").charAt(0).toUpperCase()}</div>
        <div class="otp-details">
          <div class="otp-service-name">${esc(o.service || "")}</div>
          <div class="otp-code-display">${formatOTP(o.code || "")}</div>
          <div class="otp-expires">⏱ ${esc(o.expires || "expires soon")}</div>
        </div>
        <div class="otp-btns">
          <button class="icon-btn" data-otp-copy="${esc(o.code)}" title="Copy code">📋</button>
          <button class="icon-btn trash" data-otp-del-id="${esc(o.emailId)}" data-otp-del-idx="${i}" title="Delete">🗑</button>
        </div>
      </div>
    `).join("");

    // Event delegation — avoids inline onclick and stale closure issues
    list.addEventListener("click", onOTPListClick);
  });
}

function onOTPListClick(e) {
  const copyBtn = e.target.closest("[data-otp-copy]");
  const delBtn  = e.target.closest("[data-otp-del-id]");

  if (copyBtn) {
    const code = copyBtn.dataset.otpCopy;
    chrome.runtime.sendMessage({ type: "COPY_OTP", code }, () => {
      showToast();
      copyBtn.textContent = "✓";
      setTimeout(() => copyBtn.textContent = "📋", 2000);
    });
  }

  if (delBtn) {
    const emailId = delBtn.dataset.otpDelId;
    const idx     = parseInt(delBtn.dataset.otpDelIdx, 10);
    if (!confirm("Delete this OTP email from Gmail?")) return;
    chrome.runtime.sendMessage({ type: "DELETE_EMAIL", payload: { id: emailId } }, (res) => {
      if (res?.success) {
        const item = document.getElementById(`otp-item-${idx}`);
        if (item) { item.style.opacity = "0"; setTimeout(() => item.remove(), 350); }
      }
    });
  }
}

// ─── Summary tab ──────────────────────────────────────────────────────────────
function onSummaryEmailClick(e) {
  const row = e.target.closest(".email-row");
  if (!row || !row._emailData) return;

  document.querySelectorAll("#summary-email-list .email-row").forEach(r => r.classList.remove("selected"));
  row.classList.add("selected");

  const box   = document.getElementById("summary-result-box");
  const label = document.getElementById("summary-sender-label");
  const body  = document.getElementById("summary-result-body");

  if (box)   box.style.display  = "block";
  if (label) label.textContent  = shortName(row._emailData.sender);
  if (body)  body.textContent   = "⏳ Analyzing…";

  chrome.runtime.sendMessage({ type: "SUMMARIZE_EMAIL", payload: row._emailData }, (res) => {
    if (body) body.textContent = res?.summary || "No summary returned.";
  });
}

// ─── Helpers ──────────────────────────────────────────────────────────────────
function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

function esc(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function shortName(sender) {
  return (sender || "Unknown").replace(/<[^>]+>/, "").trim() || sender;
}

function initials(sender) {
  const n = shortName(sender);
  const w = n.trim().split(/\s+/);
  return ((w[0]?.[0] || "") + (w[1]?.[0] || "")).toUpperCase().slice(0, 2) || "?";
}

const AVATAR_COLORS = [
  "linear-gradient(135deg,#4a90d9,#1a5aaa)",
  "linear-gradient(135deg,#f5a040,#c06010)",
  "linear-gradient(135deg,#d04060,#901030)",
  "linear-gradient(135deg,#3ab870,#1a7840)",
  "linear-gradient(135deg,#9060d0,#5030a0)",
  "linear-gradient(135deg,#3090c0,#106080)"
];

function avatarColor(sender) {
  let h = 0;
  for (const c of (sender || "")) h = (h * 31 + c.charCodeAt(0)) % AVATAR_COLORS.length;
  return AVATAR_COLORS[h];
}

function serviceColor(s) { return avatarColor(s); }

function badgeClass(e) {
  if (e.is_phishing)            return "badge-phishing";
  if (e.is_spam)                return "badge-spam";
  if (e.category === "otp")     return "badge-otp";
  if (e.category === "travel")  return "badge-ticket";
  if (e.category === "work")    return "badge-work";
  if (e.is_subscription)        return "badge-promo";
  if (e.priority === 1)         return "badge-important";
  return "badge-promo";
}

function badgeLabel(e) {
  if (e.is_phishing)            return "PHISHING";
  if (e.is_spam)                return "SPAM";
  if (e.category === "otp")     return "OTP";
  if (e.category === "travel")  return "TICKET";
  if (e.category === "work")    return "WORK";
  if (e.is_subscription)        return "PROMO";
  if (e.priority === 1)         return "IMPORTANT";
  return "PROMO";
}

function formatOTP(code) {
  return String(code).replace(/(\d{3})(\d{3})/, "$1 $2");
}

function showToast() {
  const t = document.getElementById("copy-toast");
  if (!t) return;
  t.classList.remove("hidden");
  setTimeout(() => t.classList.add("hidden"), 2500);
}

function flash(msg) { alert(msg); }