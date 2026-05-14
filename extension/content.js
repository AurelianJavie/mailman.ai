// content.js — MailMan.ai Gmail content script

console.log("[MailMan.ai] content.js injected into", window.location.href);

const emailClassCache = {};

// ─── Single unified message listener (Chrome only fires the first one!) ───────
chrome.runtime.onMessage.addListener((msg, sender, respond) => {
  console.log("[MailMan.ai] Message received in content.js:", msg);

  if (msg.type === "GET_EMAIL_LIST") {
    respond(collectEmailsFromDOM());
    return true;
  }

  if (msg.type === "GET_EMAIL_INFO") {
    const info = getCurrentEmailInfo();
    console.log("[MailMan.ai] Email info:", info);
    respond(info);
    return true;
  }

  if (msg.type === "DO_COPY") {
    navigator.clipboard.writeText(msg.code)
      .then(() => respond({ ok: true }))
      .catch(() => {
        // Fallback for when clipboard API is blocked
        const ta = document.createElement("textarea");
        ta.value = msg.code;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
        respond({ ok: true });
      });
    return true; // keep channel open for async respond
  }

  if (msg.type === "PING") {
    respond({ pong: true });
    return true;
  }
});

// ─── Collect all visible email rows from Gmail inbox DOM ─────────────────────
function collectEmailsFromDOM() {
  // Gmail uses tr.zA for inbox rows; works in both default and compact density
  const rows = document.querySelectorAll("tr.zA");
  const results = [];

  rows.forEach(row => {
    const id = row.getAttribute("data-thread-id") || row.id || "";

    // Sender: .yP = name shown, .zF = actual email address attr
    const senderEl = row.querySelector(".yP, .zF");
    const sender   = senderEl?.getAttribute("email") || senderEl?.innerText || "";

    // Subject: .bog holds subject span, .y6 is the subject cell
    const subject =
      row.querySelector(".bog span")?.innerText ||
      row.querySelector(".y6 span")?.innerText  ||
      row.querySelector(".bog")?.innerText       ||
      row.querySelector(".y6")?.innerText        || "";

    // Snippet: .y2 is the preview text next to subject
    const snippet = row.querySelector(".y2")?.innerText || "";

    // Date: .xW span or .bI
    const date =
      row.querySelector(".xW span")?.getAttribute("title") ||
      row.querySelector(".xW span")?.innerText ||
      "";

    // Is unread: tr.zA.zE = unread
    const unread = row.classList.contains("zE");

    const cached = emailClassCache[id] || {};
    results.push({ id, sender, subject, snippet, date, unread, ...cached });
  });

  return results;
}

// ─── Get info for the currently open/selected email ──────────────────────────
function getCurrentEmailInfo() {
  const subject =
    document.querySelector("h2.hP")?.innerText ||
    document.querySelector("h2[data-legacy-thread-id]")?.innerText ||
    document.querySelector(".ha h2")?.innerText || "";

  const senderEl = document.querySelector("span[email]");
  const sender   = senderEl?.getAttribute("email") || senderEl?.innerText || "";

  // Email body — try multiple known Gmail body containers
  const bodyEl =
    document.querySelector("div.a3s.aiL") ||          // primary body div
    document.querySelector("div.a3s") ||               // fallback
    document.querySelector("div[role='listitem'] div[dir='ltr']");
  const body = bodyEl?.innerText?.trim() || "";

  return { subject, sender, body };
}