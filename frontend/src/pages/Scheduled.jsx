import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import useWorkspace from "../hooks/useWorkspace";
import {
  cancelAllScheduled,
  cancelScheduled,
  clearAllEarlier,
  clearEarlier,
  getScheduled,
} from "../api/activity";
import { toast } from "../utils/toast";
import { canEdit } from "../utils/editPost";
import EditScheduledPost from "../components/EditScheduledPost";

const STATUS_LABEL = {
  published: "Published",
  cancelled: "Cancelled",
  removed: "Removed",
};

const showMoment = (iso) =>
  new Date(iso).toLocaleString([], {
    weekday: "long",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

export default function Scheduled() {
  const { refreshActivity } = useWorkspace();
  const [data, setData] = useState({ upcoming: [], past: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState("");
  const [editingId, setEditingId] = useState("");

  const load = useCallback(async () => {
    try {
      const result = await getScheduled();
      setData({ upcoming: result.upcoming || [], past: result.past || [] });
      setError("");
      refreshActivity();
    } catch (err) {
      setError(err.message || "Could not load your scheduled posts.");
    } finally {
      setLoading(false);
    }
  }, [refreshActivity]);

  useEffect(() => {
    let cancelled = false;

    getScheduled()
      .then((result) => {
        if (!cancelled) {
          setData({ upcoming: result.upcoming || [], past: result.past || [] });
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err.message || "Could not load your scheduled posts.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  async function cancelOne(id) {
    if (!window.confirm("Remove this scheduled post? It will not be published.")) {
      return;
    }

    setBusyId(id);
    setError("");

    try {
      await cancelScheduled(id);
      await load();
    } catch (err) {
      setError(err.message || "Could not remove the post.");
    } finally {
      setBusyId("");
    }
  }

  async function cancelEverything() {
    if (!window.confirm("Remove all scheduled posts?")) return;

    setBusyId("all");
    setError("");

    try {
      const result = await cancelAllScheduled();

      if (result.failed) {
        setError(`${result.failed} posts could not be removed. Try again.`);
      }

      await load();
    } catch (err) {
      setError(err.message || "Could not remove the posts.");
    } finally {
      setBusyId("");
    }
  }

  // Finished posts only leave this list; Facebook and the History are not changed.
  async function clearOne(id) {
    setBusyId(id);
    setError("");

    try {
      await clearEarlier(id);
      setData((value) => ({ ...value, past: value.past.filter((item) => item.id !== id) }));
      toast.success("Cleared", "The post was removed from this list.");
      await load();
    } catch (err) {
      toast.error("Could not clear the post", err.message);
      await load();
    } finally {
      setBusyId("");
    }
  }

  async function clearEverythingEarlier() {
    if (!window.confirm("Clear all earlier posts from this list? Published posts stay in your History.")) return;

    setBusyId("earlier");
    setError("");

    try {
      const result = await clearAllEarlier();
      setData((value) => ({ ...value, past: [] }));
      toast.success("List cleared", `${result.cleared} earlier ${result.cleared === 1 ? "post was" : "posts were"} cleared.`);
      await load();
    } catch (err) {
      toast.error("Could not clear the list", err.message);
    } finally {
      setBusyId("");
    }
  }

  const clearing = busyId === "earlier";

  return (
    <section className="sp-page">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="dx-eyebrow">Your queue</p>
            <h1 className="dx-title text-3xl mt-2">Scheduled posts</h1>
            <p className="mt-2 text-sm dx-muted">
              Facebook publishes these for you at the time shown. Remove any
              post before it goes out.
            </p>
          </div>

          <div className="flex flex-wrap gap-3">
            {data.upcoming.length > 0 && (
              <button
                type="button"
                className="dx-btn-danger"
                onClick={cancelEverything}
                disabled={busyId === "all"}
              >
                Remove all
              </button>
            )}
          </div>
        </div>

        {error && <p className="dx-assist-status bad mt-5">{error}</p>}
        {loading && <p className="dx-muted mt-8">Loading...</p>}

        {!loading && data.upcoming.length === 0 && (
          <div className="dx-card rounded-3xl sp-empty mt-8">
            <p className="dx-title text-xl">Nothing is scheduled</p>
            <p className="dx-muted text-sm mt-2">
              Use <Link to="/autopilot" className="dx-accent-text">Autopilot</Link> or
              the <Link to="/plan" className="dx-accent-text">7-day plan</Link> to
              schedule posts.
            </p>
          </div>
        )}

        <div className="mt-8 space-y-3">
          {data.upcoming.map((item) => (
            <div key={item.id} className={`sp-item ${editingId === item.id ? "sp-editing" : ""}`}>
              {editingId === item.id ? (
                <EditScheduledPost
                  item={item}
                  onCancel={() => setEditingId("")}
                  onSaved={() => {
                    setEditingId("");
                    load();
                  }}
                />
              ) : (
                <>
                  <div className="min-w-0">
                    <p className="sp-when">
                      🗓️ {showMoment(item.run_at)}
                      {item.with_image && " · with picture"}
                    </p>
                    <p className="sp-text">{item.message}</p>
                  </div>
                  <div className="sp-actions">
                    <button
                      type="button"
                      className="dx-btn-ghost dx-btn-sm"
                      onClick={() => setEditingId(item.id)}
                      disabled={!canEdit(item.run_at) || busyId === item.id || busyId === "all"}
                      title={
                        canEdit(item.run_at)
                          ? "Change the text, time or picture"
                          : "This post goes out in less than 10 minutes and can no longer be changed"
                      }
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      className="dx-btn-danger"
                      onClick={() => cancelOne(item.id)}
                      disabled={busyId === item.id || busyId === "all"}
                    >
                      Remove
                    </button>
                  </div>
                </>
              )}
            </div>
          ))}
        </div>

        {data.past.length > 0 && (
          <>
            <div className="mt-10 flex flex-wrap items-center justify-between gap-3">
              <h2 className="dx-title text-lg">Earlier</h2>
              {data.past.length > 1 && (
                <button
                  type="button"
                  className="dx-btn-ghost dx-btn-sm"
                  onClick={clearEverythingEarlier}
                  disabled={clearing || busyId !== ""}
                >
                  {clearing ? "Clearing..." : "Clear all"}
                </button>
              )}
            </div>
            <div className="mt-3 space-y-2">
              {data.past.map((item) => (
                <div key={item.id} className="sp-item sp-past">
                  <div className="min-w-0">
                    <p className="sp-when">{showMoment(item.run_at)}</p>
                    <p className="sp-text">{item.message}</p>
                  </div>
                  <div className="sp-past-actions">
                    <span className="dx-chip">
                      {STATUS_LABEL[item.status] || item.status}
                    </span>
                    <button
                      type="button"
                      className="dx-btn-ghost dx-btn-sm"
                      onClick={() => clearOne(item.id)}
                      disabled={busyId === item.id || clearing}
                      aria-label={`Clear this ${(STATUS_LABEL[item.status] || item.status).toLowerCase()} post from the list`}
                    >
                      {busyId === item.id ? "Clearing..." : "Clear"}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
    </section>
  );
}
