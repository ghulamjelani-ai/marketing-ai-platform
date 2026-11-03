import { useEffect, useMemo, useRef, useState } from "react";
import VoiceButton from "./VoiceButton";
import { Link } from "react-router-dom";
import {
  autopilotPost,
  cancelScheduled,
  getBestTime,
  schedulePost,
} from "../api/activity";
import { publishFacebookPhoto, publishFacebookPost } from "../api/facebook";
import { generateImage } from "../api/images";
import { autopilotPostText, isAutopilotPost } from "../utils/autopilotPost";
import { MAX_LENGTH, validateTopic } from "../utils/validateTopic";
import "../polish.css";

const STEPS = [
  { icon: "✍️", title: "Writing your post", hint: "Caption, description and hashtags" },
  { icon: "🎨", title: "Creating your picture", hint: "High quality AI image" },
  { icon: "🚀", title: "Publishing to Facebook", hint: "Straight to your Page" },
];

const fresh = () => STEPS.map(() => ({ state: "wait", note: "" }));

const STEP_FAILED = [
  "Could not write the post",
  "Could not create the picture",
  "Could not publish the post",
];

const newKey = () =>
  globalThis.crypto?.randomUUID?.() ||
  `${Date.now()}-${Math.random().toString(36).slice(2)}`;

