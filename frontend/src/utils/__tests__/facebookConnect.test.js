import { beforeEach, describe, expect, it } from "vitest";
import { clearConnecting, isConnecting, markConnecting, readFacebookResult } from "../facebookConnect";

// The tests run in Node, which has no browser storage: a small stand-in.
beforeEach(() => {
  const store = new Map();

  globalThis.window = {
    localStorage: {
      getItem: (key) => (store.has(key) ? store.get(key) : null),
      setItem: (key, value) => store.set(key, String(value)),
      removeItem: (key) => store.delete(key),
    },
  };
});

describe("readFacebookResult", () => {
  it("reads the redirect back from the Facebook window", () => {
    expect(readFacebookResult("?facebook=connected&pages=3")).toEqual({ result: "connected", pages: 3 });
    expect(readFacebookResult("?facebook=error")).toEqual({ result: "error", pages: 1 });
  });

  it("ignores any other address", () => {
    expect(readFacebookResult("")).toBeNull();
    expect(readFacebookResult("?facebook=maybe")).toBeNull();
    expect(readFacebookResult("?page=2")).toBeNull();
  });

  it("never reports fewer than one Page", () => {
    expect(readFacebookResult("?facebook=connected&pages=0").pages).toBe(1);
    expect(readFacebookResult("?facebook=connected&pages=abc").pages).toBe(1);
  });
});

describe("the connecting flag", () => {
  it("is off by default and on right after marking", () => {
    expect(isConnecting()).toBe(false);
    markConnecting();
    expect(isConnecting()).toBe(true);
  });

  it("expires after ten minutes so an old flag never hides the app", () => {
    markConnecting(1000);
    expect(isConnecting(1000 + 9 * 60 * 1000)).toBe(true);
    expect(isConnecting(1000 + 11 * 60 * 1000)).toBe(false);
  });

  it("can be cleared", () => {
    markConnecting();
    clearConnecting();
    expect(isConnecting()).toBe(false);
  });
});
