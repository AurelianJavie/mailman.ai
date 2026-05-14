// content.js

chrome.runtime.onMessage.addListener((msg, sender, respond) => {
  if (msg.type === "GET_EMAIL_LIST") {
    respond(collectEmailsFromDOM());
    return true;
  }
  if (msg.type === "DO_COPY") {
    navigator.clipboard.writeText(msg.code).catch(() => {});
    return true;
  }
});

function collectEmailsFromDOM() {
  const rows = document.querySelectorAll("tr.zA");
  const results = [];
  rows.forEach(row => {
    const id      = row.getAttribute("data-thread-id") || row.id || "";
    const sender  = row.querySelector(".yP, .zF")?.innerText || "";
    const subject = row.querySelector(".bog span, .y6 span")?.innerText
                 || row.querySelector(".bog, .y6")?.innerText || "";
    const snippet = row.querySelector(".y2")?.innerText || "";

    // Pull cached classification if we stored it
    const cached = emailClassCache[id] || {};
    results.push({ id, sender, subject, snippet, ...cached });
  });
  return results;
}


const emailClassCache = {};

console.log("content.js injected into", window.location.href);

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  console.log("Message received in content.js:", message);

  if (message && message.type === "GET_EMAIL_INFO") {
    const info = getCurrentEmailInfo();
    console.log("Email info prepared in content.js:", info);
    sendResponse(info);
    return true;
  }
});
function getCurrentEmailInfo() {
  const subject =
    document.querySelector("h2[data-legacy-thread-id]")?.innerText ||
    document.querySelector("h2.hP")?.innerText || // older class
    "";

  const sender =
    document.querySelector("span[email]")?.getAttribute("email") ||
    document.querySelector("span[aria-hidden='true']")?.innerText ||
    "unknown@sender.com";

  const bodyElement =
    document.querySelector("div[role='listitem'] div[dir='ltr']") ||
    document.querySelector("div.a3s"); // Gmail body container fallback

  const body = bodyElement?.innerText || "No body found";

  return { subject, sender, body };
}