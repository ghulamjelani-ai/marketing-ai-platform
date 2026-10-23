import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  autopilotPost,
  cancelScheduled,
  getBestTime,
  schedulePost,
} from "../api/activity";
import { publishFacebookPhoto, publishFacebookPost } from "../api/facebook";
import { generateImage } from "../api/images";
import { postToText } from "../utils/parsePlan";
import "../polish.css";

const STEPS = [
  { icon: "✍️", title: "Writing your post", hint: "Caption, description and hashtags" },
  { icon: "🎨", title: "Creating your picture", hint: "High quality AI image" },
  { icon: "🚀", title: "Publishing to Facebook", hint: "Straight to your Page" },
];

const fresh = () => STEPS.map(() => ({ state: "wait", note: "" }));

// The next time today (or tomorrow) that is clock time `time`, at least 25 minutes ahead.
function nextOccurrence(time) {
  const [hours, minutes] = time.split(":").map(Number);
  const moment = new Date();

  moment.setHours(hours, minutes, 0, 0);

  if (moment.getTime() < Date.now() + 25 * 60 * 1000) {
    moment.setDate(moment.getDate() + 1);
  }

  return moment;
}

const showMoment = (moment) =>
  moment.toLocaleString([], {
    weekday: "long",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

// One click: the AI writes the post, creates the picture and publishes (or schedules) it.
export default function Autopilot({ facebookConnected, pageName, onDone }) {
  const [request, setRequest] = useState("");
  const [withImage, setWithImage] = useState(true);
  const [mode, setMode] = useState("now");
  const [allowed, setAllowed] = useState(false);
  const [running, setRunning] = useState(false);
  const [steps, setSteps] = useState(fresh);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [removing, setRemoving] = useState(false);

  const cancelRef = useRef(false);
  const imageUrlRef = useRef("");

  function mark(index, state, note = "") {
    setSteps((list) =>
      list.map((step, i) => (i === index ? { state, note } : step)),
    );
  }

  function checkCancelled() {
    if (cancelRef.current) {
      const stop = new Error("stopped");
      stop.cancelled = true;
      throw stop;
    }
  }

  async function run() {
    setError("");
    setNotice("");
    setResult(null);
    setSteps(fresh());
    cancelRef.current = false;
    setRunning(true);

    let current = 0;

    try {
      // 1 - write
      mark(0, "run", "Reading your request...");
      const { post } = await autopilotPost(request.trim());
      const text = postToText(post);
      mark(0, "done", post.caption);
      checkCancelled();

      // 2 - picture
      current = 1;
      let image = null;

      if (withImage) {
        mark(1, "run", "This takes about 30 to 60 seconds for the best quality...");
        image = await generateImage(post.image_prompt || post.caption);
        mark(1, "done", "Picture ready");
      } else {
        mark(1, "skipped", "Skipped");
      }

      checkCancelled();

      // 3 - publish or schedule (nothing is published after Stop was pressed)
      current = 2;
      let outcome;

      if (mode === "now") {
        mark(2, "run", "Posting on " + (pageName || "your Page") + "...");

        if (image) {
          await publishFacebookPhoto(text, image);
        } else {
          await publishFacebookPost(text);
        }

        outcome = { kind: "published", label: "Published just now" };
        mark(2, "done", "Live on your Page");
      } else {
        mark(2, "run", "Choosing the best time...");

        const best = await getBestTime();
        const moment = nextOccurrence(best.times[0].time);

        const saved = await schedulePost({
          message: text,
          runAt: moment.toISOString(),
          image,
        });

        outcome = {
          id: saved?.post?.id,
          kind: "scheduled",
          label: "Scheduled for " + showMoment(moment),
        };
        mark(2, "done", outcome.label);
      }

      if (imageUrlRef.current) {
        URL.revokeObjectURL(imageUrlRef.current);
      }

      imageUrlRef.current = image ? URL.createObjectURL(image) : "";

      setResult({ text, imageUrl: imageUrlRef.current, ...outcome });
      onDone(outcome.kind);
    } catch (err) {
      if (err.cancelled) {
        setNotice("Stopped. Nothing was published.");
      } else {
        mark(current, "error", "Something went wrong");
        setError(err.message || "Autopilot could not finish.");
      }
    } finally {
      setRunning(false);
    }
  }

  async function removeScheduled() {
    if (!result?.id) return;

    setRemoving(true);
    setError("");

    try {
      await cancelScheduled(result.id);
      setResult(null);
      setNotice("Removed. That post will not be published.");
      onDone("removed");
    } catch (err) {
      setError(err.message || "Could not remove the post.");
    } finally {
      setRemoving(false);
    }
  }

  const ready = facebookConnected && allowed && !running;
  const progress =
    steps.filter((step) => step.state === "done" || step.state === "skipped")
      .length / STEPS.length;

  return (
    <div className="dx-card ap-card dx-rise rounded-3xl p-7 mb-8">
      <div className="ap-glow" />

      <div className="relative">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="dx-eyebrow">One-click Autopilot</p>
            <h2 className="dx-title text-3xl mt-2">
              Write, design and <span className="dx-gold-text">post</span> in
              one click
            </h2>
            <p className="mt-2 text-sm dx-muted max-w-2xl">
              Tell it what you need. The AI writes the post, creates a
              high-quality picture and sends it to your Facebook Page.
            </p>
          </div>

          <div className="ap-badge">✨ Fully automatic</div>
        </div>

        <div className="mt-6 grid gap-6 lg:grid-cols-[1fr_1fr]">
          <div>
            <label className="dx-label block text-sm mb-2">
              What is the post about?
            </label>
            <textarea
              value={request}
              onChange={(event) => setRequest(event.target.value)}
              rows={4}
              maxLength={2000}
              disabled={running}
              placeholder="Example: A limited time offer for new customers this weekend. (Leave empty to promote your business using what the assistant remembers.)"
              className="dx-input resize-y"
            />

            <p className="dx-assist-note !mt-2">
              Autopilot also uses what the assistant remembers about your
              business. If a post mentions the wrong business, fix it under
              &ldquo;What the assistant remembers&rdquo; at the bottom of the page.
            </p>

            <div className="ap-options mt-4">
              <label className="dx-check">
                <input
                  type="checkbox"
                  checked={withImage}
                  onChange={(event) => setWithImage(event.target.checked)}
                  disabled={running}
                />
                <span>Create an AI picture</span>
              </label>

              <div className="dx-assist-tabs">
                <button
                  type="button"
                  className={`dx-assist-tab ${mode === "now" ? "on" : ""}`}
                  onClick={() => setMode("now")}
                  disabled={running}
                >
                  Post now
                </button>
                <button
                  type="button"
                  className={`dx-assist-tab ${mode === "best" ? "on" : ""}`}
                  onClick={() => setMode("best")}
                  disabled={running}
                >
                  Post at the best time
                </button>
              </div>
            </div>

            <label className="dx-check mt-4">
              <input
                type="checkbox"
                checked={allowed}
                onChange={(event) => setAllowed(event.target.checked)}
                disabled={running}
              />
              <span>
                I allow Marketing AI to{" "}
                {mode === "now" ? "publish" : "schedule"} this post on{" "}
                <b>{pageName || "my Facebook Page"}</b> without asking again.
              </span>
            </label>

            <div className="mt-5 flex flex-wrap items-center gap-3">
              <button
                type="button"
                className="dx-btn ap-go"
                onClick={run}
                disabled={!ready}
              >
                {running ? "Autopilot is working..." : "✨ Create and post"}
              </button>

              {running && (
                <button
                  type="button"
                  className="dx-btn-ghost"
                  onClick={() => {
                    cancelRef.current = true;
                    setNotice("Stopping after the current step...");
                  }}
                >
                  Stop
                </button>
              )}
            </div>

            {!facebookConnected && (
              <p className="dx-assist-note">
                Connect your Facebook Page first (the button below) to use
                Autopilot.
              </p>
            )}
          </div>

          <div>
            <div className="ap-track">
              <div
                className="ap-track-fill"
                style={{ width: `${progress * 100}%` }}
              />
            </div>

            <div className="ap-steps">
              {STEPS.map((step, index) => (
                <div
                  key={step.title}
                  className={`ap-step ${steps[index].state}`}
                >
                  <div className="ap-orb">
                    {steps[index].state === "done" ||
                    steps[index].state === "skipped"
                      ? "✓"
                      : steps[index].state === "error"
                        ? "!"
                        : step.icon}
                  </div>
                  <div className="min-w-0">
                    <p className="ap-step-title">{step.title}</p>
                    <p className="ap-step-note">
                      {steps[index].note || step.hint}
                    </p>
                  </div>
                </div>
              ))}
            </div>

            {error && <p className="dx-assist-status bad mt-4">{error}</p>}
            {notice && !error && (
              <p className="dx-assist-status mt-4">{notice}</p>
            )}
          </div>
        </div>

        {result && (
          <div className="ap-result">
            <p className="ap-result-title">
              {result.kind === "published" ? "🎉 " : "🗓️ "}
              {result.label}
            </p>
            <div className="ap-result-body">
              {result.imageUrl && (
                <img
                  src={result.imageUrl}
                  alt="Picture created by Autopilot"
                  className="ap-result-image"
                />
              )}
              <p className="ap-result-text">{result.text}</p>
            </div>

            {result.kind === "scheduled" && (
              <div className="ap-actions">
                <button
                  type="button"
                  className="dx-btn-danger"
                  onClick={removeScheduled}
                  disabled={removing || !result.id}
                >
                  {removing ? "Removing..." : "Remove this scheduled post"}
                </button>
                <Link to="/scheduled" className="dx-btn-ghost">
                  View all scheduled posts &rarr;
                </Link>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
