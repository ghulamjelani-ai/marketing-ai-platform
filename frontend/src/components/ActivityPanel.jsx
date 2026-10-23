import { useEffect, useState } from "react";
import { clearMemory, getMemory, saveMemory } from "../api/activity";
import "../polish.css";

const excerpt = (text, length = 160) =>
  text.length > length ? `${text.slice(0, length).trim()}...` : text;

// History of published posts, and the short profile the assistant remembers.
export default function ActivityPanel({ posts, total }) {
  const [tab, setTab] = useState("posts");
  const [memory, setMemory] = useState("");
  const [memoryNote, setMemoryNote] = useState("");
  const [busy, setBusy] = useState(false);

  async function loadMemory() {
    try {
      const data = await getMemory();
      setMemory(data.summary || "");
    } catch (err) {
      setMemoryNote(err.message || "Could not load memory.");
    }
  }

  useEffect(() => {
    let off = false;

    getMemory()
      .then((data) => {
        if (!off) setMemory(data.summary || "");
      })
      .catch(() => {});

    return () => {
      off = true;
    };
  }, []);

  async function save() {
    setBusy(true);
    setMemoryNote("");

    try {
      await saveMemory(memory.trim());
      setMemoryNote("Saved.");
    } catch (err) {
      setMemoryNote(err.message || "Could not save.");
    } finally {
      setBusy(false);
    }
  }

  async function clear() {
    if (!window.confirm("Make the assistant forget your business details?")) {
      return;
    }

    setBusy(true);
    setMemoryNote("");

    try {
      await clearMemory();
      setMemory("");
      setMemoryNote("Memory cleared.");
    } catch (err) {
      setMemoryNote(err.message || "Could not clear memory.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="dx-card dx-rise rounded-3xl p-7 mt-8">
      <p className="dx-eyebrow">Your activity</p>

      <div className="dx-assist-tabs mt-4">
        <button
          type="button"
          className={`dx-assist-tab ${tab === "posts" ? "on" : ""}`}
          onClick={() => setTab("posts")}
        >
          Published posts ({total})
        </button>
        <button
          type="button"
          className={`dx-assist-tab ${tab === "memory" ? "on" : ""}`}
          onClick={() => {
            setTab("memory");
            loadMemory();
          }}
        >
          What the assistant remembers
        </button>
      </div>

      {tab === "posts" && (
        <div className="mt-2 space-y-2">
          {posts.length === 0 && (
            <p className="text-sm dx-muted">
              No posts yet. Posts you publish, and scheduled posts once they go
              live, will appear here.
            </p>
          )}

          {posts.map((post) => (
            <div key={post.id} className="dx-row">
              <div className="min-w-0">
                <p className="dx-row-title">
                  {new Date(post.created_at).toLocaleString([], {
                    month: "short",
                    day: "numeric",
                    year: "numeric",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                  {post.with_image && " · with picture"}
                </p>
                <p className="dx-row-text">
                  {excerpt(post.message) || "(picture only)"}
                </p>
              </div>
              <span className="dx-chip">
                {post.source === "scheduled" ? "Scheduled" : "Manual"}
              </span>
            </div>
          ))}
        </div>
      )}

      {tab === "memory" && (
        <div className="mt-2">
          <p className="text-sm dx-muted">
            The assistant keeps these facts about your business, so you do not
            have to repeat them in every chat. It learns them from what you
            write. You can edit or clear them at any time.
          </p>

          <textarea
            value={memory}
            onChange={(event) => setMemory(event.target.value)}
            rows={5}
            maxLength={2000}
            placeholder="Nothing remembered yet. Tell the assistant about your business in the chat."
            className="dx-input resize-y mt-4"
          />

          <div className="mt-3 flex flex-wrap items-center gap-3">
            <button
              type="button"
              className="dx-btn dx-btn-sm"
              onClick={save}
              disabled={busy}
            >
              Save changes
            </button>
            <button
              type="button"
              className="dx-btn-ghost dx-btn-sm"
              onClick={loadMemory}
              disabled={busy}
            >
              Refresh
            </button>
            <button
              type="button"
              className="dx-btn-danger"
              onClick={clear}
              disabled={busy || !memory}
            >
              Forget everything
            </button>
            {memoryNote && (
              <span className="text-sm dx-muted">{memoryNote}</span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
