const PCE_BASE_URL = "http://127.0.0.1:8766";

const statusEl = document.getElementById("status")!;
const resultEl = document.getElementById("result")!;
const saveBtn = document.getElementById("saveBtn") as HTMLButtonElement;

async function checkServer() {
  try {
    const res = await fetch(`${PCE_BASE_URL}/healthz`);
    if (res.ok) {
      statusEl.textContent = "Server: connected";
      statusEl.style.color = "#2e7d32";
    } else {
      throw new Error();
    }
  } catch {
    statusEl.textContent = "Server: not running";
    statusEl.style.color = "#c62828";
    saveBtn.disabled = true;
  }
}

saveBtn.addEventListener("click", async () => {
  saveBtn.disabled = true;
  saveBtn.textContent = "Saving...";

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab.id || !tab.url) {
    resultEl.textContent = "Cannot access this page.";
    return;
  }

  // Ask content script to extract
  const extracted = await chrome.tabs.sendMessage(tab.id, { type: "EXTRACT" });

  // Send to PCE
  chrome.runtime.sendMessage({
    type: "SAVE_PAGE",
    tabId: tab.id,
    url: extracted.url,
    title: extracted.title,
    body: extracted.body,
  }, (res) => {
    if (res?.ok) {
      resultEl.textContent = "Saved!";
    } else {
      resultEl.textContent = "Error saving page.";
    }
    saveBtn.textContent = "Save this page";
    saveBtn.disabled = false;
  });
});

checkServer();
