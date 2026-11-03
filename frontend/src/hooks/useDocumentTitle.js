import { useEffect } from "react";

// "Autopilot · Marketing AI" in the browser tab; just the name when there is no page title.
export default function useDocumentTitle(title) {
  useEffect(() => {
    document.title = title ? `${title} · Marketing AI` : "Marketing AI";
  }, [title]);
}
