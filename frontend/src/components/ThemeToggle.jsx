import { useState } from "react";
import "../theme.css";

function readTheme() {
  return document.documentElement.dataset.theme === "light" ? "light" : "dark";
}

export default function ThemeToggle({ className = "" }) {
  const [theme, setTheme] = useState(readTheme);

  const toggle = () => {
    const next = theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;

    try {
      localStorage.setItem("theme", next);
    } catch {
      // storage can be blocked; the theme still changes for this visit
    }

    setTheme(next);
  };

  return (
    <button
      type="button"
      onClick={toggle}
      className={`th-toggle ${className}`}
      aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
      title={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
    >
      <span className="th-knob" />
    </button>
  );
}
