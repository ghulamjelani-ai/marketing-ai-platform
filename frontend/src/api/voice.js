import { API_BASE_URL, authHeaders, parseResponse } from "./config";

const EXTENSION = { "audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "mp4", "audio/mpeg": "mp3", "audio/wav": "wav" };

// Sends a voice recording to the backend and returns the words that were said.
export async function transcribeAudio(blob) {
  const type = (blob.type || "audio/webm").split(";")[0];
  const formData = new FormData();

  formData.append("audio", blob, `voice.${EXTENSION[type] || "webm"}`);

  const response = await fetch(`${API_BASE_URL}/voice/transcribe`, {
    method: "POST",
    headers: await authHeaders(),
    body: formData,
  });

  const data = await parseResponse(response);
  return data.text;
}
