import { useEffect, useState } from "react";
import { useAuth } from "../context/useAuth";
import AuthLayout from "../components/AuthLayout";
import { friendlyAuthError } from "../utils/authErrors";
import { toast } from "../utils/toast";

const clock = (seconds) =>
  `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;

const secondsUntil = (time, now) => Math.max(0, Math.ceil(((time || 0) - now) / 1000));

// Shown after every sign-in until the 6-digit code from the email is confirmed.
// Nothing is sent until the user presses "Send code".
export default function VerifyOtp() {
  const { otpPending, sendOtp, verifyOtp, cancelOtp } = useAuth();

  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState("");
  const [verified, setVerified] = useState(false);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  const email = otpPending?.email || "your email";
  const expiresIn = secondsUntil(otpPending?.expiresAt, now);
  const codeLive = Boolean(otpPending?.sent) && expiresIn > 0;
  const resendIn = secondsUntil(otpPending?.resendAt, now);
  const lockedFor = secondsUntil(otpPending?.lockedUntil, now);

  async function send() {
    if (busy || resendIn > 0 || lockedFor > 0) return;

    setBusy("send");
    setError("");
    setNotice("");

    try {
      const resend = codeLive || Boolean(otpPending?.sent);
      await sendOtp();
      setCode("");
      toast.success(resend ? "New code sent" : "Code sent", `Check ${email}. It expires in 5 minutes.`);
      // The heading already says "Code sent to ..."; only a resend gets an extra note.
      setNotice(resend ? "A new code is on its way. Earlier codes no longer work." : "");
    } catch (err) {
      setError(friendlyAuthError(err));
    } finally {
      setBusy("");
    }
  }

  async function verify(value) {
    if (busy || !/^\d{6}$/.test(value) || lockedFor > 0) return;

    setBusy("verify");
    setError("");
    setNotice("");

    try {
      await verifyOtp(value);
      setVerified(true);
      toast.success("You're signed in", "Welcome to Marketing AI.");
    } catch (err) {
      setError(friendlyAuthError(err));
      setCode("");
    } finally {
      setBusy("");
    }
  }

  // Digits only, at most 6; a complete code is checked straight away (typed or pasted).
  function changeCode(raw) {
    const digits = raw.replace(/\D/g, "").slice(0, 6);
    setCode(digits);

    if (digits.length === 6) verify(digits);
  }

  let subtitle;

  if (verified) {
    subtitle = <>Verified. Opening your dashboard&hellip;</>;
  } else if (lockedFor > 0) {
    subtitle = <>Too many wrong codes. You can try again in {clock(lockedFor)}.</>;
  } else if (codeLive) {
    subtitle = (
      <>
        Code sent to <b>{email}</b>. It expires in {clock(expiresIn)}.
      </>
    );
  } else if (otpPending?.sent) {
    subtitle = (
      <>
        The code sent to <b>{email}</b> has expired. Send a new code.
      </>
    );
  } else {
    subtitle = (
      <>
        We&rsquo;ll send a 6-digit code to <b>{email}</b> to finish signing in.
      </>
    );
  }

  return (
    <AuthLayout title="Check your email" error={error} notice={notice} subtitle={subtitle}>
      {!codeLive && !verified ? (
        <div className="au-form">
          <button
            type="button"
            className="au-btn"
            onClick={send}
            disabled={Boolean(busy) || resendIn > 0 || lockedFor > 0}
          >
            {busy === "send"
              ? "Sending..."
              : resendIn > 0
                ? `Send code (${resendIn}s)`
                : "Send code"}
          </button>
        </div>
      ) : (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            verify(code);
          }}
          className="au-form"
        >
          <input
            type="text"
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            placeholder="6-digit code"
            aria-label="6-digit code"
            className="au-input au-otp"
            value={code}
            onChange={(event) => changeCode(event.target.value)}
            onPaste={(event) => {
              event.preventDefault();
              changeCode(event.clipboardData.getData("text"));
            }}
            disabled={Boolean(busy) || verified || lockedFor > 0}
            autoFocus
          />

          <button
            type="submit"
            disabled={code.length !== 6 || Boolean(busy) || verified || lockedFor > 0}
            className="au-btn"
          >
            {busy === "verify" ? "Checking..." : verified ? "Verified" : "Verify and continue"}
          </button>
        </form>
      )}

      <div className="au-otp-actions">
        {codeLive && !verified ? (
          <button
            type="button"
            className="au-link"
            onClick={send}
            disabled={Boolean(busy) || resendIn > 0 || lockedFor > 0}
          >
            {resendIn > 0 ? `Send a new code in ${resendIn}s` : "Send a new code"}
          </button>
        ) : (
          <span />
        )}
        <button type="button" className="au-link" onClick={cancelOtp} disabled={Boolean(busy)}>
          Use another account
        </button>
      </div>
    </AuthLayout>
  );
}
