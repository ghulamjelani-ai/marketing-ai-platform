import { Link } from "react-router-dom";
import ThemeToggle from "./ThemeToggle";
import "../auth.css";
import "../automation.css";

const SLIDES = [
  ["Automate Your", "Marketing"],
  ["Set It Once,", "Let AI Run It"],
  ["From Idea To", "Published Post"],
];

export default function AuthLayout({ title, subtitle, error, children }) {
  return (
    <div className="au-page">
      <ThemeToggle className="th-fixed" />
      <div className="au-card">
        <div className="au-visual">
          <span className="au-orb au-orb-1" />
          <span className="au-orb au-orb-2" />
          <span className="au-orb au-orb-3" />

          <svg
            className="au-dunes"
            viewBox="0 0 600 330"
            preserveAspectRatio="none"
          >
            <path
              className="au-dune-a"
              d="M-40 200 C 120 90, 260 120, 380 190 S 560 260, 660 170 V330 H-40Z"
              fill="#7b1e2b"
              opacity="0.55"
            />
            <path
              className="au-dune-b"
              d="M-40 250 C 100 160, 240 220, 360 250 S 540 190, 660 240 V330 H-40Z"
              fill="#3b151b"
              opacity="0.85"
            />
          </svg>

          <div className="au-orbit">
            <div className="au-path">
              <div className="au-sat"><span>💬</span></div>
              <div className="au-sat au-sat-b"><span>🗓️</span></div>
            </div>
            <div className="au-path au-path-2">
              <div className="au-sat"><span>🚀</span></div>
            </div>
            <div className="au-core">⚙️</div>
          </div>

          <div className="au-chips">
            <span className="au-chip">PLAN</span>
            <span className="au-chip">CREATE</span>
            <span className="au-chip">PUBLISH</span>
            <span className="au-chip">REPEAT</span>
          </div>

          <Link to="/" className="au-logo" style={{ textDecoration: "none" }}>
            Marketing AI
          </Link>

          <div className="au-slides">
            {SLIDES.map(([a, b]) => (
              <p key={a} className="au-slide">
                {a}
                <br />
                {b}
              </p>
            ))}
          </div>

          <div className="au-dots">
            <span className="au-dot" />
            <span className="au-dot" />
            <span className="au-dot" />
          </div>
        </div>

        <div className="au-form-wrap">
          <h1 className="au-title font-classic">{title}</h1>
          <p className="au-sub">{subtitle}</p>
          {error ? <div className="au-error">{error}</div> : <div />}
          {children}
        </div>
      </div>
    </div>
  );
}
