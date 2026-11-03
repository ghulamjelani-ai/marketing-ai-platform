import { useEffect, useRef, useState } from "react";
import {
  getRedirectResult,
  signInWithPopup,
  signInWithRedirect,
  signOut,
  onAuthStateChanged,
  createUserWithEmailAndPassword,
  signInWithEmailAndPassword,
  updateProfile,
} from "firebase/auth";
import { auth, googleProvider } from "../firebase/firebase";
import { API_BASE_URL } from "../api/config";
import { AuthContext } from "./useAuth";


const BACKEND_URL = API_BASE_URL;

function makeCleanUser(firebaseUser) {
  return {
    uid: firebaseUser.uid,
    name: firebaseUser.displayName,
    email: firebaseUser.email,
    photo: firebaseUser.photoURL,
    businessName: "My Business",
  };
}

// forceRefresh gets a new ID token, for example so it carries a name set just now.
async function syncUserWithBackend(firebaseUser, forceRefresh = false) {
  const token = await firebaseUser.getIdToken(forceRefresh);

  const response = await fetch(`${BACKEND_URL}/auth/sync`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    let errorMessage = "Failed to sync user with backend";

    let errorCode = "";

    try {
      const errorData = await response.json();

      if (errorData.error?.message) {
        errorMessage = errorData.error.message;
        errorCode = errorData.error.code || "";
      } else if (typeof errorData.detail === "string") {
        errorMessage = errorData.detail;
      } else if (errorData.detail?.message) {
        errorMessage = errorData.detail.message;
      }
    } catch {
      errorMessage = "Failed to sync user with backend";
    }

    const error = new Error(errorMessage);
    error.code = errorCode;
    throw error;
  }

  return await response.json();
}

// POST to an /auth/otp/* endpoint with the current Firebase token.
async function otpRequest(path, body) {
  const firebaseUser = auth.currentUser;

  if (!firebaseUser) {
    throw new Error("Your sign-in has ended. Please sign in with Google again.");
  }

  const response = await fetch(`${BACKEND_URL}/auth/otp/${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${await firebaseUser.getIdToken()}`,
    },
    body: JSON.stringify(body || {}),
  });

  const data = await response.json().catch(() => null);

  if (!response.ok) {
    const error = new Error(
      data?.error?.message ||
        (typeof data?.detail === "string" ? data.detail : "") ||
        "Something went wrong. Please try again.",
    );
    error.code = data?.error?.code || "";
    throw error;
  }

  return data;
}

// Every sign-in (email/password and Google) finishes with a 6-digit code sent to the
// account's email. Codes are never sent automatically: the code screen asks first.
// What that screen shows comes from the server (GET /auth/otp/status), so a reload or a
// closed tab comes back to the same state.

// These end the sign-in; for other errors the user stays on the code screen and can retry.
// Firebase codes that mean "this browser still holds a session that was ended".
const STALE_SESSION = new Set(["auth/user-token-expired", "auth/requires-recent-login", "auth/user-mismatch"]);

const OTP_FATAL = new Set(["EMAIL_NOT_VERIFIED", "OTP_NOT_NEEDED", "EMAIL_MISSING"]);

async function getOtpStatus() {
  const firebaseUser = auth.currentUser;

  if (!firebaseUser) {
    throw new Error("Your sign-in has ended. Please sign in again.");
  }

  const response = await fetch(`${BACKEND_URL}/auth/otp/status`, {
    headers: { Authorization: `Bearer ${await firebaseUser.getIdToken()}` },
  });
  const data = await response.json().catch(() => null);

  if (!response.ok) {
    const error = new Error(data?.error?.message || "Could not check your sign-in code.");
    error.code = data?.error?.code || "";
    throw error;
  }

  return data;
}

