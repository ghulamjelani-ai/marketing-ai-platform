import { useEffect, useState } from "react";
import { onToast } from "../utils/toast";

const ICONS = { success: "✓", info: "i", error: "!" };

// Shows pop-up notifications in the top-right corner; each closes by itself or on click.
export default function Toaster() {
  const [items, setItems] = useState([]);

  useEffect(
    () =>
      onToast((item) => {
        setItems((list) => [...list.slice(-2), item]);
        setTimeout(() => setItems((list) => list.filter((x) => x.id !== item.id)), item.ms);
      }),
    [],
  );

  const close = (id) => setItems((list) => list.filter((x) => x.id !== id));

  return (
    <div className="toaster" aria-live="polite">
      {items.map((item) => (
        <div key={item.id} className={`toast toast-${item.kind}`} role={item.kind === "error" ? "alert" : "status"}>
          <span className="toast-icon" aria-hidden="true">{ICONS[item.kind]}</span>
          <div className="toast-body">
            <p className="toast-title">{item.title}</p>
            {item.text && <p className="toast-text">{item.text}</p>}
          </div>
          <button type="button" className="toast-close" onClick={() => close(item.id)} aria-label="Close notification">
            &times;
          </button>
          <span className="toast-timer" style={{ animationDuration: `${item.ms}ms` }} />
        </div>
      ))}
    </div>
  );
}
