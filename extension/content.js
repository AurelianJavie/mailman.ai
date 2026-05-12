// content.js
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