import { useCallback, useEffect, useRef, useState } from "react";

import "../dashboard.css";
import Navbar from "../components/Navbar";
import Confetti from "../components/Confetti";
import useSpotlight from "../hooks/useSpotlight";
import ChatBox from "../components/ChatBox";
import AutoPoster from "../components/AutoPoster";
import Autopilot from "../components/Autopilot";
import ActivityPanel from "../components/ActivityPanel";
import {
  AutomationPipeline,
  WorkflowFeed,
  StatCard,
} from "../components/AutomationFlow";

import { useAuth } from "../context/AuthContext";

import {
  connectFacebook,
  disconnectFacebook,
  getFacebookStatus,
  publishFacebookPhoto,
  publishFacebookPost,
} from "../api/facebook";
import { generateImage } from "../api/images";
import { getPublishedPosts, getScheduled } from "../api/activity";

import "../polish.css";

const HEADLINE = [
  { text: "Create" },
  { text: "Marketing" },
  { text: "Plans" },
  { text: "&" },
  { text: "Social", gold: true },
  { text: "Posts", gold: true },
  { text: "for" },
  { text: "Your" },
  { text: "Business" },
];

// Loads the published-post history and the scheduled posts. Returns null on failure.
async function fetchActivity() {
  try {
    // Scheduled posts first: that call records posts that went live since the last visit.
    const scheduled = await getScheduled();
    const published = await getPublishedPosts();

    return {
      posts: published.posts,
      total: published.total,
      upcoming: scheduled.upcoming,
      past: scheduled.past,
    };
  } catch (error) {
    console.error("Activity load error:", error);
    return null;
  }
}

