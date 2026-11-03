import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import ThemeToggle from "../components/ThemeToggle";
import BrandMark from "../components/BrandMark";
import useSpotlight from "../hooks/useSpotlight";
import useDocumentTitle from "../hooks/useDocumentTitle";
import { useAuth } from "../context/useAuth";
import "../dashboard.css";
import "../automation.css";
import "../theme.css";
import "../intro.css";
import "../polish.css";

const SECTIONS = ["Welcome", "What we do", "How it works", "Get started"];

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

// The welcome page: four full-screen sections you scroll through. Each section fades in
// the first time it comes into view.
export default function Intro() {
  useSpotlight();
  useDocumentTitle("Your marketing, on autopilot");

  // A signed-in visitor can still read this page (so the Back button works); the buttons
  // lead to the dashboard instead of to sign-up.
  const { user } = useAuth();

  const scrollerRef = useRef(null);
  const [active, setActive] = useState(0);
  // Without IntersectionObserver (very old browsers) every section is simply shown.
  const [seen, setSeen] = useState(() =>
    "IntersectionObserver" in window ? new Set([0]) : new Set(SECTIONS.map((_, i) => i)),
  );

  useEffect(() => {
    const scroller = scrollerRef.current;
    const sections = [...scroller.querySelectorAll(".in-slide")];

    if (!("IntersectionObserver" in window)) return undefined;

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;

          const i = sections.indexOf(entry.target);
          setSeen((value) => (value.has(i) ? value : new Set(value).add(i)));

          if (entry.intersectionRatio >= 0.5) setActive(i);
        });
      },
      { root: scroller, threshold: [0.15, 0.5] },
    );

    sections.forEach((section) => observer.observe(section));
    return () => observer.disconnect();
  }, []);

  // Focus the scroll box so the keyboard (arrows, Page Down, Space, Home, End) scrolls it.
  useEffect(() => {
    scrollerRef.current.focus({ preventScroll: true });
  }, []);

  const goTo = (i) => {
    const still = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    document.getElementById(`intro-${i + 1}`)?.scrollIntoView({ behavior: still ? "auto" : "smooth", block: "start" });
  };

  const sectionProps = (i) => ({
    id: `intro-${i + 1}`,
    "aria-label": SECTIONS[i],
    className: `in-slide ${seen.has(i) ? "seen" : ""} ${active === i ? "active" : ""}`,
  });

  return (
    <div className="in-page" ref={scrollerRef} tabIndex={-1}>
      <div className="dx-grid-bg" />
      <div className="dx-cursor" />

      <header className="in-top">
        <div className="in-brand">
          <BrandMark size={34} />
          Marketing AI
        </div>

        <div className="in-top-actions">
          {user ? (
            <Link to="/home" className="in-ghost in-ghost-sm">
              Open dashboard
            </Link>
          ) : (
            <Link to="/login" className="in-ghost in-ghost-sm">
              Log in
            </Link>
          )}
          <ThemeToggle />
        </div>
      </header>

      <main className="in-stage">
        {/* 1 - WELCOME */}
        <section {...sectionProps(0)}>
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
              See how it works ↓
            </button>
          </div>

          <button type="button" className="in-scroll-cue" onClick={() => goTo(1)} aria-label="Scroll down">
            <span className="in-mouse" aria-hidden="true" />
            Scroll
          </button>
        </section>

        {/* 2 - WHAT WE DO */}
        <section {...sectionProps(1)}>
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
        <section {...sectionProps(2)}>
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
        <section {...sectionProps(3)}>
          <span className="in-tag">Ready when you are</span>
          <h2 className="in-h1">
            Put your marketing <span className="dx-gold-text">to work</span>
          </h2>
          <p className="in-lead">
            Create an account in under a minute, or log in to continue where
            you left off.
          </p>

          <div className="in-row">
            {user ? (
              <Link to="/home" className="in-btn">
                Open dashboard
              </Link>
            ) : (
              <>
                <Link to="/signup" className="in-btn">
                  Create account
                </Link>
                <Link to="/login" className="in-ghost">
                  Log in
                </Link>
              </>
            )}
          </div>
        </section>
      </main>
    </div>
  );
}