// Server status (seconds) -> screen state (times in ms since 1970).
function pendingFrom(status, purpose = "sign_in") {
  const now = Date.now();

  return {
    email: status.email,
    sent: Boolean(status.sent),
    expiresAt: status.sent ? now + status.expires_in * 1000 : 0,
    resendAt: now + (status.resend_in || 0) * 1000,
    lockedUntil: status.locked_for ? now + status.locked_for * 1000 : 0,
    purpose,
  };
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [authLoading, setAuthLoading] = useState(true);
  // Set while a sign-in waits for its email code (see pendingFrom).
  const [otpPending, setOtpPending] = useState(null);
  // A sign-in error that must survive the login page being swapped out (Google redirect,
  // or a code step that ended the sign-in). Shown by Login/Signup.
  const [signInError, setSignInError] = useState(null);
  // True while a login/sign-up button is finishing the sign-in itself, so the auth
  // listener below does not repeat the same backend calls at the same time.
  const signingInRef = useRef(false);

  const withSignIn = async (work) => {
    signingInRef.current = true;

    try {
      return await work();
    } finally {
      signingInRef.current = false;
    }
  };

  // After any Firebase sign-in: open the session if this sign-in is already confirmed,
  // otherwise show the code screen.
  const finishSignIn = async (firebaseUser, { forceRefresh = false, purpose = "sign_in" } = {}) => {
    try {
      await syncUserWithBackend(firebaseUser, forceRefresh);
      setUser(makeCleanUser(firebaseUser));
      setOtpPending(null);
      return { otpRequired: false };
    } catch (error) {
      if (error.code !== "OTP_REQUIRED") throw error;
    }

    setOtpPending(pendingFrom(await getOtpStatus(), purpose));
    return { otpRequired: true };
  };

  const refreshOtpStatus = async () => {
    const status = await getOtpStatus();
    setOtpPending((pending) => pendingFrom(status, pending?.purpose));
  };

  // EMAIL SIGNUP
  const signup = (name, email, password) => withSignIn(async () => {
    setSignInError(null);

    const result = await createUserWithEmailAndPassword(auth, email, password);

    await updateProfile(result.user, {
      displayName: name,
    });

    // A fresh token carries the new name, so the backend saves it.
    return finishSignIn(result.user, { forceRefresh: true, purpose: "sign_up" });
  });

  // EMAIL LOGIN
  const login = (email, password) => withSignIn(async () => {
    setSignInError(null);

    let result;

    try {
      result = await signInWithEmailAndPassword(auth, email, password);
    } catch (error) {
      if (!STALE_SESSION.has(error.code)) throw error;

      // An old session in this browser was ended (for example by a password reset):
      // clear it and try once more.
      await signOut(auth);
      result = await signInWithEmailAndPassword(auth, email, password);
    }

    return finishSignIn(result.user);
  });

  // GOOGLE (the same button signs up and logs in)
  const googleLogin = () => withSignIn(async () => {
    let result;
    setSignInError(null);

    try {
      result = await signInWithPopup(auth, googleProvider);
    } catch (error) {
      if (error.code === "auth/popup-blocked") {
        // The page leaves for Google and comes back; the auth listener continues.
        await signInWithRedirect(auth, googleProvider);
        return { otpRequired: true };
      }

      throw error;
    }

    return finishSignIn(result.user);
  });

  // Emails a code to the signed-in account's own address (the server picks the address).
  const sendOtp = async () => {
    try {
      const status = await otpRequest("send", { purpose: otpPending?.purpose || "sign_in" });
      setOtpPending((pending) => pendingFrom(status, pending?.purpose));
    } catch (error) {
      if (OTP_FATAL.has(error.code)) {
        await signOut(auth);
        setOtpPending(null);
        setSignInError(error);
      } else if (error.code === "OTP_COOLDOWN" || error.code === "OTP_LOCKED") {
        await refreshOtpStatus().catch(() => {});
      }

      throw error;
    }
  };

  const verifyOtp = async (code) => {
    try {
      await otpRequest("verify", { code });
    } catch (error) {
      if (error.code === "OTP_LOCKED" || error.code === "OTP_EXPIRED") {
        await refreshOtpStatus().catch(() => {});
      }

      throw error;
    }

    const firebaseUser = auth.currentUser;
    await syncUserWithBackend(firebaseUser);

    setUser(makeCleanUser(firebaseUser));
    setOtpPending(null);
  };

  const cancelOtp = async () => {
    await signOut(auth);
    setOtpPending(null);
  };

  // LOGOUT
  const logout = async () => {
    await signOut(auth);
    localStorage.removeItem("marketing_ai_conversation_id");
    setUser(null);
    setOtpPending(null);
  };

  // KEEP USER LOGGED IN (and restore an unfinished sign-in after a reload)
  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, async (firebaseUser) => {
      // A login button is already handling this sign-in (see withSignIn).
      if (firebaseUser && signingInRef.current) {
        setAuthLoading(false);
        return;
      }

      try {
        if (firebaseUser) {
          await syncUserWithBackend(firebaseUser);

          const cleanUser = makeCleanUser(firebaseUser);
          setUser(cleanUser);
        } else {
          setUser(null);
          setOtpPending(null);
        }
      } catch (error) {
        setUser(null);

        if (error.code === "OTP_REQUIRED") {
          // A sign-in whose code is not confirmed yet: the server says what was sent.
          if (auth.currentUser?.uid === firebaseUser.uid) {
            try {
              const status = await getOtpStatus();
              setOtpPending((pending) => pendingFrom(status, pending?.purpose));
            } catch (statusError) {
              console.error("Sign-in code status error:", statusError);
            }
          }
        } else {
          console.error("Auth state sync error:", error);
        }
      } finally {
        setAuthLoading(false);
      }
    });

    // Coming back from the Google redirect (used when the pop-up was blocked); the
    // listener above takes it from there.
    getRedirectResult(auth).catch((error) => setSignInError(error));

    return () => unsubscribe();
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        signup,
        login,
        googleLogin,
        sendOtp,
        verifyOtp,
        cancelOtp,
        otpPending,
        signInError,
        logout,
        authLoading,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}
