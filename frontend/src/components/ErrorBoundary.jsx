import { Component } from "react";

// Catches a crash while drawing a page, so the user sees a clear message and a way out
// instead of a blank screen.
export default class ErrorBoundary extends Component {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error, info) {
    console.error("The page crashed:", error, info?.componentStack);
  }

  render() {
    if (!this.state.failed) return this.props.children;

    return (
      <div className="au-page" role="alert">
        <div className="au-card rounded-3xl px-8 py-8 text-center">
          <h1 className="font-classic text-3xl font-bold" style={{ color: "var(--text)" }}>
            Something went wrong
          </h1>
          <p className="text-sm mt-3" style={{ color: "color-mix(in srgb, var(--text) 65%, transparent)" }}>
            The page could not be shown. Your posts and settings are safe.
          </p>
          <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
            <button type="button" className="dx-btn" onClick={() => window.location.reload()}>
              Reload the page
            </button>
            <a className="dx-btn-ghost" href="/">
              Go to the start page
            </a>
          </div>
        </div>
      </div>
    );
  }
}
