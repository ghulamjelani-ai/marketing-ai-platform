import { API_BASE_URL, authHeaders, parseResponse } from "./config";

export async function connectFacebook() {
  const response = await fetch(`${API_BASE_URL}/facebook/connect-url`, {
    headers: await authHeaders(),
  });

  const data = await parseResponse(response);

  if (!data?.connect_url) {
    throw new Error("Facebook connection URL was not returned.");
  }

  window.location.href = data.connect_url;
}

export async function getFacebookStatus() {
  const response = await fetch(`${API_BASE_URL}/facebook/status`, {
    headers: await authHeaders(),
  });

  return parseResponse(response);
}

export async function publishFacebookPost(message) {
  const response = await fetch(`${API_BASE_URL}/facebook/publish`, {
    method: "POST",

    headers: {
      "Content-Type": "application/json",
      ...(await authHeaders()),
    },

    body: JSON.stringify({
      message,
    }),
  });

  return parseResponse(response);
}

export async function publishFacebookPhoto(message, image) {
  const formData = new FormData();

  formData.append("message", message || "");

  formData.append("image", image);

  const response = await fetch(`${API_BASE_URL}/facebook/publish-photo`, {
    method: "POST",
    headers: await authHeaders(),
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
