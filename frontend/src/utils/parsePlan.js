// Reads a marketing plan reply from the AI and extracts the ready-to-use posts
// (caption, description, hashtags) and the image generation prompts.

const clean = (value) =>
  value
    .replace(/\*\*|__|`/g, "")
    .replace(/\s+/g, " ")
    .trim();

function section(text, number) {
  const start = new RegExp(`^\\s*${number}\\.\\s.*$`, "m").exec(text);

  if (!start) return "";

  const rest = text.slice(start.index + start[0].length);
  const next = new RegExp(`^\\s*${number + 1}\\.\\s.*$`, "m").exec(rest);

  return next ? rest.slice(0, next.index) : rest;
}

function field(chunk, label, followingLabels) {
  const stop = followingLabels.length
    ? `(?=\\n\\s*\\**(?:${followingLabels.join("|")})\\**\\s*:|$)`
    : "$";

  const match = new RegExp(
    `\\**${label}\\**\\s*:\\s*\\**([\\s\\S]*?)${stop}`,
    "i",
  ).exec(chunk);

  return match ? clean(match[1]) : "";
}

// Reads "Post 1 / Caption / Description / Hashtags / Image prompt" blocks.
function readPosts(text) {
  return text
    .split(/^\s*\**Post\s*\d+\**\s*:?\s*$/im)
    .map((chunk) => ({
      caption: field(chunk, "Caption", ["Description", "Hashtags?", "Image prompt"]),
      description: field(chunk, "Description", ["Hashtags?", "Image prompt"]),
      hashtags: field(chunk, "Hashtags?", ["Image prompt"]),
      imagePrompt: field(chunk, "Image prompt", []),
    }))
    .filter((post) => post.caption);
}

export function parsePlan(reply) {
  const text = String(reply || "").replace(/\r/g, "");

  // A full plan keeps its posts in section 5; a plain post reply has no sections.
  let posts = readPosts(section(text, 5));

  if (posts.length === 0) {
    posts = readPosts(text);
  }

  const imagePrompts = section(text, 6)
    .split("\n")
    .map((line) =>
      clean(line)
        .replace(/^([-*•]|\d+[.)])\s*/, "")
        .replace(/^["“]|["”]$/g, "")
        .trim(),
    )
    .filter((line) => line.length > 15);

  return { posts, imagePrompts };
}

// Text that goes into the Facebook post box for one parsed post.
export function postToText(post) {
  return [post.caption, post.description, post.hashtags]
    .filter(Boolean)
    .join("\n\n");
}
