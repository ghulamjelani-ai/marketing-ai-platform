// Autopilot posts come from the backend as a validated object:
// { caption, description, hashtags: string[], image_prompt, language }

export function isAutopilotPost(post) {
  return (
    Boolean(post) &&
    typeof post.caption === "string" &&
    post.caption.trim() !== "" &&
    typeof post.description === "string" &&
    Array.isArray(post.hashtags) &&
    typeof post.image_prompt === "string"
  );
}

// The text that is published on Facebook.
export function autopilotPostText(post) {
  return [post.caption, post.description, post.hashtags.join(" ")]
    .filter(Boolean)
    .join("\n\n");
}
