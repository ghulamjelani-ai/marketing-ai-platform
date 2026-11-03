// Same rules as backend/app/core/topic_check.py. The backend checks again, so this
// only gives the user a quick answer before anything is sent.

export const MIN_LENGTH = 10;
export const MAX_LENGTH = 500;

export const TOPIC_EXAMPLE =
  "Please describe your post topic in words, for example: 'Summer sale on running shoes'.";

const TAG = /<\s*\/?\s*[a-zA-Z][^>]*>/;
const LETTER = /\p{L}/u;
const LETTERS_ONLY = /^\p{L}+$/u;
const EDGE_PUNCT = /^[.,!?;:'"()[\]{}\-–—…،۔؟]+|[.,!?;:'"()[\]{}\-–—…،۔؟]+$/g;
const VOWELS = /[aeiouy]/;
const KEYBOARD_ROWS = ["qwertyuiop", "asdfghjkl", "zxcvbnm", "1234567890"];

function looksLikeWord(word) {
  if ([...word].length < 2) return false;

  if (!/^[a-z]+$/.test(word)) {
    // Urdu and other scripts: any alphabetic token of two or more letters.
    return new Set(word).size > 1;
  }

  if (new Set(word).size === 1) return false;
  if (/(.)\1\1/.test(word)) return false;
  if (!VOWELS.test(word)) return word.length <= 3;
  if (/[^aeiouy]{5,}/.test(word)) return false;
  if (word.length >= 4 && KEYBOARD_ROWS.some((row) => row.includes(word))) return false;

  if (word.length >= 7) {
    const vowels = [...word].filter((ch) => VOWELS.test(ch)).length;
    if (vowels / word.length < 0.25) return false;
  }

  return true;
}

// Returns "" when the topic is fine, otherwise a message to show under the textbox.
export function validateTopic(raw) {
  const text = (raw || "").split(/\s+/).filter(Boolean).join(" ");

  if (!text) return "Tell Autopilot what the post is about. " + TOPIC_EXAMPLE;

  if (text.length < MIN_LENGTH) {
    return `The topic is too short (at least ${MIN_LENGTH} characters). ` + TOPIC_EXAMPLE;
  }

  if (text.length > MAX_LENGTH) {
    return `The topic is too long (at most ${MAX_LENGTH} characters).`;
  }

  if (TAG.test(text)) return "HTML or script tags are not allowed. " + TOPIC_EXAMPLE;

  if (!LETTER.test(text)) {
    return "The topic has no words, only numbers, symbols or emoji. " + TOPIC_EXAMPLE;
  }

  const chars = [...text.toLowerCase()].filter((ch) => /[\p{L}\p{N}]/u.test(ch));
  if (new Set(chars).size <= 2) return "The topic is just repeated characters. " + TOPIC_EXAMPLE;

  const lettered = text
    .split(" ")
    .map((token) => token.replace(EDGE_PUNCT, "").toLowerCase())
    .filter((token) => LETTER.test(token));

  const words = lettered.filter((token) => LETTERS_ONLY.test(token) && looksLikeWord(token));

  if (words.length < 2 || words.length * 2 < lettered.length) {
    return "That does not look like real words. " + TOPIC_EXAMPLE;
  }

  return "";
}
