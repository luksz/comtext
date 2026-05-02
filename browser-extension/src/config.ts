export const PCE_BASE_URL = "http://127.0.0.1:8766";

export const DOMAIN_BLOCKLIST = new Set([
  "chase.com", "bankofamerica.com", "wellsfargo.com",
  "accounts.google.com", "login.microsoftonline.com",
  "mychart.com", "patientgateway.org",
]);

// Minimum time on page before we auto-capture (ms)
export const DWELL_THRESHOLD_MS = 15_000;

export function isBlocked(url: string): boolean {
  try {
    const host = new URL(url).hostname.replace(/^www\./, "");
    return [...DOMAIN_BLOCKLIST].some(d => host === d || host.endsWith("." + d));
  } catch {
    return true;
  }
}
