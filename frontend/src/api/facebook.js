import { API_BASE_URL, authHeaders, parseResponse } from "./config";
import { clearConnecting, markConnecting } from "../utils/facebookConnect";

// Opens the Facebook dialog in a small window so this page stays where it is (and Back keeps
// working). Returns "popup", or "redirect" when the browser blocked the window and the whole
// page is leaving for Facebook instead.
export async function connectFacebook() {
  // Must open straight from the click, before any waiting, or browsers block it.
  const popup = window.open("", "fb-connect", "width=640,height=780");

  try {
    const response = await fetch(`${API_BASE_URL}/facebook/connect-url`, {
      headers: await authHeaders(),
    });

    const data = await parseResponse(response);

    if (!data?.connect_url) {
      throw new Error("Facebook connection URL was not returned.");
    }

    if (popup && !popup.closed) {
      markConnecting();
      popup.location.href = data.connect_url;
      popup.focus();
      return "popup";
    }

    window.location.href = data.connect_url;
    return "redirect";
  } catch (error) {
    clearConnecting();
    popup?.close();
    throw error;
  }
}

export async function getFacebookStatus() {
  const response = await fetch(`${API_BASE_URL}/facebook/status`, {
    headers: await authHeaders(),
  });

  return parseResponse(response);
}

// The optional idempotency key makes a repeated request (double click, retry) publish only once.
const keyHeader = (idempotencyKey) =>
  idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {};

export async function publishFacebookPost(message, { idempotencyKey } = {}) {
  const response = await fetch(`${API_BASE_URL}/facebook/publish`, {
    method: "POST",

    headers: {
      "Content-Type": "application/json",
      ...keyHeader(idempotencyKey),
      ...(await authHeaders()),
    },

    body: JSON.stringify({
      message,
    }),
  });

  return parseResponse(response);
}

export async function publishFacebookPhoto(message, image, { idempotencyKey } = {}) {
  const formData = new FormData();

  formData.append("message", message || "");

  formData.append("image", image);

  const response = await fetch(`${API_BASE_URL}/facebook/publish-photo`, {
    method: "POST",
    headers: { ...keyHeader(idempotencyKey), ...(await authHeaders()) },
    body: formData,
  });

  return parseResponse(response);
}

export async function disconnectFacebook() {
  const response = await fetch(`${API_BASE_URL}/facebook/disconnect`, {
    method: "POST",
    headers: await authHeaders(),
  });

  return parseResponse(response);
}

// Every Page saved when Facebook was connected; `selected` is the one posts go to.
export async function getFacebookPages() {
  const response = await fetch(`${API_BASE_URL}/facebook/pages`, {
    headers: await authHeaders(),
  });

  return parseResponse(response);
}

export async function selectFacebookPage(pageId) {
  const response = await fetch(`${API_BASE_URL}/facebook/select-page`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await authHeaders()) },
    body: JSON.stringify({ page_id: pageId }),
  });

  return parseResponse(response);
}
