import { useEffect } from "react";

// Mouse effects for the whole page: a soft glow that follows the cursor,
// a spotlight inside the hovered card, and a gentle 3D tilt on .dx-tilt cards.
export default function useSpotlight() {
  useEffect(() => {
    if (!window.matchMedia("(pointer: fine)").matches) return undefined;

    const root = document.documentElement;
    let frame = 0;

    const onMove = (event) => {
      cancelAnimationFrame(frame);

      frame = requestAnimationFrame(() => {
        root.style.setProperty("--cx", `${event.clientX}px`);
        root.style.setProperty("--cy", `${event.clientY}px`);

        const card = event.target.closest?.(".dx-card, .in-card");
        if (!card) return;

        const rect = card.getBoundingClientRect();
        const x = event.clientX - rect.left;
        const y = event.clientY - rect.top;

        card.style.setProperty("--mx", `${x}px`);
        card.style.setProperty("--my", `${y}px`);

        if (card.classList.contains("dx-tilt")) {
          card.style.setProperty("--ry", `${(x / rect.width - 0.5) * 8}deg`);
          card.style.setProperty("--rx", `${(0.5 - y / rect.height) * 8}deg`);
        }
      });
    };

    window.addEventListener("pointermove", onMove, { passive: true });

    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("pointermove", onMove);
    };
  }, []);
}
