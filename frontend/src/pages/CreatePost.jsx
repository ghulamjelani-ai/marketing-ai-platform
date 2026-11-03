import { useEffect, useRef, useState } from "react";

import ChatBox from "../components/ChatBox";
import useWorkspace from "../hooks/useWorkspace";
import { publishFacebookPhoto, publishFacebookPost } from "../api/facebook";
import { generateImage } from "../api/images";

// Create post: the AI chat on one side, the Facebook publisher on the other.
export default function CreatePost() {
  const { facebookConnected, pageName, publishedCount, onPublished } = useWorkspace();

  const fileInputRef = useRef(null);

  const [publishing, setPublishing] = useState(false);

  const [postText, setPostText] = useState("");

  const [imagePrompt, setImagePrompt] = useState("");

  const [generatingImage, setGeneratingImage] = useState(false);

  const [selectedImage, setSelectedImage] = useState(null);

  const [imagePreview, setImagePreview] = useState("");

  const [message, setMessage] = useState("");

  const [messageType, setMessageType] = useState("");

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

      onPublished();

      setPostText("");

      removeSelectedImage();
    } catch (error) {
      setMessage(error.message || "Facebook publishing failed.");

      setMessageType("error");
    } finally {
      setPublishing(false);
    }
  }

  return (
    <section className="grid lg:grid-cols-[1.1fr_0.9fr] gap-8 items-stretch">
      <div>
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

        {!facebookConnected ? (
          <div className="dx-card dx-rise rounded-3xl p-7">
            <p className="dx-eyebrow">Facebook Publisher</p>
            <h2 className="dx-title text-3xl mt-2">Create Your Facebook Post</h2>
            <p className="mt-3 text-sm dx-muted">
              Connect your Facebook Page with the button above to publish from
              here. You can already chat with the AI to plan and write posts.
            </p>
          </div>
        ) : (
          <div
            id="facebook-publisher"
            className="dx-card dx-rise rounded-3xl p-7"
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
                    {pageName || "your connected Page"}
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
      </div>

      {/* ===================================================
          AI CHAT
      =================================================== */}

      <ChatBox
        assistant={{
          facebookConnected,
          pageName,
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
  );
}
