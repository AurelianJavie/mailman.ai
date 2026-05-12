// popup.js
console.log("popup.js loaded FINAL");

document.addEventListener("DOMContentLoaded", () => {
  console.log("popup DOM loaded");

  const analyzeBtn = document.getElementById("analyzeBtn");
  const listBtn = document.getElementById("listBtn");
  const resultEl = document.getElementById("result");
  const listResultEl = document.getElementById("listResult");

  if (!analyzeBtn || !listBtn || !resultEl || !listResultEl) {
    console.log("Some DOM elements not found in popup.html");
    return;
  }

  // ---- Analyze current Gmail email ----
  analyzeBtn.addEventListener("click", async () => {
    console.log("Analyze button clicked");
    resultEl.textContent = "Reading email from Gmail...";

    try {
      // 1) Active tab (should be Gmail)
      const [tab] = await chrome.tabs.query({
        active: true,
        currentWindow: true
      });

      if (!tab || !tab.id) {
        resultEl.textContent = "No active tab found.";
        return;
      }

      // 2) Ask content script for sender + body
      const emailInfo = await chrome.tabs.sendMessage(tab.id, {
        type: "GET_EMAIL_INFO"
      });

      if (!emailInfo || !emailInfo.sender || !emailInfo.body) {
        resultEl.textContent =
          "Could not read email. Please open an email in a Gmail tab.";
        return;
      }

      console.log("Email info from content script:", emailInfo);

      const payload = {
        sender: emailInfo.sender,
        body: emailInfo.body
      };

      // 3) Send to FastAPI
      const res = await fetch("http://127.0.0.1:8000/analyze", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify(payload)
      });

      const data = await res.json();
      console.log("Response from /analyze:", data);

      resultEl.textContent = JSON.stringify(data, null, 2);
    } catch (err) {
      console.error("Error in analyze flow:", err);
      resultEl.textContent = "Error: " + err;
    }
  });

  // ---- Show recent emails from backend ----
  listBtn.addEventListener("click", async () => {
    console.log("List button clicked");
    listResultEl.textContent = "Loading saved emails...";

    try {
      const res = await fetch("http://127.0.0.1:8000/list_emails");
      const data = await res.json();
      console.log("Response from /list_emails:", data);

      listResultEl.textContent = JSON.stringify(data, null, 2);
    } catch (err) {
      console.error("Error in list_emails flow:", err);
      listResultEl.textContent = "Error: " + err;
    }
  });
});
