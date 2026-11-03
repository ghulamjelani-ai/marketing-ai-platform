import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import AuthLayout from "../components/AuthLayout";
import PasswordInput from "../components/PasswordInput";
import PasswordHints from "../components/PasswordHints";
import { API_BASE_URL, parseResponse } from "../api/config";
import { friendlyAuthError } from "../utils/authErrors";
import { passwordProblem } from "../utils/passwordRules";
import { toast } from "../utils/toast";

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

async function post(path, body) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  return parseResponse(response);
}

// Forgot password: a 6-digit code is emailed to the account, then a new password is set.
export default function ForgotPassword() {
  const navigate = useNavigate();
  const location = useLocation();

  const [email, setEmail] = useState(location.state?.email || "");
  const [step, setStep] = useState("email");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [resendAt, setResendAt] = useState(0);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  const resendIn = Math.max(0, Math.ceil((resendAt - now) / 1000));

  async function sendCode(event) {
    event?.preventDefault();
    if (busy || resendIn > 0) return;

    if (!EMAIL.test(email.trim())) {
      setError("Please enter a valid email address.");
      return;
    }

    setBusy(true);
    setError("");

    try {
      const reply = await post("/auth/password/forgot", { email: email.trim() });
      setResendAt(Date.now() + (reply.resend_in || 60) * 1000);
      setNotice(reply.message);
      setStep("code");
      toast.info("Check your email", "Your 6-digit code is on its way.");
    } catch (err) {
      setError(friendlyAuthError(err));
    } finally {
      setBusy(false);
    }
  }

  async function resetPassword(event) {
    event.preventDefault();
    if (busy) return;

    if (!/^\d{6}$/.test(code)) {
      setError("Enter the 6-digit code from the email.");
      return;
    }

    const weak = passwordProblem(password);

    if (weak) {
      setError(weak);
      return;
    }

    if (password !== confirm) {
      setError("The passwords do not match.");
      return;
    }

    setBusy(true);
    setError("");

    try {
      const reply = await post("/auth/password/reset", {
        email: email.trim(),
        code,
        new_password: password,
      });

      toast.success("Password changed", "Log in with your new password.");
      navigate("/login", { state: { email: email.trim(), notice: reply.message } });
    } catch (err) {
      setError(friendlyAuthError(err));
      setCode("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthLayout
      title="Reset your password"
      error={error}
      notice={step === "code" ? notice : ""}
      subtitle={
        <>
          Remembered it? <Link to="/login" state={{ email: email.trim() }}>Log in</Link>
        </>
      }
    >
      {step === "email" ? (
        <form onSubmit={sendCode} className="au-form" noValidate>
          <p className="au-notice !mt-0">
            Enter the email you log in with. We&rsquo;ll send a 6-digit code to it.
          </p>

          <input
            type="email"
            placeholder="Email Address"
            className="au-input"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            autoFocus
          />

          <button type="submit" disabled={busy} className="au-btn">
            {busy ? "Sending..." : "Send code"}
          </button>
        </form>
      ) : (
        <form onSubmit={resetPassword} className="au-form" noValidate>
          <input
            type="text"
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            placeholder="6-digit code"
            aria-label="6-digit code"
            className="au-input au-otp"
            value={code}
            onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
            autoFocus
          />

          <PasswordInput
            placeholder="New Password"
            autoComplete="new-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />

          <PasswordInput
            placeholder="Confirm New Password"
            autoComplete="new-password"
            value={confirm}
            onChange={(event) => setConfirm(event.target.value)}
          />

          <PasswordHints password={password} confirm={confirm} />

          <button type="submit" disabled={busy} className="au-btn">
            {busy ? "Saving..." : "Set new password"}
          </button>

          <div className="au-otp-actions !mt-0">
            <button
              type="button"
              className="au-link"
              onClick={() => sendCode()}
              disabled={busy || resendIn > 0}
            >
              {resendIn > 0 ? `Send a new code in ${resendIn}s` : "Send a new code"}
            </button>
            <button
              type="button"
              className="au-link"
              onClick={() => {
                setStep("email");
                setError("");
                setCode("");
              }}
              disabled={busy}
            >
              Use another email
            </button>
          </div>
        </form>
      )}
    </AuthLayout>
  );
}
