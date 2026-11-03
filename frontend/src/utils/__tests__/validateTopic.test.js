import { describe, expect, it } from "vitest";
import { MAX_LENGTH, validateTopic } from "../validateTopic";

const INVALID = [
  "",
  "   ",
  "123456",
  "1234563qrguoherjgnvsui",
  "!!!???",
  "!!!???!!!???",
  "aaaaaaaaaa",
  "abababababab",
  "asdfghjkl",
  "asdf qwer zxcv",
  "hjkdf sdfkj lorem",
  "<script>alert(1)</script>",
  "Sale on <b>shoes</b> today",
  "😀😀😀😀😀😀😀😀😀😀😀",
  "x".repeat(5000),
  "sale " + "a".repeat(300),
];

const VALID = [
  "Summer sale on running shoes",
  "Grand opening of our new cafe in Lahore this Friday",
  "ہماری نئی بیکری کا افتتاح جمعہ کو ہے",
  "   Summer sale on running shoes   ",
  "SUMMER sale ON Running SHOES",
  "50% off on all cakes this weekend",
  "Robert'); DROP TABLE users;-- sale on shoes",
  "' OR 1=1 -- weekend discount on pizza",
  "Supercalifragilisticexpialidocious sale this weekend",
  "New iPhone15 cases available now",
  "Eid sale on clothes 🎉",
];

describe("validateTopic", () => {
  it.each(INVALID)("rejects %j", (text) => {
    expect(validateTopic(text)).not.toBe("");
  });

  it.each(VALID)("accepts %j", (text) => {
    expect(validateTopic(text)).toBe("");
  });

  it("shows the example in the message", () => {
    expect(validateTopic("1234563qrguoherjgnvsui")).toContain(
      "Summer sale on running shoes",
    );
  });

  it("checks the length after trimming", () => {
    expect(validateTopic("   ab cd   ")).toMatch(/too short/);
    expect(validateTopic(("Fresh bread ".repeat(50)).slice(0, MAX_LENGTH))).toBe("");
    expect(validateTopic("Fresh bread ".repeat(50))).toMatch(/too long/);
  });
});
