import { useCallback, useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

import "../dashboard.css";
import "../polish.css";
import Navbar from "./Navbar";
import Confetti from "./Confetti";
import PageSwitcher from "./PageSwitcher";
import useSpotlight from "../hooks/useSpotlight";
import useDocumentTitle from "../hooks/useDocumentTitle";
import { toast } from "../utils/toast";
import {
  connectFacebook,
  disconnectFacebook,
  getFacebookStatus,
} from "../api/facebook";
import { getPublishedPosts, getScheduled } from "../api/activity";
import { SECTIONS } from "./sections";
import { CHANNEL, clearConnecting } from "../utils/facebookConnect";

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

// The pop-up says what happened after the user came back from Facebook.
function announceFacebook(result, pages = 1) {
  if (result === "connected") {
    toast.success(
      "Facebook connected",
      pages > 1
        ? `You manage ${pages} Pages: choose where to post under "Posting to".`
        : "Your Facebook Page is ready for posts.",
    );
  } else {
    toast.error("Facebook not connected", "The connection was cancelled or failed. Please try again.");
  }
}

// ?facebook=connected|error&pages=N comes back when the whole page went to Facebook
// (the browser blocked the small window).
function showFacebookResult() {
  const params = new URLSearchParams(window.location.search);
  const result = params.get("facebook");

  if (!result) return;

  window.history.replaceState({}, document.title, window.location.pathname);
  announceFacebook(result, Number(params.get("pages") || 1));
}

// The frame around every signed-in page: navbar, section tabs, the Facebook bar,
// and the state the pages share.
export default function DashboardLayout() {
  useSpotlight();

  const { pathname } = useLocation();
  useDocumentTitle(SECTIONS.find((section) => section.to === pathname)?.label);

  const [facebook, setFacebook] = useState({ checking: true, connected: false, pageName: "" });
  const [connecting, setConnecting] = useState(false);
  // True while the small Facebook window is open and we wait for it to finish.
  const [waitingForFacebook, setWaitingForFacebook] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);
  const [publishedCount, setPublishedCount] = useState(0);
  const [activity, setActivity] = useState({ posts: [], total: 0, upcoming: [], past: [] });

  const refreshActivity = useCallback(async () => {
    const data = await fetchActivity();

    if (data) {
      setActivity(data);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

    showFacebookResult();

    getFacebookStatus()
      .then((data) => {
        if (!cancelled) {
          setFacebook({ checking: false, connected: Boolean(data?.connected), pageName: data?.page_name || "" });
        }
      })
      .catch((error) => {
        console.error("Facebook status error:", error);
        if (!cancelled) setFacebook((value) => ({ ...value, checking: false }));
      });

    fetchActivity().then((data) => {
      if (data && !cancelled) {
        setActivity(data);
      }
    });

    return () => {
      cancelled = true;
    };
  }, []);

  const stopWaiting = useCallback(() => {
    clearConnecting();
    setWaitingForFacebook(false);
    setConnecting(false);
  }, []);

  // While the Facebook window is open: listen for its "done" message, and also check the
  // connection every few seconds in case the message gets lost. Gives up after 3 minutes.
  useEffect(() => {
    if (!waitingForFacebook) return undefined;

    let finished = false;

    const finish = async (payload) => {
      if (finished) return;
      finished = true;
      stopWaiting();

      if (payload?.result === "connected") {
        try {
          const data = await getFacebookStatus();
          setFacebook({ checking: false, connected: Boolean(data?.connected), pageName: data?.page_name || "" });
        } catch (error) {
          console.error("Facebook status error:", error);
        }

        refreshActivity();
      }

      announceFacebook(payload?.result, payload?.pages);
    };

    const channel = typeof BroadcastChannel === "undefined" ? null : new BroadcastChannel(CHANNEL);

    if (channel) {
      channel.onmessage = (event) => finish(event.data);
    }

    const poll = setInterval(async () => {
      try {
        const data = await getFacebookStatus();

        if (data?.connected) finish({ result: "connected", pages: 1 });
      } catch {
        // keep waiting; the next check tries again
      }
    }, 3000);

    const giveUp = setTimeout(() => {
      if (!finished) {
        finished = true;
        stopWaiting();
      }
    }, 3 * 60 * 1000);

    return () => {
      finished = true;
      clearInterval(poll);
      clearTimeout(giveUp);
      channel?.close();
    };
  }, [waitingForFacebook, stopWaiting, refreshActivity]);

  async function handleConnect() {
    try {
      setConnecting(true);

      if ((await connectFacebook()) === "popup") {
        setWaitingForFacebook(true);
      }
    } catch (error) {
      toast.error("Facebook not connected", error.message || "Facebook connection failed.");
      setConnecting(false);
    }
  }

  async function handleDisconnect() {
    try {
      setDisconnecting(true);
      await disconnectFacebook();
      setFacebook({ checking: false, connected: false, pageName: "" });
      toast.success("Facebook disconnected", "Connect again any time to keep posting.");
    } catch (error) {
      toast.error("Could not disconnect", error.message || "Please try again.");
    } finally {
      setDisconnecting(false);
    }
  }

  const workspace = {
    facebookConnected: facebook.connected,
    checkingFacebook: facebook.checking,
    pageName: facebook.pageName,
    activity,
    refreshActivity,
    publishedCount,
    onPublished: () => {
      setPublishedCount((count) => count + 1);
      refreshActivity();
    },
  };

  return (
    <div className="dx-page">
      <div className="dx-grid-bg" />
      <div className="dx-cursor" />
      <Confetti burst={publishedCount} />
      <span className="dx-bg-orb dx-bg-orb-1" />
      <span className="dx-bg-orb dx-bg-orb-2" />

      <Navbar />

      <main className="dx-main max-w-7xl mx-auto px-5 py-6">
        <nav className="dx-tabs" aria-label="Sections">
          {SECTIONS.map((section) => (
            <NavLink
              key={section.to}
              to={section.to}
              className={({ isActive }) => `dx-tab ${isActive ? "on" : ""}`}
            >
              <span aria-hidden="true">{section.icon}</span> {section.label}
              {section.to === "/scheduled" && activity.upcoming.length > 0 && (
                <span className="dx-tab-count">{activity.upcoming.length}</span>
              )}
            </NavLink>
          ))}
        </nav>

        <div className="dx-fbbar">
          {facebook.checking ? (
            <p className="text-sm dx-faint">Checking Facebook...</p>
          ) : facebook.connected ? (
            <>
              <div className="dx-badge-ok px-4 py-2">
                <p className="text-xs opacity-80">Facebook Connected</p>
                <p className="text-sm font-semibold">{facebook.pageName || "Facebook Page"}</p>
              </div>

              <PageSwitcher
                onChanged={(name) => setFacebook((value) => ({ ...value, pageName: name }))}
              />

              <button
                onClick={handleDisconnect}
                disabled={disconnecting}
                className="dx-btn-ghost dx-btn-sm dx-fbbar-end"
              >
                {disconnecting ? "Disconnecting..." : "Disconnect"}
              </button>
            </>
          ) : (
            <>
              <p className="text-sm dx-muted">
                Connect your Facebook Page to publish and schedule posts.
              </p>
              {waitingForFacebook && (
                <button type="button" onClick={stopWaiting} className="dx-btn-ghost dx-btn-sm dx-fbbar-end">
                  Cancel
                </button>
              )}
              <button
                onClick={handleConnect}
                disabled={connecting}
                className={`dx-btn ${waitingForFacebook ? "" : "dx-fbbar-end"}`}
              >
                {waitingForFacebook
                  ? "Finish in the Facebook window..."
                  : connecting
                    ? "Connecting..."
                    : "Connect Facebook Page"}
              </button>
            </>
          )}
        </div>

        <Outlet context={workspace} />
      </main>
    </div>
  );
}
