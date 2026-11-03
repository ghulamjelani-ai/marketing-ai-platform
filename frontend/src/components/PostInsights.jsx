import { useCallback, useEffect, useState } from "react";
import { getInsights } from "../api/activity";

const showDate = (iso) => new Date(iso).toLocaleDateString([], { month: "short", day: "numeric" });

// How the latest published posts performed: reactions + comments + shares, from Facebook.
export default function PostInsights() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (refresh = false) => {
    setLoading(true);

    try {
      setData(await getInsights(refresh));
      setError("");
    } catch (err) {
      setError(err.message || "Could not load how your posts performed.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let off = false;

    getInsights(false)
      .then((result) => {
        if (!off) setData(result);
      })
      .catch((err) => {
        if (!off) setError(err.message || "Could not load how your posts performed.");
      })
      .finally(() => {
        if (!off) setLoading(false);
      });

    return () => {
      off = true;
    };
  }, []);

  const posts = data?.posts || [];
  const top = Math.max(1, ...posts.map((post) => post.engagement || 0));

  return (
    <section className="dx-card in-card rounded-3xl p-6 mb-6" aria-labelledby="in-title">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="dx-eyebrow">Performance</p>
          <h2 id="in-title" className="dx-title text-2xl mt-1">
            How your posts did
          </h2>
          <p className="dx-muted text-sm mt-1">
            Reactions, comments and shares on your latest posts, straight from Facebook.
          </p>
        </div>

        <button type="button" className="dx-btn-ghost dx-btn-sm" onClick={() => load(true)} disabled={loading}>
          {loading ? "Checking..." : "Refresh"}
        </button>
      </div>

      {error && <p className="dx-assist-status bad mt-4">{error}</p>}

      {!error && !loading && posts.length === 0 && (
        <p className="dx-muted text-sm mt-4">Publish a post and its results will appear here.</p>
      )}

      {data && posts.length > 0 && (
        <>
          <div className="pi-tiles">
            <div className="pi-tile">
              <span className="pi-num">{data.total}</span>
              <span className="pi-label">Total engagement</span>
            </div>
            <div className="pi-tile">
              <span className="pi-num">{data.measured ? data.average : "-"}</span>
              <span className="pi-label">Average per post</span>
            </div>
            <div className="pi-tile">
              <span className="pi-num">{data.measured}</span>
              <span className="pi-label">Posts measured</span>
            </div>
          </div>

          {data.measured === 0 && (
            <p className="dx-assist-note">
              Facebook has not returned numbers for these posts yet. New posts can take a little while.
            </p>
          )}

          <ul className="pi-list" aria-label="Engagement per post">
            {posts.map((post) => (
              <li key={post.id} className={`pi-row ${post.id === data.best_id ? "best" : ""}`}>
                <div className="pi-text">
                  <p className="pi-message">{post.message || "(picture only)"}</p>
                  <p className="pi-date">
                    {showDate(post.created_at)}
                    {post.id === data.best_id && <span className="dx-chip pi-best">Top post</span>}
                  </p>
                </div>
                <div className="pi-bar" aria-hidden="true">
                  <span style={{ width: `${((post.engagement || 0) / top) * 100}%` }} />
                </div>
                <span className="pi-score">{post.engagement === null ? "n/a" : post.engagement}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
