import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import ThemeToggle from "../components/ThemeToggle";
import useSpotlight from "../hooks/useSpotlight";
import "../dashboard.css";
import "../automation.css";
import "../theme.css";
import "../intro.css";
import "../polish.css";

const LAST = 3;

const FEATURES = [
  {
    icon: "🎯",
    title: "AI Strategy",
    text: "Understands your business and builds a practical marketing plan around your audience and goals.",
  },
  {
    icon: "✨",
    title: "Content Creation",
    text: "Captions, hooks and post ideas written for you in seconds, ready to publish.",
  },
  {
    icon: "🚀",
    title: "Auto Publishing",
    text: "Connect your Facebook Page and publish photos and posts straight from your dashboard.",
  },
];

const STEPS = [
  { icon: "💬", title: "1. Describe", text: "Tell the AI about your business" },
  { icon: "🧠", title: "2. Plan", text: "AI builds your strategy" },
  { icon: "✍️", title: "3. Create", text: "Posts and captions are written" },
  { icon: "🚀", title: "4. Publish", text: "One click to your Facebook Page" },
];

export default function Intro() {
  useSpotlight();
  const [index, setIndex] = useState(0);

  const goTo = (next) => setIndex(Math.max(0, Math.min(LAST, next)));

  useEffect(() => {
    const onKey = (event) => {
      if (event.key === "ArrowRight") setIndex((i) => Math.min(LAST, i + 1));
      if (event.key === "ArrowLeft") setIndex((i) => Math.max(0, i - 1));
    };

    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const slideClass = (i) =>
    `in-slide ${i === index ? "active" : i < index ? "past" : ""}`;

  return (
    <div className="in-page">
      <div className="dx-grid-bg" />
      <div className="dx-cursor" />

      <header className="in-top">
        <div className="in-brand">
          <svg
            className="dx-gear"
            viewBox="0 0 24 24"
            fill="none"
            strokeWidth="1.6"
            style={{ stroke: "var(--accent)" }}
          >
            <circle cx="12" cy="12" r="3" />
            <path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1" />
          </svg>
          Marketing AI
        </div>

        <div className="in-top-actions">
          <Link to="/login" className="in-ghost in-ghost-sm">
            Log in
          </Link>
          <ThemeToggle />
        </div>
      </header>

      <main className="in-stage">
        {/* 1 - WELCOME */}
        <section className={slideClass(0)} aria-hidden={index !== 0}>
          <div className="in-orbit">
            <div className="in-ring">
              <div className="in-sat"><span>💬</span></div>
            </div>
            <div className="in-ring in-ring-2">
              <div className="in-sat"><span>🚀</span></div>
            </div>
            <div className="in-core">⚙️</div>
          </div>

          <span className="in-tag">Welcome to Marketing AI</span>
          <h1 className="in-h1">
            Your marketing, on <span className="dx-gold-text">autopilot</span>
          </h1>
          <p className="in-lead">
            Tell the AI about your business once. It plans, writes and
            publishes your social media content, so you can get back to your
            real work.
          </p>

          <div className="in-row">
            <button className="in-btn" onClick={() => goTo(1)}>
              See how it works →
            </button>
          </div>
        </section>

        {/* 2 - WHAT WE DO */}
        <section className={slideClass(1)} aria-hidden={index !== 1}>
          <span className="in-tag">What we do</span>
          <h2 className="in-h2">
            Three jobs, <span className="dx-gold-text">fully automated</span>
          </h2>
          <p className="in-lead">
            Stop juggling tools. One assistant handles the work that normally
            eats your week.
          </p>

          <div className="in-grid3">
            {FEATURES.map((f) => (
              <div key={f.title} className="in-card">
                <div className="in-card-ic">{f.icon}</div>
                <h3>{f.title}</h3>
                <p>{f.text}</p>
              </div>
            ))}
          </div>
        </section>

        {/* 3 - HOW IT WORKS */}
        <section className={slideClass(2)} aria-hidden={index !== 2}>
          <span className="in-tag">How it works</span>
          <h2 className="in-h2">
            From idea to published post in{" "}
            <span className="dx-gold-text">4 steps</span>
          </h2>

          <div className="in-steps">
            {STEPS.map((s, i) => (
              <div key={s.title} className="in-step" style={{ "--d": `${i * 2}s` }}>
                <div className="in-num">{s.icon}</div>
                <b>{s.title}</b>
                <small>{s.text}</small>
              </div>
            ))}
          </div>
        </section>

        {/* 4 - GET STARTED */}
        <section className={slideClass(3)} aria-hidden={index !== 3}>
          <span className="in-tag">Ready when you are</span>
          <h1 className="in-h1">
            Put your marketing <span className="dx-gold-text">to work</span>
          </h1>
          <p className="in-lead">
            Create an account in under a minute, or log in to continue where
            you left off.
          </p>

          <div className="in-row">
            <Link to="/signup" className="in-btn">
              Create account
            </Link>
            <Link to="/login" className="in-ghost">
              Log in
            </Link>
          </div>
        </section>
      </main>

      <div className="in-controls">
        <button
          className="in-ghost in-ghost-sm"
          onClick={() => goTo(index - 1)}
          style={{ visibility: index === 0 ? "hidden" : "visible" }}
          aria-label="Previous"
        >
          ←
        </button>

        <div className="in-dots">
          {[0, 1, 2, 3].map((i) => (
            <button
              key={i}
              className={`in-dot ${i === index ? "on" : ""}`}
              onClick={() => goTo(i)}
              aria-label={`Go to step ${i + 1}`}
            />
          ))}
        </div>

        <button
          className="in-btn in-btn-sm"
          onClick={() => goTo(index + 1)}
          style={{ visibility: index === LAST ? "hidden" : "visible" }}
        >
          Next →
        </button>
      </div>

      {index < LAST && (
        <button className="in-skip" onClick={() => goTo(LAST)}>
          Skip intro
        </button>
      )}
    </div>
  );
}
