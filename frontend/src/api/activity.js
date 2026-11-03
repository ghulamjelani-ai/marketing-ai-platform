import { API_BASE_URL, authHeaders, parseResponse } from "./config";

async function get(path) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: await authHeaders(),
  });

  return parseResponse(response);
}

async function send(method, path, body) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers: {
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
      ...(await authHeaders()),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  return parseResponse(response);
}

// ---- published posts (history) ----
export const getPublishedPosts = () => get("/history/posts");

// ---- memory ----
export const getMemory = () => get("/memory");
export const saveMemory = (summary) => send("PUT", "/memory", { summary });
export const clearMemory = () => send("DELETE", "/memory");

// ---- chat conversations ----
export const listConversations = () => get("/chat/conversations");
export const deleteConversation = (id) =>
  send("DELETE", `/chat/conversations/${id}`);

// ---- 7-day automatic posting ----
export const draftWeekPlan = (description) =>
  send("POST", "/schedule/draft", { description, days: 7 });

export const getScheduled = () => get("/schedule");
export const cancelScheduled = (id) => send("DELETE", `/schedule/${id}`);
export const cancelAllScheduled = () => send("POST", "/schedule/cancel-all");
// Clears finished (published, cancelled or removed) entries from the list.
export const clearEarlier = (id) => send("DELETE", `/schedule/earlier/${id}`);
export const clearAllEarlier = () => send("POST", "/schedule/clear-earlier");

// Hands one post to Facebook with its publish time (an ISO string with a time zone).
export async function schedulePost({ message, runAt, image, idempotencyKey }) {
  const formData = new FormData();

  formData.append("message", message || "");
  formData.append("run_at", runAt);

  if (image) {
    formData.append("image", image);
  }

  const response = await fetch(`${API_BASE_URL}/schedule/post`, {
    method: "POST",
    headers: {
      ...(idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {}),
      ...(await authHeaders()),
    },
    body: formData,
  });

  return parseResponse(response);
}

// Changes a post that is still waiting. Only the fields that changed are sent:
// message, runAt (ISO with time zone), image (a File) or removeImage.
export async function updateScheduled(id, { message, runAt, image, removeImage }) {
  const formData = new FormData();

  if (message !== undefined) formData.append("message", message);
  if (runAt) formData.append("run_at", runAt);
  if (image) formData.append("image", image);
  if (removeImage) formData.append("remove_image", "true");

  const response = await fetch(`${API_BASE_URL}/schedule/${id}`, {
    method: "PUT",
    headers: await authHeaders(),
    body: formData,
  });

  return parseResponse(response);
}

// Suggested times to post. The browser time zone offset lets the backend answer in local time.
export const getBestTime = () =>
  get(`/schedule/best-time?tz_offset=${new Date().getTimezoneOffset()}`);

// One ready-to-publish post (caption, description, hashtags, image prompt) for the Autopilot.
export const autopilotPost = (request) =>
  send("POST", "/autopilot/post", { request });


// ---- email notifications about posts ----
export const getNotifications = () => get("/notifications");
export const saveNotificationSettings = (emailEnabled) =>
  send("PUT", "/notifications/settings", { email_enabled: emailEnabled });
export const sendTestEmail = () => send("POST", "/notifications/test");

// How the latest published posts performed (engagement from Facebook; kept 10 minutes).
export const getInsights = (refresh = false) => get(`/history/insights${refresh ? "?refresh=true" : ""}`);
