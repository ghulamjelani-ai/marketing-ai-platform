import { auth } from "../firebase/firebase";

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

// Every backend call that belongs to a user carries the Firebase ID token.
export async function authHeaders() {
  const currentUser = auth.currentUser;

  if (!currentUser) {
    throw new Error("Firebase user not found. Please login again.");
  }

  const token = await currentUser.getIdToken();

  return { Authorization: `Bearer ${token}` };
}

export async function parseResponse(response) {
  let data;

  try {
    data = await response.json();
  } catch {
    data = null;
  }

  if (!response.ok) {
    let errorMessage = "Something went wrong.";

    if (typeof data?.detail === "string") {
      errorMessage = data.detail;
    } else if (data?.detail?.message) {
      errorMessage = data.detail.message;
    } else if (data?.message) {
      errorMessage = data.message;
    }

    throw new Error(errorMessage);
  }

  return data;
}
