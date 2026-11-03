// Password rules for new passwords (sign-up and reset). The backend checks the same
// rules for resets (backend/app/core/password_reset.py).

export const PASSWORD_RULES = [
  { label: "At least 8 characters", test: (p) => p.length >= 8, need: "at least 8 characters" },
  { label: "A capital letter (A-Z)", test: (p) => /[A-Z]/.test(p), need: "a capital letter" },
  { label: "A small letter (a-z)", test: (p) => /[a-z]/.test(p), need: "a small letter" },
  { label: "A number (0-9)", test: (p) => /[0-9]/.test(p), need: "a number" },
  { label: "A special character (! @ # $ ...)", test: (p) => /[^A-Za-z0-9]/.test(p), need: "a special character such as ! @ # $" },
];

// "" when the password is strong enough, otherwise one sentence saying what is missing.
export function passwordProblem(password) {
  const missing = PASSWORD_RULES.filter((rule) => !rule.test(password)).map((rule) => rule.need);

  if (!missing.length) return "";

  const last = missing.pop();
  return `Your password needs ${missing.length ? missing.join(", ") + " and " : ""}${last}.`;
}
