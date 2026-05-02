/**
 * Content script — injected into every page.
 * Listens for extraction requests from the background worker.
 */
chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === "EXTRACT") {
    const article = document.querySelector("article, main, [role=main]");
    const el = (article ?? document.body) as HTMLElement;
    sendResponse({
      title: document.title,
      body: el.innerText.slice(0, 50_000),
      url: location.href,
    });
  }
});
