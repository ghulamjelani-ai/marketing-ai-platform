import { useState } from "react";
import { Link } from "react-router-dom";
import {
  cancelAllScheduled,
  cancelScheduled,
  draftWeekPlan,
  getBestTime,
  schedulePost,
} from "../api/activity";
import { generateImage } from "../api/images";
import { postToText } from "../utils/parsePlan";
import "../polish.css";

const pad = (n) => String(n).padStart(2, "0");

function dateInputValue(date) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function tomorrow() {
  const date = new Date();
  date.setDate(date.getDate() + 1);
  return dateInputValue(date);
}

// Local date and time for day number `dayIndex` of the plan (0 = first day).
function momentFor(startDate, time, dayIndex) {
  const [year, month, day] = startDate.split("-").map(Number);
  const [hours, minutes] = time.split(":").map(Number);

  return new Date(year, month - 1, day + dayIndex, hours, minutes, 0);
}

const showMoment = (moment) =>
  moment.toLocaleString([], {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

const excerpt = (text, length = 110) =>
  text.length > length ? `${text.slice(0, length).trim()}...` : text;

const STATUS_LABEL = {
  published: "Published",
  cancelled: "Cancelled",
  removed: "Removed",
};

// "Post for 7 days" - the AI writes a week of posts, the user approves them, and each
// post is handed to Facebook with its publish time. Facebook publishes them itself.
export default function AutoPoster({
  facebookConnected,
  pageName,
  upcoming,
  past,
  onChanged,
}) {
  const [phase, setPhase] = useState("idle"); // idle | drafting | review | scheduling
  const [description, setDescription] = useState("");
  const [drafts, setDrafts] = useState([]);
  const [startDate, setStartDate] = useState(tomorrow);
  const [time, setTime] = useState("10:00");
  const [withImage, setWithImage] = useState(false);
  const [allowed, setAllowed] = useState(false);
  const [progress, setProgress] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busyId, setBusyId] = useState("");
  const [best, setBest] = useState(null);

  async function createPlan() {
    setError("");
    setNotice("");
    setPhase("drafting");

    try {
      const data = await draftWeekPlan(description.trim());

      setDrafts(
        data.posts.map((post) => ({
          text: postToText(post),
          imagePrompt: post.image_prompt || "",
        })),
      );
      setAllowed(false);
      setBest(null);
      setPhase("review");

      // Suggested posting times arrive a moment later; the top one is pre-selected.
      getBestTime()
        .then((data) => {
          setBest(data);

          if (data.times?.length) {
            setTime(data.times[0].time);
          }
        })
        .catch(() => {});
    } catch (err) {
      setError(err.message || "Could not create the plan.");
      setPhase("idle");
    }
  }

  function updateDraft(index, patch) {
    setDrafts((list) =>
      list.map((draft, i) => (i === index ? { ...draft, ...patch } : draft)),
    );
  }

  async function scheduleAll() {
    setError("");
    setNotice("");

    const first = momentFor(startDate, time, 0);

    if (first.getTime() < Date.now() + 20 * 60 * 1000) {
      setError("Choose a start time at least 20 minutes from now.");
      return;
    }

    const total = drafts.length;
    let done = 0;

    setPhase("scheduling");

    try {
      for (let i = 0; i < total; i += 1) {
        const draft = drafts[i];
        let image = null;

        if (withImage && draft.imagePrompt.trim()) {
          setProgress(`Creating picture ${i + 1} of ${total}...`);
          image = await generateImage(draft.imagePrompt.trim());
        }

        setProgress(`Scheduling post ${i + 1} of ${total} on Facebook...`);

        await schedulePost({
          message: draft.text,
          runAt: momentFor(startDate, time, i).toISOString(),
          image,
        });

        done += 1;
      }

      setNotice(
        `Done. ${done} posts are scheduled. Facebook will publish them for you.`,
      );
      setDrafts([]);
      setAllowed(false);
      setPhase("idle");
    } catch (err) {
      setError(`Stopped after ${done} of ${total} posts: ${err.message}`);

      if (done > 0) {
        // Keep only the posts that were not scheduled yet, continuing on the next free day.
        setStartDate(dateInputValue(momentFor(startDate, time, done)));
        setDrafts((list) => list.slice(done));
      }

      setPhase("review");
    } finally {
      setProgress("");
      onChanged();
    }
  }

  async function cancelOne(id) {
    setBusyId(id);
    setError("");

    try {
      await cancelScheduled(id);
      onChanged();
    } catch (err) {
      setError(err.message || "Could not cancel the post.");
    } finally {
      setBusyId("");
    }
  }

  async function cancelEverything() {
    if (!window.confirm("Cancel all scheduled posts?")) return;

    setBusyId("all");
    setError("");

    try {
      const result = await cancelAllScheduled();

      if (result.failed) {
        setError(`${result.failed} posts could not be cancelled. Try again.`);
      }

      onChanged();
    } catch (err) {
      setError(err.message || "Could not cancel the posts.");
    } finally {
      setBusyId("");
    }
  }

  const working = phase === "drafting" || phase === "scheduling";

  return (
    <div className="dx-card dx-rise rounded-3xl p-7 mt-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="dx-eyebrow">Automatic posting</p>
          <h2 className="dx-title text-2xl mt-2">Post every day for 7 days</h2>
          <p className="mt-2 text-sm dx-muted max-w-2xl">
            The AI writes a week of posts. You read and approve them, then
            Facebook publishes one each day at the time you choose, even when
            your computer is off.
          </p>
        </div>

        <div className="flex flex-wrap gap-3">
          <Link to="/scheduled" className="dx-btn-ghost">
            🗓️ Manage scheduled posts
          </Link>
          {upcoming.length > 0 && (
            <button
              type="button"
              className="dx-btn-danger"
              onClick={cancelEverything}
              disabled={busyId === "all"}
            >
              Cancel all scheduled
            </button>
          )}
        </div>
      </div>

      {!facebookConnected && (
        <p className="dx-assist-note">
          Connect your Facebook Page first (the button at the top of the
          dashboard) to schedule posts.
        </p>
      )}

      {error && <p className="dx-assist-status bad mt-5">{error}</p>}
      {notice && <p className="dx-assist-status ok mt-5">{notice}</p>}

      {phase === "idle" && (
        <div className="mt-6">
          <label className="dx-label block text-sm mb-2">
            About your business (optional if the assistant already remembers it)
          </label>
          <textarea
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            rows={3}
            maxLength={2000}
            placeholder="Example: Sunrise Bakery in Lahore. We sell sourdough bread and cakes and want more local families."
            className="dx-input resize-y"
          />
          <button
            type="button"
            className="dx-btn mt-4"
            onClick={createPlan}
            disabled={!facebookConnected}
          >
            Create my 7-day plan
          </button>
        </div>
      )}

      {phase === "drafting" && (
        <p className="dx-assist-status mt-6">
          Writing your 7 posts... this usually takes about 10 seconds.
        </p>
      )}

      {(phase === "review" || phase === "scheduling") && (
        <div className="mt-6">
          <div className="grid gap-4 sm:grid-cols-3">
            <div>
              <label className="dx-label block text-sm mb-2">Start date</label>
              <input
                type="date"
                value={startDate}
                min={dateInputValue(new Date())}
                onChange={(event) => setStartDate(event.target.value)}
                disabled={working}
                className="dx-input"
              />
            </div>
            <div>
              <label className="dx-label block text-sm mb-2">
                Time of day
              </label>
              <input
                type="time"
                value={time}
                onChange={(event) => setTime(event.target.value)}
                disabled={working}
                className="dx-input"
              />
            </div>
            <label className="dx-check">
              <input
                type="checkbox"
                checked={withImage}
                onChange={(event) => setWithImage(event.target.checked)}
                disabled={working}
              />
              <span>
                Add a high quality AI picture to every post (about a minute
                each, so a full week takes several minutes and uses your
                OpenAI credit)
              </span>
            </label>
          </div>

          {best?.times?.length > 0 && (
            <div className="dx-best">
              <p className="dx-best-title">
                Best times to post
                <span className="dx-chip">
                  {best.source === "your_posts"
                    ? `from your ${best.based_on} posts`
                    : "general guide"}
                </span>
              </p>

              <div className="dx-best-times">
                {best.times.map((item) => (
                  <button
                    key={item.time}
                    type="button"
                    className={`dx-assist-tab ${time === item.time ? "on" : ""}`}
                    onClick={() => setTime(item.time)}
                    disabled={working}
                    title={item.reason}
                  >
                    {item.time}
                  </button>
                ))}
              </div>

              {best.times.map((item) => (
                <p key={item.time} className="dx-best-reason">
                  <b>{item.time}</b> &middot; {item.reason}
                </p>
              ))}

              <p className="dx-best-note">{best.note}</p>
            </div>
          )}

          <div className="mt-5 space-y-4">
            {drafts.map((draft, index) => (
              <div key={index} className="dx-draft">
                <p className="dx-draft-day">
                  Day {index + 1} &middot;{" "}
                  {showMoment(momentFor(startDate, time, index))}
                </p>
                <textarea
                  value={draft.text}
                  onChange={(event) =>
                    updateDraft(index, { text: event.target.value })
                  }
                  rows={5}
                  disabled={working}
                  className="dx-input resize-y"
                />
                {withImage && (
                  <input
                    value={draft.imagePrompt}
                    onChange={(event) =>
                      updateDraft(index, { imagePrompt: event.target.value })
                    }
                    disabled={working}
                    placeholder="Describe the picture for this post"
                    className="dx-input mt-2"
                  />
                )}
              </div>
            ))}
          </div>

          <label className="dx-check mt-6">
            <input
              type="checkbox"
              checked={allowed}
              onChange={(event) => setAllowed(event.target.checked)}
              disabled={working}
            />
            <span>
              I allow Marketing AI to schedule these {drafts.length} posts on{" "}
              <b>{pageName || "my Facebook Page"}</b>. Facebook will publish
              them automatically at the times shown, and I can cancel any of
              them here before they go out.
            </span>
          </label>

          <div className="mt-5 flex flex-wrap items-center gap-3">
            <button
              type="button"
              className="dx-btn"
              onClick={scheduleAll}
              disabled={
                !allowed || working || !facebookConnected || drafts.length === 0
              }
            >
              {phase === "scheduling"
                ? "Scheduling..."
                : `Yes, schedule ${drafts.length} posts`}
            </button>

            <button
              type="button"
              className="dx-btn-ghost"
              onClick={() => {
                setDrafts([]);
                setPhase("idle");
              }}
              disabled={working}
            >
              Start over
            </button>

            {progress && <span className="text-sm dx-muted">{progress}</span>}
          </div>
        </div>
      )}

      {(upcoming.length > 0 || past.length > 0) && (
        <div className="mt-8">
          <h3 className="dx-title text-lg">Scheduled posts</h3>

          <div className="mt-3 space-y-2">
            {upcoming.map((item) => (
              <div key={item.id} className="dx-row">
                <div className="min-w-0">
                  <p className="dx-row-title">
                    {showMoment(new Date(item.run_at))}
                    {item.with_image && " · with picture"}
                  </p>
                  <p className="dx-row-text">{excerpt(item.message)}</p>
                </div>
                <button
                  type="button"
                  className="dx-btn-danger"
                  onClick={() => cancelOne(item.id)}
                  disabled={busyId === item.id || busyId === "all"}
                >
                  Cancel
                </button>
              </div>
            ))}

            {past.map((item) => (
              <div key={item.id} className="dx-row dx-row-past">
                <div className="min-w-0">
                  <p className="dx-row-title">
                    {showMoment(new Date(item.run_at))}
                    {item.with_image && " · with picture"}
                  </p>
                  <p className="dx-row-text">{excerpt(item.message)}</p>
                </div>
                <span className="dx-chip">
                  {STATUS_LABEL[item.status] || item.status}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
