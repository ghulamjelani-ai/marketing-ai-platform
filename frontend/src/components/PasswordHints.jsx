import { PASSWORD_RULES } from "../utils/passwordRules";

// Live checklist under the password fields, so problems show while typing instead of
// only after pressing the button.
export default function PasswordHints({ password, confirm }) {
  if (!password && !confirm) return null;

  const matchState = !confirm ? "" : confirm === password ? "ok" : "bad";

  return (
    <ul className="au-hints" aria-live="polite">
      {PASSWORD_RULES.map((rule) => (
        <li key={rule.label} className={`au-hint ${rule.test(password) ? "ok" : ""}`}>
          {rule.label}
        </li>
      ))}
      {confirm && (
        <li className={`au-hint ${matchState}`}>
          {matchState === "ok" ? "Passwords match" : "Passwords don't match yet"}
        </li>
      )}
    </ul>
  );
}
