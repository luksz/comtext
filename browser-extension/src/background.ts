/**
 * Background service worker.
 * - Listens for tab focus changes and tracks dwell time.
 * - After DWELL_THRESHOLD_MS, asks the content script to extract the page.
 * - Sends extracted content to the PCE backend.
 */
import { PCE_BASE_URL, DWELL_THRESHOLD_MS, isBlocked } from "./config";

interface DwellRecord {
  tabId: number;
  url: string;
  startedAt: number;
  timer: ReturnType<typeof setTimeout>;
}

let active: DwellRecord | null = null;

function clearActive() {
  if (active) {
    clearTimeout(active.timer);
    active = null;
  }
}

async function sendToPCE(url: string, title: string, body: string) {
  try {
    await fetch(`${PCE_BASE_URL}/ingest/browser`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, title, body }),
    });
  } catch {
    // Server may not be running — fail silently in background
  }
}

async function triggerExtraction(tabId: number, url: string) {
  try {
    const results = await chrome.scripting.executeScript({
      target: { tabId },
      func: () => {
        // Inline Readability-lite: grab main text content
        const article = document.querySelector("article, main, [role=main]");
        const el = article ?? document.body;
        return {
          title: document.title,
          body: el.innerText.slice(0, 50_000),
        };
      },
    });
    const { title, body } = results[0].result as { title: string; body: string };
    if (body.trim().length > 100) {
      await sendToPCE(url, title, body);
    }
  } catch {
    // Tab may have navigated away — ignore
  }
}

function startDwell(tabId: number, url: string) {
  clearActive();
  if (!url.startsWith("http") || isBlocked(url)) return;

  const timer = setTimeout(() => triggerExtraction(tabId, url), DWELL_THRESHOLD_MS);
  active = { tabId, url, startedAt: Date.now(), timer };
}

// Track tab focus changes
chrome.tabs.onActivated.addListener(async ({ tabId }) => {
  const tab = await chrome.tabs.get(tabId);
  if (tab.url) startDwell(tabId, tab.url);
});

// Track navigation within a tab
chrome.tabs.onUpdated.addListener((tabId, change, tab) => {
  if (change.status === "complete" && tab.active && tab.url) {
    startDwell(tabId, tab.url);
  }
});

// Track history additions (catches SPA navigation)
chrome.history.onVisited.addListener(({ url }) => {
  if (!url || isBlocked(url)) return;
  chrome.tabs.query({ active: true, currentWindow: true }, ([tab]) => {
    if (tab?.id && tab.url === url) startDwell(tab.id, url);
  });
});

// Listen for manual save from popup
chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === "SAVE_PAGE") {
    const { tabId, url, title, body } = msg;
    sendToPCE(url, title, body).then(() => sendResponse({ ok: true }));
    return true; // async response
  }
});
