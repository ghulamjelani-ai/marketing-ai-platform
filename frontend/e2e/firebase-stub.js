// E2E only: replaces src/firebase/firebase.js and the "firebase/auth" package, so the
// browser tests sign in without Google or Firebase. The test page sets
// window.__e2eGoogle to "ok", "cancel", "unverified", "blocked", "unauthorized" or
// "exists" before clicking "Google". Emails containing "taken" are already registered.
// window.__e2eCalls counts the calls, so tests can check double clicks.

const KEY = "e2e_user";
const REDIRECT_KEY = "e2e_redirect_pending";

window.__e2eCalls = { createUser: 0, popup: 0, redirect: 0 };

function authError(code) {
  const error = new Error(`Firebase: Error (${code}).`);
  error.code = code;
  return error;
}
const listeners = new Set();

function load() {
  try {
    return JSON.parse(sessionStorage.getItem(KEY) || "null");
  } catch {
    return null;
  }
}

function makeUser(data) {
  const user = {
    ...data,
    // Like Firebase, a cached token keeps the old name until it is refreshed,
    // and updateProfile changes this same user object in place.
    getIdToken: async (forceRefresh) => {
      if (forceRefresh) user.tokenName = user.displayName || "";
      return `e2e:${user.provider}:${user.authTime}:${user.uid}:${user.email}:${encodeURIComponent(user.tokenName || "")}`;
    },
  };

  return user;
}

const saved = load();

export const auth = { currentUser: saved ? makeUser(saved) : null };
export const googleProvider = { providerId: "google.com" };

export class GoogleAuthProvider {}
export const getAuth = () => auth;

function setUser(data) {
  if (data) {
    sessionStorage.setItem(KEY, JSON.stringify(data));
  } else {
    sessionStorage.removeItem(KEY);
  }

  auth.currentUser = data ? makeUser(data) : null;
  listeners.forEach((callback) => callback(auth.currentUser));
}

export function onAuthStateChanged(_auth, callback) {
  listeners.add(callback);
  setTimeout(() => callback(auth.currentUser), 0);
  return () => listeners.delete(callback);
}

function googleUser(mode) {
  const email = mode === "unverified" ? "unverified.owner@gmail.com" : "owner@gmail.com";
  return {
    uid: "google-owner",
    email,
    displayName: "Google Owner",
    photoURL: null,
    provider: "google.com",
    authTime: Date.now(),
    tokenName: "Google Owner",
  };
}

export async function signInWithPopup() {
  window.__e2eCalls.popup += 1;
  const mode = window.__e2eGoogle || "ok";

  if (mode === "cancel") throw authError("auth/popup-closed-by-user");
  if (mode === "blocked") throw authError("auth/popup-blocked");
  if (mode === "unauthorized") throw authError("auth/unauthorized-domain");
  if (mode === "exists") throw authError("auth/account-exists-with-different-credential");

  setUser(googleUser(mode));
  return { user: auth.currentUser };
}

// Pretends to leave for Google and come back signed in.
export async function signInWithRedirect() {
  window.__e2eCalls.redirect += 1;
  sessionStorage.setItem(REDIRECT_KEY, "1");
  sessionStorage.setItem(KEY, JSON.stringify(googleUser("ok")));
  window.location.reload();
  return new Promise(() => {});
}

export async function getRedirectResult() {
  if (!sessionStorage.getItem(REDIRECT_KEY)) return null;

  sessionStorage.removeItem(REDIRECT_KEY);
  return { user: auth.currentUser };
}

export async function signInWithEmailAndPassword(_auth, email) {
  if (!navigator.onLine) throw authError("auth/network-request-failed");

  setUser({
    uid: "pw-" + email.replace(/\W/g, ""),
    email,
    displayName: "E2E Tester",
    photoURL: null,
    provider: "password",
    authTime: Date.now(),
  });

  return { user: auth.currentUser };
}

export async function createUserWithEmailAndPassword(_auth, email, password) {
  window.__e2eCalls.createUser += 1;
  await new Promise((resolve) => setTimeout(resolve, 300));

  if (!navigator.onLine) throw authError("auth/network-request-failed");
  if (email.includes("taken")) throw authError("auth/email-already-in-use");
  if (password.length < 6) throw authError("auth/weak-password");

  return signInWithEmailAndPassword(_auth, email);
}

export async function updateProfile(user, { displayName }) {
  const data = JSON.parse(sessionStorage.getItem(KEY));
  data.displayName = displayName;
  sessionStorage.setItem(KEY, JSON.stringify(data));
  // Like Firebase: the same user object changes, so a token refreshed on it is kept.
  Object.assign(user, { displayName });
}

export async function signOut() {
  setUser(null);
}
