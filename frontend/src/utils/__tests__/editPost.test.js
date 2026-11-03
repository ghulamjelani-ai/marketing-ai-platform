import { describe, expect, it } from "vitest";
import { canEdit, changedFields, toLocalInput, validateEdit, EDIT_LOCK_MS } from "../editPost";

const NOW = new Date("2026-11-02T10:00:00").getTime();
const at = (minutes) => toLocalInput(new Date(NOW + minutes * 60000).toISOString());

describe("validateEdit", () => {
  it("accepts text and a time at least 15 minutes ahead", () => {
    expect(validateEdit({ message: "Eid sale", when: at(60), hasPicture: false }, NOW)).toBe("");
  });

  it("needs text or a picture", () => {
    expect(validateEdit({ message: "   ", when: at(60), hasPicture: false }, NOW)).toMatch(/text or a picture/);
    expect(validateEdit({ message: "", when: at(60), hasPicture: true }, NOW)).toBe("");
  });

  it("refuses a missing, soon or too distant time", () => {
    expect(validateEdit({ message: "x", when: "", hasPicture: false }, NOW)).toMatch(/date and time/);
    expect(validateEdit({ message: "x", when: at(5), hasPicture: false }, NOW)).toMatch(/15 minutes/);
    expect(validateEdit({ message: "x", when: at(60 * 24 * 40), hasPicture: false }, NOW)).toMatch(/29 days/);
  });
});

describe("canEdit", () => {
  it("locks a post that goes out in under 10 minutes", () => {
    expect(canEdit(new Date(NOW + EDIT_LOCK_MS - 1000).toISOString(), NOW)).toBe(false);
    expect(canEdit(new Date(NOW + EDIT_LOCK_MS + 1000).toISOString(), NOW)).toBe(true);
  });
});

describe("changedFields", () => {
  const item = { message: "Eid offer", run_at: new Date(NOW + 3600000).toISOString(), with_image: true };
  const same = { message: "Eid offer", when: toLocalInput(item.run_at), image: null, removeImage: false };

  it("sends nothing when nothing changed", () => {
    expect(changedFields(item, same)).toEqual({});
  });

  it("sends only the changed text", () => {
    expect(changedFields(item, { ...same, message: " New text " })).toEqual({ message: "New text" });
  });

  it("sends the new time as an ISO string", () => {
    const changes = changedFields(item, { ...same, when: at(120) });
    expect(Object.keys(changes)).toEqual(["runAt"]);
    expect(changes.runAt).toMatch(/Z$/);
  });

  it("sends a new picture, or a removal only for a post that has one", () => {
    const file = new File(["x"], "a.png", { type: "image/png" });
    expect(changedFields(item, { ...same, image: file }).image).toBe(file);
    expect(changedFields(item, { ...same, removeImage: true })).toEqual({ removeImage: true });
    expect(changedFields({ ...item, with_image: false }, { ...same, removeImage: true })).toEqual({});
  });
});
