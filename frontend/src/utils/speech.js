// Reading AI replies aloud with the browser's own voices (free, nothing is uploaded).

export const canSpeak = () => Boolean(globalThis.speechSynthesis && globalThis.SpeechSynthesisUtterance);

const URDU = /[؀-ۿ]/; // Arabic script, used for Urdu

// Turns a chat reply into something pleasant to listen to: no markdown, links or
// hashtags, and long plans are cut at a sentence with a pointer to the screen.
export function speakableText(text, limit = 600) {
  let clean = String(text || "")
    .replace(/https?:\/\/\S+/g, "")
    .replace(/#[\p{L}\p{N}_]+/gu, "")
    .replace(/[*_`>#|]+/g, "")
    .replace(/^\s*[-•]\s+/gm, "")
    .replace(/\s*\n+\s*/g, ". ")
    .replace(/\.\s*\./g, ".")
    .replace(/\s{2,}/g, " ")
    .trim();

  if (clean.length > limit) {
    const cut = clean.slice(0, limit);
    const end = Math.max(cut.lastIndexOf(". "), cut.lastIndexOf("? "), cut.lastIndexOf("! "), cut.lastIndexOf("۔ "));
    clean = (end > limit / 3 ? cut.slice(0, end + 1) : cut) + " The full answer is on your screen.";
  }

  return clean;
}

function pickVoice(lang) {
  const voices = globalThis.speechSynthesis.getVoices();
  const prefix = lang.slice(0, 2);
  const matching = voices.filter((voice) => voice.lang?.toLowerCase().startsWith(prefix));

  // Natural-sounding voices first when the system has them.
  return matching.find((voice) => /natural|neural|google|online/i.test(voice.name)) || matching[0] || null;
}

export function stopSpeaking() {
  if (canSpeak()) globalThis.speechSynthesis.cancel();
}

// Speaks text; onEnd runs when it finishes, is stopped or fails.
export function speak(text, onEnd = () => {}) {
  if (!canSpeak()) return false;

  const words = speakableText(text);
  if (!words) return false;

  globalThis.speechSynthesis.cancel();

  const utterance = new SpeechSynthesisUtterance(words);
  utterance.lang = URDU.test(words) ? "ur-PK" : "en-US";
  utterance.voice = pickVoice(utterance.lang);
  utterance.rate = 1;
  utterance.pitch = 1;
  utterance.onend = onEnd;
  utterance.onerror = onEnd;

  globalThis.speechSynthesis.speak(utterance);
  return true;
}
