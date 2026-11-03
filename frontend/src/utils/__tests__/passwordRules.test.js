import { describe, expect, it } from "vitest";
import { PASSWORD_RULES, passwordProblem } from "../passwordRules";

describe("password rules", () => {
  it.each(["Secret-123", "Marketing@2026", "Ab1!Ab1!"])("accepts %s", (password) => {
    expect(passwordProblem(password)).toBe("");
  });

  it("lists everything that is missing in one sentence", () => {
    expect(passwordProblem("abc")).toBe(
      "Your password needs at least 8 characters, a capital letter, a number and a special character such as ! @ # $.",
    );
  });

  it("has five rules", () => {
    expect(PASSWORD_RULES).toHaveLength(5);
  });
});
