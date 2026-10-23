import apiClient from "./client";
import { auth } from "../firebase/firebase";

async function readErrorMessage(error) {
  const data = error.response?.data;

  // Errors arrive as a Blob because the request asks for an image response.
  if (data instanceof Blob) {
    try {
      const body = JSON.parse(await data.text());

      if (typeof body?.detail === "string") return body.detail;
      if (body?.detail?.message) return body.detail.message;
    } catch {
      // fall through to the generic message
    }
  }

  return error.message || "Image generation failed.";
}

// Generates one image from a text prompt and returns it as a File,
// so it can be previewed and published like an uploaded photo.
export async function generateImage(prompt) {
  const currentUser = auth.currentUser;

  if (!currentUser) {
    throw new Error("Firebase user not found. Please login again.");
  }

  const token = await currentUser.getIdToken();

  try {
    const response = await apiClient.post(
      "/images/generate",
      { prompt },
      {
        responseType: "blob",
        timeout: 150000,
        headers: {
          Authorization: `Bearer ${token}`,
        },
      },
    );

    const type = response.data.type || "image/png";
    const extension = type.split("/")[1] || "png";

    return new File([response.data], `ai-generated-image.${extension}`, {
      type,
    });
  } catch (error) {
    throw new Error(await readErrorMessage(error), { cause: error });
  }
}
