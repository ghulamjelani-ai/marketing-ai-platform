import { useEffect, useMemo, useState } from "react";
import { updateScheduled } from "../api/activity";
import { toast } from "../utils/toast";
import { changedFields, toLocalInput, validateEdit } from "../utils/editPost";

// The form for changing a scheduled post: text, publish time and picture.
export default function EditScheduledPost({ item, onSaved, onCancel }) {
  const [message, setMessage] = useState(item.message || "");
  const [when, setWhen] = useState(toLocalInput(item.run_at));
  const [image, setImage] = useState(null);
  const [removeImage, setRemoveImage] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const previewUrl = useMemo(() => (image ? URL.createObjectURL(image) : ""), [image]);

  useEffect(() => () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
  }, [previewUrl]);

  const hasPicture = Boolean(image) || (item.with_image && !removeImage);
  const form = { message, when, image, removeImage };

  async function save(event) {
    event.preventDefault();

    const problem = validateEdit({ message, when, hasPicture });

    if (problem) {
      setError(problem);
      return;
    }

    const changes = changedFields(item, form);

    if (Object.keys(changes).length === 0) {
      onCancel();
      return;
    }

    setSaving(true);
    setError("");

    try {
      await updateScheduled(item.id, changes);
      toast.success("Post updated", "Your changes are saved and the new time is set.");
      onSaved();
    } catch (err) {
      setError(err.message || "Could not save your changes. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="sp-edit" onSubmit={save} noValidate>
      <label className="dx-label sp-edit-label" htmlFor={`edit-text-${item.id}`}>
        Post text
      </label>
      <textarea
        id={`edit-text-${item.id}`}
        className="dx-input resize-y"
        rows={6}
        value={message}
        maxLength={5000}
        disabled={saving}
        onChange={(event) => {
          setMessage(event.target.value);
          setError("");
        }}
      />

      <label className="dx-label sp-edit-label" htmlFor={`edit-when-${item.id}`}>
        Publish at
      </label>
      <input
        id={`edit-when-${item.id}`}
        type="datetime-local"
        className="dx-input sp-edit-when"
        value={when}
        disabled={saving}
        onChange={(event) => {
          setWhen(event.target.value);
          setError("");
        }}
      />

      <p className="dx-label sp-edit-label">Picture</p>

      {previewUrl && <img src={previewUrl} alt="New picture preview" className="sp-edit-preview" />}

      {item.with_image && !image && (
        <p className="dx-assist-note !mt-0">
          {removeImage
            ? "The picture will be removed from this post."
            : "This post has a picture. Choose a new one to replace it, or remove it."}
        </p>
      )}

      <div className="sp-edit-picture">
        <label className="dx-btn-ghost dx-btn-sm sp-edit-file">
          {item.with_image || image ? "Choose a new picture" : "Add a picture"}
          <input
            type="file"
            accept="image/*"
            hidden
            disabled={saving}
            onChange={(event) => {
              const file = event.target.files?.[0] || null;
              setImage(file);
              setRemoveImage(false);
              setError("");
              event.target.value = "";
            }}
          />
        </label>

        {image && (
          <button type="button" className="dx-btn-ghost dx-btn-sm" onClick={() => setImage(null)} disabled={saving}>
            Keep the old picture
          </button>
        )}

        {item.with_image && !image && (
          <label className="dx-check">
            <input
              type="checkbox"
              checked={removeImage}
              disabled={saving}
              onChange={(event) => {
                setRemoveImage(event.target.checked);
                setError("");
              }}
            />
            <span>Remove the picture</span>
          </label>
        )}
      </div>

      {error && (
        <p role="alert" className="dx-assist-status bad">
          {error}
        </p>
      )}

      <div className="sp-edit-actions">
        <button type="submit" className="dx-btn dx-btn-sm" disabled={saving}>
          {saving ? "Saving..." : "Save changes"}
        </button>
        <button type="button" className="dx-btn-ghost dx-btn-sm" onClick={onCancel} disabled={saving}>
          Cancel
        </button>
      </div>
    </form>
  );
}
