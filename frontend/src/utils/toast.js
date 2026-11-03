// Tiny pop-up notifications: toast.success("Code sent") from anywhere; <Toaster /> shows them.

const listeners = new Set();
let nextId = 1;

function show(kind, title, text = "", ms = 5000) {
  const item = { id: nextId++, kind, title, text, ms };
  listeners.forEach((listener) => listener(item));
  return item.id;
}

export const toast = {
  success: (title, text, ms) => show("success", title, text, ms),
  info: (title, text, ms) => show("info", title, text, ms),
  error: (title, text, ms) => show("error", title, text, ms),
};

export function onToast(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
