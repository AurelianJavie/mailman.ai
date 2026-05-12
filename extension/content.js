// content.js
console.log("content.js injected into", window.location.href);

function getCurrentEmailInfo() {
  const sender =
    document.querySelector("span[email]")?.getAttribute("email") ||
    document.querySelector("span[aria-hidden='true']")?.innerText ||
    "unknown@sender.com";

  const body =
    document.querySelector("div[role='listitem'] div[dir='ltr']")?.innerText ||
    document.body.innerText.slice(0, 1000) ||
    "No body found";

  return { sender, body };
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  console.log("Message received in content.js:", message);

  if (message && message.type === "GET_EMAIL_INFO") {
    const info = getCurrentEmailInfo();
    console.log("Email info prepared in content.js:", info);
    sendResponse(info);
    return true;
  }
});
