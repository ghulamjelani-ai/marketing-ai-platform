import { Fragment } from "react";

// Shows an AI reply as clean text: no markdown symbols, with headings, lists and bold kept.
function plain(text) {
  return text.replace(/`/g, "").replace(/\*+/g, "");
}

function inline(text) {
  return text
    .split(/(\*\*[^*]+\*\*|__[^_]+__)/g)
    .map((part, i) =>
      /^(\*\*|__)/.test(part) ? (
        <strong key={i}>{plain(part.slice(2, -2))}</strong>
      ) : (
        <Fragment key={i}>{plain(part)}</Fragment>
      ),
    );
}

function parseBlocks(text) {
  const blocks = [];
  let list = null;

  String(text || "")
    .replace(/\r/g, "")
    .split("\n")
    .forEach((raw) => {
      const line = raw.trim();

      if (!line || /^[-*_]{3,}$/.test(line)) {
        list = null;
        return;
      }

      const heading = /^#{1,6}\s+(.*)$/.exec(line);
      const numbered = /^\**(\d+)[.)]\s+(.*)$/.exec(line);
      const bullet = /^[-*•]\s+(.*)$/.exec(line);
      const label = /^\**([A-Za-z][A-Za-z ]{1,24}?)\**\s*:\s*\**\s*(.*)$/.exec(line);

      // "1. Title" on its own (or ending with a colon) is a section heading.
      const numberedTitle =
        numbered && /^[^:]{2,70}:?\**$/.test(numbered[2]) && !/[.!?]$/.test(numbered[2]);

      const postTitle = /^\**(Post|Day)\s*\d+\**\s*:?\**$/i.test(line);

      if (heading || numberedTitle || postTitle) {
        list = null;
        blocks.push({
          type: "heading",
          text: heading ? heading[1] : numbered ? `${numbered[1]}. ${numbered[2]}` : line,
        });
      } else if (bullet || numbered) {
        if (!list) {
          list = { type: "list", items: [] };
          blocks.push(list);
        }
        list.items.push(bullet ? bullet[1] : numbered[2]);
      } else if (label) {
        list = null;
        blocks.push({ type: "label", name: label[1].trim(), text: label[2] });
      } else {
        list = null;
        blocks.push({ type: "p", text: line });
      }
    });

  return blocks;
}

export default function RichText({ text }) {
  return (
    <div className="dx-rich">
      {parseBlocks(text).map((block, i) => {
        if (block.type === "heading") {
          return (
            <p key={i} className="dx-rich-h">
              {inline(block.text.replace(/:\**$/, ""))}
            </p>
          );
        }

        if (block.type === "list") {
          return (
            <ul key={i} className="dx-rich-ul">
              {block.items.map((item, j) => (
                <li key={j}>{inline(item)}</li>
              ))}
            </ul>
          );
        }

        if (block.type === "label") {
          return (
            <p key={i} className="dx-rich-p">
              <span className="dx-rich-label">{block.name}</span>
              {inline(block.text)}
            </p>
          );
        }

        return (
          <p key={i} className="dx-rich-p">
            {inline(block.text)}
          </p>
        );
      })}
    </div>
  );
}
