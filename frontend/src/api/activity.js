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

// Hands one post to Facebook with its publish time (an ISO string with a time zone).
export async function schedulePost({ message, runAt, image }) {
  const formData = new FormData();

  formData.append("message", message || "");
  formData.append("run_at", runAt);

  if (image) {
    formData.append("image", image);
  }

  const response = await fetch(`${API_BASE_URL}/schedule/post`, {
    method: "POST",
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

