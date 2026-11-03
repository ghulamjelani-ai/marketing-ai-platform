// Rules and helpers for editing a post that is still waiting to go out.
// They mirror the backend (schedule.py), which checks everything again.

export const MIN_AHEAD_MS = 15 * 60 * 1000;
export const MAX_AHEAD_MS = 29 * 24 * 60 * 60 * 1000;
// Facebook does not accept changes to a post that is about to go out.
export const EDIT_LOCK_MS = 10 * 60 * 1000;

const pad = (value) => String(value).padStart(2, "0");

// An ISO time -> the "YYYY-MM-DDTHH:mm" text a datetime-local input shows, in local time.
export function toLocalInput(iso) {
  const moment = new Date(iso);

  return (
    `${moment.getFullYear()}-${pad(moment.getMonth() + 1)}-${pad(moment.getDate())}` +
    `T${pad(moment.getHours())}:${pad(moment.getMinutes())}`
  );
}

export function canEdit(runAtIso, now = Date.now()) {
  return new Date(runAtIso).getTime() - now >= EDIT_LOCK_MS;
}

// Returns a sentence for the user, or "" when the edit can be saved.
export function validateEdit({ message, when, hasPicture }, now = Date.now()) {
  if (!String(message || "").trim() && !hasPicture) {
    return "A post needs some text or a picture.";
  }

  const moment = new Date(when).getTime();

  if (!when || Number.isNaN(moment)) {
    return "Choose a publish date and time.";
  }

  if (moment < now + MIN_AHEAD_MS) {
    return "Choose a time at least 15 minutes from now.";
  }

  if (moment > now + MAX_AHEAD_MS) {
    return "Facebook can schedule posts at most 29 days ahead.";
  }

  return "";
}

// Only what the user actually changed is sent. `item.run_at` is an ISO string.
export function changedFields(item, form) {
  const changes = {};

  if (form.message.trim() !== (item.message || "").trim()) {
    changes.message = form.message.trim();
  }

  const newTime = new Date(form.when).getTime();
  const oldTime = new Date(toLocalInput(item.run_at)).getTime();

  if (newTime !== oldTime) {
    changes.runAt = new Date(form.when).toISOString();
  }

  if (form.image) {
    changes.image = form.image;
  } else if (form.removeImage && item.with_image) {
    changes.removeImage = true;
  }

  return changes;
}
