// Connecting Facebook happens in a small window, so the page the user is on never leaves
// and the browser's Back button keeps working. The small window comes back to this app at
// /home?facebook=connected|error&pages=N; it tells the main window through a BroadcastChannel
// and closes itself. Both windows share one origin, so localStorage and the channel work
// even when Facebook's own pages cut the link between the two windows (window.opener).

export const CHANNEL = "marketing-ai-facebook";
const FLAG = "marketing_ai_facebook_connecting";
const MAX_AGE_MS = 10 * 60 * 1000;

function storage() {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function markConnecting(now = Date.now()) {
  storage()?.setItem(FLAG, String(now));
}

export function clearConnecting() {
  storage()?.removeItem(FLAG);
}

// True while a connect window opened by this browser is expected to come back.
export function isConnecting(now = Date.now()) {
  const stored = Number(storage()?.getItem(FLAG));

  return Number.isFinite(stored) && stored > 0 && now - stored < MAX_AGE_MS;
}

// What the redirect back to the app says, or null when the address is not that redirect.
export function readFacebookResult(search) {
  const params = new URLSearchParams(search);
  const result = params.get("facebook");

  if (result !== "connected" && result !== "error") return null;

  return { result, pages: Math.max(1, Number(params.get("pages") || 1) || 1) };
}

export function announceFacebookResult(payload) {
  if (typeof BroadcastChannel === "undefined") return;

  const channel = new BroadcastChannel(CHANNEL);
  channel.postMessage(payload);
  channel.close();
}
