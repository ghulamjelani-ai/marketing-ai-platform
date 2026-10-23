import { useState } from "react";
import { postToText } from "../utils/parsePlan";
import "../polish.css";

// Guided steps under a marketing plan. Nothing happens until the user clicks:
// 1) add the text to the publisher, 2) generate a picture, 3) publish to Facebook.
export default function PostAssistant({ plan, assistant }) {
  const {
    facebookConnected,
    pageName,
    postText,
    hasImage,
    generatingImage,
    publishing,
    message,
    messageType,
    onUsePost,
    onGenerateImage,
    onPublish,
  } = assistant;

  const [selected, setSelected] = useState(0);
  const [textAdded, setTextAdded] = useState(false);
  const [imageAsked, setImageAsked] = useState(false);
  const [confirming, setConfirming] = useState(false);

  const post = plan.posts[selected];
  const imagePrompt =
    post.imagePrompt ||
    plan.imagePrompts[selected] ||
    plan.imagePrompts[0] ||
    "";

  const canPublish =
    facebookConnected && (postText.trim().length > 0 || hasImage);

  function choose(index) {
    setSelected(index);
    setTextAdded(false);
    setImageAsked(false);
    setConfirming(false);
  }

  function addText() {
    onUsePost(postToText(post));
    setTextAdded(true);
  }

  function makePicture() {
    setImageAsked(true);
    onGenerateImage(imagePrompt);
  }

  function publish() {
    setConfirming(false);
    onPublish();
  }

  return (
    <div className="dx-assist">
      <p className="dx-assist-title">
        Ready to post? I will ask before each step.
      </p>

      <div className="dx-assist-tabs">
        {plan.posts.map((_, index) => (
          <button
            key={index}
            type="button"
            className={`dx-assist-tab ${index === selected ? "on" : ""}`}
            onClick={() => choose(index)}
          >
            Post {index + 1}
          </button>
        ))}
      </div>

      <div className="dx-assist-preview">
        <p>
          <b>{post.caption}</b>
        </p>
        {post.description && <p>{post.description}</p>}
        {post.hashtags && <p className="dx-assist-tags">{post.hashtags}</p>}
      </div>

      <div className="dx-assist-step">
        <span className="dx-assist-num">{textAdded ? "✓" : "1"}</span>
        <div className="dx-assist-body">
          <p>Add this caption, description and hashtags to the publisher?</p>
          <button
            type="button"
            className="dx-btn dx-btn-sm"
            onClick={addText}
            disabled={!facebookConnected}
          >
            {textAdded ? "Added - add again" : "Yes, add to publisher"}
          </button>
        </div>
      </div>

      <div className="dx-assist-step">
        <span className="dx-assist-num">{hasImage ? "✓" : "2"}</span>
        <div className="dx-assist-body">
          <p>Create a picture for this post with AI?</p>
          {imagePrompt && (
            <p className="dx-assist-prompt">&ldquo;{imagePrompt}&rdquo;</p>
          )}
          <button
            type="button"
            className="dx-btn dx-btn-sm"
            onClick={makePicture}
            disabled={!facebookConnected || generatingImage || !imagePrompt}
          >
            {generatingImage
              ? "Creating picture..."
              : imageAsked && hasImage
                ? "Create another picture"
                : "Yes, create the picture"}
          </button>
        </div>
      </div>

      <div className="dx-assist-step">
        <span className="dx-assist-num">3</span>
        <div className="dx-assist-body">
          <p>
            Publish to{" "}
            <b>{pageName || "your connected Facebook Page"}</b>
            {hasImage ? " with the picture" : " as a text post"}?
          </p>

          {!confirming ? (
            <button
              type="button"
              className="dx-btn dx-btn-sm"
              onClick={() => setConfirming(true)}
              disabled={!canPublish || publishing}
            >
              {publishing ? "Publishing..." : "Publish to Facebook"}
            </button>
          ) : (
            <div className="dx-assist-confirm">
              <span>Post this publicly now?</span>
              <button
                type="button"
                className="dx-btn dx-btn-sm"
                onClick={publish}
              >
                Yes, publish
              </button>
              <button
                type="button"
                className="dx-btn-ghost dx-btn-sm"
                onClick={() => setConfirming(false)}
              >
                Cancel
              </button>
            </div>
          )}
        </div>
      </div>

      {!facebookConnected && (
        <p className="dx-assist-note">
          Connect your Facebook Page first (the button at the top of the
          dashboard) to use these steps.
        </p>
      )}

      {message && (
        <p
          className={`dx-assist-status ${
            messageType === "error" ? "bad" : messageType === "success" ? "ok" : ""
          }`}
        >
          {message}
        </p>
      )}
    </div>
  );
}