// Browser network failures arrive as TypeError("Failed to fetch").
function friendlyError(err) {
  if (err instanceof TypeError || /failed to fetch|network ?error/i.test(err?.message || "")) {
    return "Could not reach the server. Check your connection and try again.";
  }

  return err?.message || "Autopilot could not finish.";
}

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
  const [touched, setTouched] = useState(false);

  const [failedStep, setFailedStep] = useState(-1);

  // "Let me review first": after the post and picture are made, the run waits for the user.
  const [reviewFirst, setReviewFirst] = useState(false);
  const [reviewing, setReviewing] = useState(false);
  const [draftText, setDraftText] = useState("");
  const [draftImage, setDraftImage] = useState(null);
  const [regenerating, setRegenerating] = useState(false);
  const [reviewError, setReviewError] = useState("");
  const reviewedRef = useRef(false);

  const cancelRef = useRef(false);
  const imageUrlRef = useRef("");
  // Guards against a double click before React re-renders the disabled button.
  const runningRef = useRef(false);
  // What finished steps produced, so Retry continues from the failed step.
  const doneRef = useRef({ post: null, text: "", image: null });
  // One key per run: Facebook gets the post at most once, even if a request is repeated.
  const keyRef = useRef("");

  const draftPreview = useMemo(() => (draftImage ? URL.createObjectURL(draftImage) : ""), [draftImage]);

  useEffect(() => () => {
    if (draftPreview) URL.revokeObjectURL(draftPreview);
  }, [draftPreview]);

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

  // `from` is 0 for a new run, or the index of a failed step to retry.
  async function run(from = 0) {
    // Nothing is sent to the AI or Facebook unless the topic is valid and consent is given.
    if (validateTopic(request) || !allowed || runningRef.current) return;

    runningRef.current = true;
    setRunning(true);
    setError("");
    setNotice("");
    setFailedStep(-1);
    cancelRef.current = false;

    if (from === 0) {
      reviewedRef.current = false;
      setReviewing(false);
      keyRef.current = newKey();
      doneRef.current = { post: null, text: "", image: null };
      setResult(null);
      setSteps(fresh());
    } else {
      setSteps((list) =>
        list.map((step, i) => (i >= from ? { state: "wait", note: "" } : step)),
      );
    }

    let current = from;

    try {
      // 1 - write
      if (current === 0) {
        mark(0, "run", "Reading your request...");
        const { post } = await autopilotPost(request.trim());

        if (!isAutopilotPost(post)) {
          throw new Error("The AI did not return a usable post. Please try again.");
        }

        doneRef.current.post = post;
        doneRef.current.text = autopilotPostText(post);
        mark(0, "done", post.caption);
        checkCancelled();
        current = 1;
      }

      const { post } = doneRef.current;

      // 2 - picture (a failed picture stops the run: no broken post is published)
      if (current === 1) {
        if (withImage) {
          mark(1, "run", "This takes about 30 to 60 seconds for the best quality...");
          doneRef.current.image = await generateImage(post.image_prompt || post.caption);
          mark(1, "done", "Picture ready");
        } else {
          doneRef.current.image = null;
          mark(1, "skipped", "Skipped");
        }

        checkCancelled();
        current = 2;
      }

      // The user asked to check the post first: stop here until they say it is fine.
      if (reviewFirst && !reviewedRef.current) {
        setDraftText(doneRef.current.text);
        setDraftImage(doneRef.current.image);
        setReviewError("");
        setReviewing(true);
        setNotice("Your post is ready. Read it, change anything you like, then continue.");
        return;
      }

      const { image, text: finalText } = doneRef.current;

      // 3 - publish or schedule (nothing is published after Stop was pressed)
      let outcome;
      const idempotencyKey = keyRef.current;

      if (mode === "now") {
        mark(2, "run", "Posting on " + (pageName || "your Page") + "...");

        if (image) {
          await publishFacebookPhoto(finalText, image, { idempotencyKey });
        } else {
          await publishFacebookPost(finalText, { idempotencyKey });
        }

        outcome = { kind: "published", label: "Published just now" };
        mark(2, "done", "Live on your Page");
      } else {
        mark(2, "run", "Choosing the best time...");

        const best = await getBestTime();
        const moment = nextOccurrence(best.times[0].time);

        const saved = await schedulePost({
          message: finalText,
          runAt: moment.toISOString(),
          image,
          idempotencyKey,
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

      setResult({ text: finalText, imageUrl: imageUrlRef.current, ...outcome });
      onDone(outcome.kind);
    } catch (err) {
      if (err.cancelled) {
        setNotice("Stopped. Nothing was published.");
      } else {
        const message = friendlyError(err);

        mark(current, "error", STEP_FAILED[current]);
        setFailedStep(current);
        setError(
          current < 2 ? message + " Nothing was published." : message,
        );
      }
    } finally {
      runningRef.current = false;
      setRunning(false);
    }
  }

  function continueAfterReview() {
    if (!draftText.trim() && !draftImage) {
      setReviewError("A post needs some text or a picture.");
      return;
    }

    doneRef.current.text = draftText.trim();
    doneRef.current.image = draftImage;
    reviewedRef.current = true;
    setReviewing(false);
    setNotice("");
    run(2);
  }

  function discardReview() {
    setReviewing(false);
    setNotice("Cancelled. Nothing was published.");
    setSteps((list) => list.map((step, i) => (i === 2 ? { state: "wait", note: "" } : step)));
  }

  async function makeNewPicture() {
    const post = doneRef.current.post;

    if (!post) return;

    setRegenerating(true);
    setReviewError("");

    try {
      setDraftImage(await generateImage(post.image_prompt || post.caption));
    } catch (err) {
      setReviewError(friendlyError(err));
    } finally {
      setRegenerating(false);
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

  const topicError = validateTopic(request);
  const showTopicError = touched && Boolean(topicError);
  const ready = facebookConnected && allowed && !running && !topicError;
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
            <div className="mb-2 flex items-center justify-between gap-3">
              <label className="dx-label block text-sm" htmlFor="ap-topic">
                What is the post about?
              </label>
              <VoiceButton
                label="Say what the post is about"
                disabled={running}
                onText={(text) => {
                  setRequest((current) => (current.trim() ? `${current.trim()} ${text}` : text).slice(0, MAX_LENGTH));
                  setTouched(true);
                  setFailedStep(-1);
                }}
              />
            </div>
            <textarea
              id="ap-topic"
              value={request}
              onChange={(event) => {
                setRequest(event.target.value);
                setTouched(true);
                setFailedStep(-1);
              }}
              onBlur={() => setTouched(true)}
              rows={4}
              maxLength={MAX_LENGTH}
              disabled={running}
              aria-invalid={showTopicError}
              aria-describedby="ap-topic-error"
              placeholder="Example: A limited time offer for new customers this weekend."
              className="dx-input resize-y"
            />

            {showTopicError && (
              <p id="ap-topic-error" role="alert" className="dx-assist-status bad !mt-2">
                {topicError}
              </p>
            )}

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
                checked={reviewFirst}
                onChange={(event) => setReviewFirst(event.target.checked)}
                disabled={running || reviewing}
              />
              <span>Let me review and edit the post before it goes out</span>
            </label>

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
                onClick={() => run(0)}
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
                    {failedStep === index && !running && (
                      <button
                        type="button"
                        className="dx-btn-ghost ap-retry"
                        onClick={() => run(index)}
                        disabled={!ready}
                      >
                        Retry this step
                      </button>
                    )}
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

        {reviewing && (
          <div className="ap-review">
            <p className="ap-review-title">Review your post</p>

            <label className="dx-label text-sm" htmlFor="ap-review-text">
              Post text (caption, description and hashtags)
            </label>
            <textarea
              id="ap-review-text"
              className="dx-input resize-y"
              rows={8}
              value={draftText}
              maxLength={5000}
              onChange={(event) => {
                setDraftText(event.target.value);
                setReviewError("");
              }}
            />

            <p className="dx-label text-sm">Picture</p>
            <div className="ap-review-picture">
              {draftPreview ? (
                <img src={draftPreview} alt="Picture for your post" className="ap-result-image" />
              ) : (
                <p className="dx-assist-note !mt-0">This post has no picture.</p>
              )}

              <div className="sp-edit-picture">
                <label className="dx-btn-ghost dx-btn-sm sp-edit-file">
                  Upload your own picture
                  <input
                    type="file"
                    accept="image/*"
                    hidden
                    onChange={(event) => {
                      const file = event.target.files?.[0] || null;

                      if (file) {
                        setDraftImage(file);
                        setReviewError("");
                      }

                      event.target.value = "";
                    }}
                  />
                </label>
                <button
                  type="button"
                  className="dx-btn-ghost dx-btn-sm"
                  onClick={makeNewPicture}
                  disabled={regenerating}
                >
                  {regenerating ? "Creating a new picture..." : "Create a new AI picture"}
                </button>
                {draftImage && (
                  <button
                    type="button"
                    className="dx-btn-ghost dx-btn-sm"
                    onClick={() => setDraftImage(null)}
                    disabled={regenerating}
                  >
                    Remove the picture
                  </button>
                )}
              </div>
            </div>

            {reviewError && (
              <p role="alert" className="dx-assist-status bad">
                {reviewError}
              </p>
            )}

            <div className="sp-edit-actions">
              <button
                type="button"
                className="dx-btn ap-go"
                onClick={continueAfterReview}
                disabled={regenerating || !facebookConnected}
              >
                {mode === "now" ? "Looks good, post now" : "Looks good, schedule it"}
              </button>
              <button type="button" className="dx-btn-ghost" onClick={discardReview} disabled={regenerating}>
                Cancel
              </button>
            </div>
          </div>
        )}

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
