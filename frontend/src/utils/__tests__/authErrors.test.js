import { describe, expect, it } from "vitest";
import { friendlyAuthError, validateLogin, validateSignup } from "../authErrors";

const firebaseError = (code) =>
  Object.assign(new Error(`Firebase: Error (${code}).`), { code });

describe("friendlyAuthError", () => {
  it.each([
    ["auth/email-already-in-use", "already registered"],
    ["auth/invalid-email", "valid email"],
    ["auth/weak-password", "stronger password"],
    ["auth/network-request-failed", "No connection"],
    ["auth/too-many-requests", "Too many attempts"],
    ["auth/popup-closed-by-user", "cancelled"],
    ["auth/popup-blocked", "blocked the Google window"],
    ["auth/account-exists-with-different-credential", "Log in with your password"],
    ["auth/operation-not-allowed", "Sign-in method"],
    ["auth/unauthorized-domain", "Authorized domains"],
    ["auth/invalid-credential", "email or password is not right"],
  ])("%s", (code, text) => {
    const message = friendlyAuthError(firebaseError(code));
    expect(message).toContain(text);
    expect(message).not.toMatch(/Firebase:|auth\//);
  });

  it("never shows an unknown raw Firebase error", () => {
    expect(friendlyAuthError(firebaseError("auth/something-new"))).toBe(
      "Something went wrong while signing in. Please try again.",
    );
  });

  it("keeps readable backend messages", () => {
    const error = Object.assign(new Error("That code is not right. 4 tries left."), {
      code: "OTP_WRONG",
    });
    expect(friendlyAuthError(error)).toBe("That code is not right. 4 tries left.");
  });

  it("explains a backend that cannot be reached", () => {
    expect(friendlyAuthError(new TypeError("Failed to fetch"))).toContain("Could not reach");
  });
});

describe("validateSignup", () => {
  const ok = {
    name: "Umer",
    email: "umer@example.com",
    password: "Secret-123",
    confirmPassword: "Secret-123",
  };

  it("accepts a complete form", () => {
    expect(validateSignup(ok)).toBe("");
  });

  it.each([
    [{ name: " " }, "name"],
    [{ email: "" }, "email address"],
    [{ email: "umer@" }, "valid email"],
    [{ password: "Sh0rt!", confirmPassword: "Sh0rt!" }, "8 characters"],
    [{ password: "secret-123", confirmPassword: "secret-123" }, "a capital letter"],
    [{ password: "SECRET-123", confirmPassword: "SECRET-123" }, "a small letter"],
    [{ password: "Secret-abc", confirmPassword: "Secret-abc" }, "a number"],
    [{ password: "Secret1234", confirmPassword: "Secret1234" }, "a special character"],
    [{ confirmPassword: "Different-1" }, "do not match"],
  ])("rejects %j", (change, text) => {
    expect(validateSignup({ ...ok, ...change })).toContain(text);
  });
});

describe("validateLogin", () => {
  it("needs an email and a password", () => {
    expect(validateLogin({ email: "bad", password: "x" })).toContain("valid email");
    expect(validateLogin({ email: "a@b.co", password: "" })).toContain("password");
    expect(validateLogin({ email: "a@b.co", password: "x" })).toBe("");
  });
});
