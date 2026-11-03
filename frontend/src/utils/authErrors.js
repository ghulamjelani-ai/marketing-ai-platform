import { passwordProblem } from "./passwordRules";

// Turns Firebase and backend sign-in errors into messages people can act on.
// Raw texts such as "Firebase: Error (auth/email-already-in-use)." are never shown.

const MESSAGES = {
  "auth/email-already-in-use":
    "This email is already registered. Log in instead, or continue with Google.",
  "auth/invalid-email": "Please enter a valid email address.",
  "auth/missing-email": "Please enter your email address.",
  "auth/weak-password": "Please choose a stronger password (see the checklist under the password).",
  "auth/missing-password": "Please enter your password.",
  "auth/network-request-failed":
    "No connection. Check your internet and try again.",
  "auth/too-many-requests":
    "Too many attempts. Please wait a few minutes and try again.",
  "auth/popup-closed-by-user": "Google sign-in was cancelled.",
  "auth/cancelled-popup-request": "Google sign-in was cancelled.",
  "auth/user-cancelled": "Google sign-in was cancelled.",
  "auth/popup-blocked":
    "Your browser blocked the Google window. Allow pop-ups for this site, or try again.",
  "auth/account-exists-with-different-credential":
    "This email already has an account with a password. Log in with your password first.",
  "auth/operation-not-allowed":
    "This sign-in method is turned off in Firebase. Enable it in the Firebase Console (Authentication > Sign-in method).",
  "auth/unauthorized-domain":
    "This address is not allowed to use Google sign-in. Add it in the Firebase Console (Authentication > Settings > Authorized domains).",
  "auth/invalid-credential":
    "The email or password is not right. If you signed up with Google, use the Google button, or set a password with \"Forgot password?\".",
  "auth/wrong-password": "The email or password is not right.",
  "auth/user-not-found": "The email or password is not right.",
  "auth/user-disabled": "This account has been disabled.",
  "auth/invalid-login-credentials": "The email or password is not right.",
  "auth/user-token-expired":
    "Your sign-in expired (for example after a password change). Please log in again.",
  "auth/requires-recent-login": "For your safety, please log in again.",
  "auth/user-mismatch": "That is a different account. Please log in again.",
  "auth/internal-error": "Sign-in had a hiccup on Firebase's side. Please try again.",
  "auth/timeout": "Sign-in took too long. Check your connection and try again.",
  "auth/quota-exceeded": "Too many sign-ins right now. Please try again in a few minutes.",
  "auth/password-does-not-meet-requirements":
    "This password doesn't meet the password rules. Please choose a stronger one.",
  "auth/invalid-api-key":
    "Firebase is not set up correctly (VITE_FIREBASE_API_KEY in frontend/.env).",
};

const FALLBACK = "Something went wrong while signing in. Please try again.";

export function friendlyAuthError(error) {
  if (!error) return FALLBACK;

  if (MESSAGES[error.code]) return MESSAGES[error.code];

  // Our backend already answers with readable messages (error.code is like "OTP_WRONG").
  if (error.code && !String(error.code).startsWith("auth/") && error.message) {
    return error.message;
  }

  if (error instanceof TypeError || /failed to fetch|network/i.test(error.message || "")) {
    return "Could not reach the Marketing AI server. Make sure the backend is running and try again.";
  }

  if (String(error.code || "").startsWith("auth/") || /^Firebase:/.test(error.message || "")) {
    // Not shown to the user, but visible in the browser console for troubleshooting.
    console.warn("Unhandled sign-in error code:", error.code || error.message);
    return FALLBACK;
  }

  return error.message || FALLBACK;
}

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

// Checks the sign-up form before anything is sent to Firebase. Returns "" when fine.
export function validateSignup({ name, email, password, confirmPassword }) {
  if (!name.trim()) return "Please enter your name.";
  if (!email.trim()) return "Please enter your email address.";
  if (!EMAIL.test(email.trim())) return "Please enter a valid email address.";
  const weak = passwordProblem(password);
  if (weak) return weak;
  if (password !== confirmPassword) return "The passwords do not match.";
  return "";
}

export function validateLogin({ email, password }) {
  if (!EMAIL.test(email.trim())) return "Please enter a valid email address.";
  if (!password) return "Please enter your password.";
  return "";
}
