import { describe, expect, it } from "vitest";
import { autopilotPostText, isAutopilotPost } from "../autopilotPost";

const POST = {
  caption: "Summer sale on running shoes!",
  description: "Up to 30% off this week.",
  hashtags: ["#SummerSale", "#Shoes", "#Run"],
  image_prompt: "Running shoes on a track.",
  language: "English",
};

describe("autopilot post", () => {
  it("accepts the typed object", () => {
    expect(isAutopilotPost(POST)).toBe(true);
  });

  it.each([
    null,
    {},
    { ...POST, caption: "  " },
    { ...POST, hashtags: "#a #b #c" },
    { ...POST, description: undefined },
  ])("rejects %j", (post) => {
    expect(isAutopilotPost(post)).toBe(false);
  });

  it("builds the published text from the fields", () => {
    expect(autopilotPostText(POST)).toBe(
      "Summer sale on running shoes!\n\nUp to 30% off this week.\n\n#SummerSale #Shoes #Run",
    );
  });
});
