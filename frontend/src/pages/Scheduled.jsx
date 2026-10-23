import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import Navbar from "../components/Navbar";
import {
  cancelAllScheduled,
  cancelScheduled,
  getScheduled,
} from "../api/activity";
import "../dashboard.css";
import "../polish.css";

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
  const [data, setData] = useState({ upcoming: [], past: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState("");

  const load = useCallback(async () => {
    try {
      const result = await getScheduled();
      setData({ upcoming: result.upcoming || [], past: result.past || [] });
      setError("");
    } catch (err) {
      setError(err.message || "Could not load your scheduled posts.");
    } finally {
      setLoading(false);
    }
  }, []);

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

  return (
    <div className="dx-page min-h-screen">
      <Navbar />
      <main className="sp-page">
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
            <Link to="/home" className="dx-btn-ghost">
              &larr; Back to dashboard
            </Link>
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
              Use Autopilot or the 7-day plan on the dashboard to schedule
              posts.
            </p>
          </div>
        )}

        <div className="mt-8 space-y-3">
          {data.upcoming.map((item) => (
            <div key={item.id} className="sp-item">
              <div className="min-w-0">
                <p className="sp-when">
                  🗓️ {showMoment(item.run_at)}
                  {item.with_image && " · with picture"}
                </p>
                <p className="sp-text">{item.message}</p>
              </div>
              <button
                type="button"
                className="dx-btn-danger"
                onClick={() => cancelOne(item.id)}
                disabled={busyId === item.id || busyId === "all"}
              >
                Remove
              </button>
            </div>
          ))}
        </div>

        {data.past.length > 0 && (
          <>
            <h2 className="dx-title text-lg mt-10">Earlier</h2>
            <div className="mt-3 space-y-2">
              {data.past.map((item) => (
                <div key={item.id} className="sp-item" style={{ opacity: 0.75 }}>
                  <div className="min-w-0">
                    <p className="sp-when">{showMoment(item.run_at)}</p>
                    <p className="sp-text">{item.message}</p>
                  </div>
                  <span className="dx-chip">
                    {STATUS_LABEL[item.status] || item.status}
                  </span>
                </div>
              ))}
            </div>
          </>
        )}
      </main>
    </div>
  );
}