export default function Home() {
  const { user } = useAuth();

  useSpotlight();

  const fileInputRef = useRef(null);

  const [facebookConnected, setFacebookConnected] = useState(false);

  const [facebookPageName, setFacebookPageName] = useState("");

  const [checkingFacebook, setCheckingFacebook] = useState(true);

  const [connecting, setConnecting] = useState(false);

  const [publishing, setPublishing] = useState(false);

  const [disconnecting, setDisconnecting] = useState(false);

  const [postText, setPostText] = useState("");

  const [imagePrompt, setImagePrompt] = useState("");

  const [generatingImage, setGeneratingImage] = useState(false);

  const [selectedImage, setSelectedImage] = useState(null);

  const [imagePreview, setImagePreview] = useState("");

  const [publishedCount, setPublishedCount] = useState(0);

  // History of published posts and the scheduled posts, loaded from the backend.
  const [activity, setActivity] = useState({
    posts: [],
    total: 0,
    upcoming: [],
    past: [],
  });

  const refreshActivity = useCallback(async () => {
    const data = await fetchActivity();

    if (data) {
      setActivity(data);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

    fetchActivity().then((data) => {
      if (data && !cancelled) {
        setActivity(data);
      }
    });

    return () => {
      cancelled = true;
    };
  }, []);

  const [message, setMessage] = useState("");

  const [messageType, setMessageType] = useState("");

  // =======================================================
  // LOAD FACEBOOK STATUS
  // =======================================================

  useEffect(() => {
    loadFacebookStatus();

    const params = new URLSearchParams(window.location.search);

    const facebookResult = params.get("facebook");

    if (facebookResult === "connected") {
      setMessage("Facebook Page connected successfully.");

      setMessageType("success");

      window.history.replaceState({}, document.title, window.location.pathname);
    }

    if (facebookResult === "error") {
      setMessage("Facebook connection was cancelled or failed.");

      setMessageType("error");

      window.history.replaceState({}, document.title, window.location.pathname);
    }
  }, []);

  // =======================================================
  // CLEAN IMAGE PREVIEW MEMORY
  // =======================================================

  useEffect(() => {
    return () => {
      if (imagePreview) {
        URL.revokeObjectURL(imagePreview);
      }
    };
  }, [imagePreview]);

  // =======================================================
  // FACEBOOK STATUS
  // =======================================================

  async function loadFacebookStatus() {
    try {
      setCheckingFacebook(true);

      const data = await getFacebookStatus();

      setFacebookConnected(Boolean(data?.connected));

      setFacebookPageName(data?.page_name || "");
    } catch (error) {
      console.error("Facebook status error:", error);
    } finally {
      setCheckingFacebook(false);
    }
  }

  // =======================================================
  // CONNECT FACEBOOK
  // =======================================================

  async function handleFacebookConnect() {
    try {
      setConnecting(true);

      setMessage("");
      setMessageType("");

      await connectFacebook();
    } catch (error) {
      setMessage(error.message || "Facebook connection failed.");

      setMessageType("error");

      setConnecting(false);
    }
  }

  // =======================================================
  // SELECT IMAGE
  // =======================================================

  function handleImageChange(event) {
    const file = event.target.files?.[0];

    if (!file) {
      return;
    }

    if (!file.type.startsWith("image/")) {
      setMessage("Please select a valid image file.");

      setMessageType("error");

      return;
    }

    const maxFileSize = 15 * 1024 * 1024;

    if (file.size > maxFileSize) {
      setMessage("Image is too large. Maximum size is 15 MB.");

      setMessageType("error");

      return;
    }

    if (imagePreview) {
      URL.revokeObjectURL(imagePreview);
    }

    const previewUrl = URL.createObjectURL(file);

    setSelectedImage(file);
    setImagePreview(previewUrl);

    setMessage("");
    setMessageType("");
  }

  // =======================================================
  // REMOVE IMAGE
  // =======================================================

  function removeSelectedImage() {
    if (imagePreview) {
      URL.revokeObjectURL(imagePreview);
    }

    setSelectedImage(null);
    setImagePreview("");

    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }

  // =======================================================
  // CHAT ASSISTANT HELPERS
  // =======================================================

  function scrollToPublisher() {
    document
      .getElementById("facebook-publisher")
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function handleUsePost(text) {
    setPostText(text);

    setMessage("Post text added to the publisher. Review it, then continue.");
    setMessageType("success");

    scrollToPublisher();
  }

  // =======================================================
  // GENERATE IMAGE WITH AI
  // =======================================================

  async function handleGenerateImage(promptOverride) {
    // The chat assistant passes the prompt as text; the button passes a click event.
    const fromChat = typeof promptOverride === "string";
    const prompt = (fromChat ? promptOverride : imagePrompt).trim();

    if (!prompt) {
      setMessage("Describe the image you want the AI to create.");

      setMessageType("error");

      return;
    }

    try {
      setGeneratingImage(true);

      setMessage("");
      setMessageType("");

      if (fromChat) {
        setImagePrompt(prompt);
      }

      const file = await generateImage(prompt);

      if (imagePreview) {
        URL.revokeObjectURL(imagePreview);
      }

      setSelectedImage(file);
      setImagePreview(URL.createObjectURL(file));

      setMessage("Image generated. Review it below, then publish it.");

      setMessageType("success");

      if (fromChat) {
        scrollToPublisher();
      }
    } catch (error) {
      setMessage(error.message || "Image generation failed.");

      setMessageType("error");
    } finally {
      setGeneratingImage(false);
    }
  }

  // =======================================================
  // PUBLISH FACEBOOK POST
  // =======================================================

  async function handlePublish() {
    if (!postText.trim() && !selectedImage) {
      setMessage("Please write some content or select an image.");

      setMessageType("error");

      return;
    }

    try {
      setPublishing(true);

      setMessage("");
      setMessageType("");

      let result;

      if (selectedImage) {
        result = await publishFacebookPhoto(postText, selectedImage);
      } else {
        result = await publishFacebookPost(postText);
      }

      if (selectedImage) {
        setMessage("Photo published successfully to your Facebook Page.");
      } else {
        setMessage(
          result?.post_id
            ? `Facebook post published successfully. Post ID: ${result.post_id}`
            : "Facebook post published successfully.",
        );
      }

      setMessageType("success");

      setPublishedCount((count) => count + 1);

      refreshActivity();

      setPostText("");

      removeSelectedImage();
    } catch (error) {
      setMessage(error.message || "Facebook publishing failed.");

      setMessageType("error");
    } finally {
      setPublishing(false);
    }
  }

  // =======================================================
  // DISCONNECT FACEBOOK
  // =======================================================

  async function handleDisconnect() {
    try {
      setDisconnecting(true);

      setMessage("");
      setMessageType("");

      await disconnectFacebook();

      setFacebookConnected(false);
      setFacebookPageName("");

      setPostText("");

      removeSelectedImage();

      setMessage("Facebook Page disconnected successfully.");

      setMessageType("success");
    } catch (error) {
      setMessage(error.message || "Could not disconnect Facebook.");

      setMessageType("error");
    } finally {
      setDisconnecting(false);
    }
  }

  return (
    <div className="dx-page">
      <div className="dx-grid-bg" />
      <div className="dx-cursor" />
      <Confetti burst={publishedCount} />
      <span className="dx-bg-orb dx-bg-orb-1" />
      <span className="dx-bg-orb dx-bg-orb-2" />

      <Navbar />

      <main className="dx-main max-w-7xl mx-auto px-5 py-8">
        <AutomationPipeline />

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 my-8">
          <StatCard
            value={checkingFacebook ? "…" : facebookConnected ? "Connected" : "Not connected"}
            label="Facebook Page"
            color={facebookConnected ? "#4ade80" : "var(--accent)"}
            path="M0 30 L25 28 L45 18 L70 22 L110 6"
            delay="dx-d1"
          />
          <StatCard
            value={activity.total}
            label="Posts published"
            path="M0 40 L30 28 L50 32 L75 14 L110 6"
            delay="dx-d2"
          />
          <StatCard
            value={activity.upcoming.length}
            label="Posts scheduled"
            color="#4ade80"
            path="M0 34 L25 36 L45 20 L70 24 L110 8"
            delay="dx-d3"
          />
          <StatCard
            value="24/7"
            label="AI assistant availability"
            path="M0 20 L40 18 L70 12 L110 8"
            delay="dx-d4"
          />
        </div>

        <Autopilot
          facebookConnected={facebookConnected}
          pageName={facebookPageName}
          onDone={(kind) => {
            if (kind === "published") {
              setPublishedCount((count) => count + 1);
            }

            refreshActivity();
          }}
        />

        <section className="grid lg:grid-cols-[1.1fr_0.9fr] gap-8 items-stretch mt-8">
          <div>
            {/* =================================================
                HERO
            ================================================= */}

            <div className="dx-card dx-hero dx-rise rounded-3xl p-8 mb-8">
              <p className="dx-eyebrow">AI Powered Marketing</p>

              <h1 className="dx-h1 text-4xl md:text-6xl mt-4" aria-label="Create Marketing Plans and Social Posts for Your Business">
                {HEADLINE.map((word, i) => (
                  <span key={i} aria-hidden="true">
                    <span
                      className={`dx-word ${word.gold ? "dx-gold-text" : ""}`}
                      style={{ "--i": i }}
                    >
                      {word.text}
                    </span>{" "}
                  </span>
                ))}
              </h1>

              <p className="dx-muted mt-5 text-lg max-w-2xl">
                Welcome {user?.name}. Chat with our AI, create your marketing
                plan, generate social content, and publish directly to your
                connected Facebook Page.
              </p>

              <div className="mt-8 flex flex-wrap gap-4">
                <button className="dx-btn">Start Marketing Plan</button>

                {!facebookConnected ? (
                  <button
                    onClick={handleFacebookConnect}
                    disabled={connecting || checkingFacebook}
                    className="dx-btn-ghost"
                  >
                    {checkingFacebook
                      ? "Checking Facebook..."
                      : connecting
                        ? "Connecting..."
                        : "Connect Facebook Page"}
                  </button>
                ) : (
                  <div className="flex items-center gap-3">
                    <div className="dx-badge-ok px-5 py-2">
                      <p className="text-xs opacity-80">Facebook Connected</p>

                      <p className="text-sm font-semibold">
                        {facebookPageName || "Facebook Page"}
                      </p>
                    </div>

                    <button
                      onClick={handleDisconnect}
                      disabled={disconnecting}
                      className="dx-btn-ghost"
                    >
                      {disconnecting ? "Disconnecting..." : "Disconnect"}
                    </button>
                  </div>
                )}
              </div>
            </div>

            {/* =================================================
                MESSAGE
            ================================================= */}

            {message && (
              <div
                className={`dx-alert ${
                  messageType === "success"
                    ? "dx-alert-success"
                    : messageType === "error"
                      ? "dx-alert-error"
                      : "dx-alert-info"
                }`}
              >
                <p className="text-sm font-medium">{message}</p>
              </div>
            )}

            {/* =================================================
                FACEBOOK PUBLISHER
            ================================================= */}

            {facebookConnected && (
              <div
                id="facebook-publisher"
                className="dx-card dx-rise rounded-3xl p-7 mb-8"
              >
                <div className="flex flex-wrap items-center justify-between gap-4">
                  <div>
                    <p className="dx-eyebrow">Facebook Publisher</p>

                    <h2 className="dx-title text-3xl mt-2">
                      Create Your Facebook Post
                    </h2>

                    <p className="mt-2 text-sm dx-faint">
                      Publishing to{" "}
                      <span className="font-semibold dx-strong">
                        {facebookPageName || "your connected Page"}
                      </span>
                    </p>
                  </div>

                  <div className="dx-badge-ok px-4 py-2 text-sm font-semibold">
                    ✓ Connected
                  </div>
                </div>

                {/* =============================================
                    POST CAPTION
                ============================================= */}

                <div className="mt-7">
                  <label className="dx-label block text-sm mb-2">
                    Post Caption
                  </label>

                  <textarea
                    value={postText}
                    onChange={(event) => setPostText(event.target.value)}
                    rows={7}
                    maxLength={5000}
                    placeholder="Write your Facebook post here..."
                    className="dx-input resize-y"
                  />

                  <div className="mt-2 flex justify-end">
                    <span className="text-xs dx-faint">
                      {postText.length} characters
                    </span>
                  </div>
                </div>

                {/* =============================================
                    IMAGE UPLOAD
                ============================================= */}

                <div className="mt-6">
                  <label className="dx-label block text-sm mb-2">
                    Generate Image with AI
                  </label>

                  <div className="flex flex-wrap gap-3">
                    <input
                      value={imagePrompt}
                      onChange={(event) => setImagePrompt(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" && !generatingImage) {
                          handleGenerateImage();
                        }
                      }}
                      maxLength={1000}
                      placeholder="Example: fresh sourdough bread on a rustic table, warm light"
                      className="dx-input flex-1 min-w-[220px]"
                    />

                    <button
                      type="button"
                      onClick={handleGenerateImage}
                      disabled={generatingImage || publishing}
                      className="dx-btn"
                    >
                      {generatingImage ? "Generating..." : "Generate Image"}
                    </button>
                  </div>
                </div>

                <div className="mt-6">
                  <label className="dx-label block text-sm mb-2">
                    Upload Photo
                  </label>

                  {!imagePreview ? (
                    <label className="dx-drop">
                      <div>
                        <div className="dx-plus">+</div>

                        <p className="mt-4 font-semibold dx-accent-text">
                          Choose Photo From Computer
                        </p>

                        <p className="mt-1 text-xs dx-faint">
                          JPG, JPEG, PNG, WEBP or another image format
                        </p>

                        <p className="mt-1 text-xs dx-faint">
                          Maximum file size: 15 MB
                        </p>
                      </div>

                      <input
                        ref={fileInputRef}
                        type="file"
                        accept="image/*"
                        onChange={handleImageChange}
                        className="hidden"
                      />
                    </label>
                  ) : (
                    <div className="dx-preview">
                      <div className="dx-preview-bg">
                        <img
                          src={imagePreview}
                          alt="Facebook post preview"
                          className="mx-auto max-h-[500px] w-full rounded-xl object-contain"
                        />
                      </div>

                      <div className="flex flex-wrap items-center justify-end gap-4 p-4">
                        <button
                          type="button"
                          onClick={removeSelectedImage}
                          disabled={publishing}
                          className="dx-btn-danger"
                        >
                          Remove Photo
                        </button>
                      </div>
                    </div>
                  )}
                </div>

                {/* =============================================
                    PUBLISH BUTTON
                ============================================= */}

                <div className="mt-7 flex flex-wrap items-center gap-4">
                  <button
                    onClick={handlePublish}
                    disabled={publishing}
                    className="dx-btn"
                  >
                    {publishing
                      ? "Publishing..."
                      : selectedImage
                        ? "Post Photo to Facebook"
                        : "Post to Facebook"}
                  </button>

                  <p className="text-xs dx-faint">
                    {selectedImage
                      ? "Your photo and caption will be published together."
                      : "Add a photo if you want to publish an image post."}
                  </p>
                </div>
              </div>
            )}

            <WorkflowFeed />

            {/* =================================================
                FEATURE CARDS
            ================================================= */}

            <div className="grid md:grid-cols-3 gap-5">
              <div className="dx-card dx-hover dx-tilt dx-rise dx-d2 rounded-2xl p-5">
                <div className="dx-feature-icon">🎯</div>
                <h3 className="dx-title text-xl">AI Strategy</h3>

                <p className="text-sm dx-muted mt-2">
                  AI understands your business and creates a practical marketing
                  direction.
                </p>
              </div>

              <div className="dx-card dx-hover dx-tilt dx-rise dx-d3 rounded-2xl p-5">
                <div className="dx-feature-icon">✨</div>
                <h3 className="dx-title text-xl">Post Ideas</h3>

                <p className="text-sm dx-muted mt-2">
                  Generate captions, questions, hooks, and content plans for
                  social media.
                </p>
              </div>

              <div className="dx-card dx-hover dx-tilt dx-rise dx-d4 rounded-2xl p-5">
                <div className="dx-feature-icon">🚀</div>
                <h3 className="dx-title text-xl">Facebook Sharing</h3>

                <p className="text-sm dx-muted mt-2">
                  Connect your Facebook Page, upload photos, and publish
                  directly from your dashboard.
                </p>
              </div>
            </div>
          </div>

          {/* ===================================================
              AI CHAT
          =================================================== */}

          <ChatBox
            assistant={{
              facebookConnected,
              pageName: facebookPageName,
              postText,
              hasImage: Boolean(selectedImage),
              generatingImage,
              publishing,
              message,
              messageType,
              publishedCount,
              onUsePost: handleUsePost,
              onGenerateImage: handleGenerateImage,
              onPublish: handlePublish,
            }}
          />
        </section>

        <AutoPoster
          facebookConnected={facebookConnected}
          pageName={facebookPageName}
          upcoming={activity.upcoming}
          past={activity.past}
          onChanged={refreshActivity}
        />

        <ActivityPanel posts={activity.posts} total={activity.total} />
      </main>
    </div>
  );
}
