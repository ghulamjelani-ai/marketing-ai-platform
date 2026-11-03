import { useCallback, useEffect, useState } from "react";
import { getNotifications, saveNotificationSettings, sendTestEmail } from "../api/activity";
import { toast } from "../utils/toast";

const EVENT_LABEL = {
  published: "Post published",
  scheduled: "Post scheduled",
  live: "Scheduled post went live",
  updated: "Scheduled post edited",
  test: "Test email",
};

const STATUS_LABEL = { sent: "Sent", failed: "Not sent", skipped: "Skipped" };

const showTime = (iso) =>
  new Date(iso).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });

// The owner's email notifications: an on/off switch, a test email, and what happened to each one.
export default function NotificationsPanel() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);

  const load = useCallback(async () => {
    try {
      setData(await getNotifications());
      setError("");
    } catch (err) {
      setError(err.message || "Could not load your notifications.");
    }
  }, []);

  useEffect(() => {
    let off = false;

    getNotifications()
      .then((result) => {
        if (!off) setData(result);
      })
      .catch((err) => {
        if (!off) setError(err.message || "Could not load your notifications.");
      });

    return () => {
      off = true;
    };
  }, []);

  async function toggle(enabled) {
    setSaving(true);

    try {
      await saveNotificationSettings(enabled);
      setData((value) => ({ ...value, email_enabled: enabled }));
      toast.success(
        enabled ? "Email notifications on" : "Email notifications off",
        enabled ? "You will get an email for each post." : "You will not get emails about your posts.",
      );
    } catch (err) {
      toast.error("Could not save", err.message);
    } finally {
      setSaving(false);
    }
  }

  async function test() {
    setTesting(true);

    try {
      const result = await sendTestEmail();
      toast.success("Test email sent", `Look in ${result.sent_to}. If it is not in your inbox, check Spam.`);
    } catch (err) {
      toast.error("Test email failed", err.message);
    } finally {
      setTesting(false);
      load();
    }
  }

  return (
    <section className="dx-card nt-card rounded-3xl p-6 mb-6" aria-labelledby="nt-title">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="dx-eyebrow">Stay informed</p>
          <h2 id="nt-title" className="dx-title text-2xl mt-1">
            Email notifications
          </h2>
          <p className="dx-muted text-sm mt-1">
            We email {data?.address ? <b>{data.address}</b> : "you"} when a post is published, scheduled, goes live or
            is edited.
          </p>
        </div>

        <div className="nt-actions">
          <label className="dx-check">
            <input
              type="checkbox"
              checked={Boolean(data?.email_enabled)}
              disabled={!data || saving}
              onChange={(event) => toggle(event.target.checked)}
            />
            <span>Send me emails</span>
          </label>
          <button type="button" className="dx-btn-ghost dx-btn-sm" onClick={test} disabled={!data || testing}>
            {testing ? "Sending..." : "Send a test email"}
          </button>
        </div>
      </div>

      {data && !data.server_ready && (
        <p className="dx-assist-status bad mt-4">
          This server cannot send email yet, so notifications are not going out. The site administrator needs to
          finish the email settings.
        </p>
      )}

      {error && <p className="dx-assist-status bad mt-4">{error}</p>}

      {data && data.items.length === 0 && !error && (
        <p className="dx-muted text-sm mt-4">
          Nothing yet. Your next published or scheduled post will show up here.
        </p>
      )}

      {data && data.items.length > 0 && (
        <p className="dx-assist-note">
          &ldquo;Sent&rdquo; means our email provider accepted the message. If it is not in your inbox, check Spam or
          Junk. School and work accounts often also have a Quarantine page where filtered mail waits.
        </p>
      )}

      {data && data.items.length > 0 && (
        <ul className="nt-list" aria-label="Recent notifications">
          {data.items.map((item) => (
            <li key={item.id} className="nt-row">
              <div className="min-w-0">
                <p className="nt-event">{EVENT_LABEL[item.event] || item.event}</p>
                {item.preview && <p className="nt-preview">{item.preview}</p>}
                {item.reason && <p className="nt-reason">{item.reason}</p>}
              </div>
              <div className="nt-meta">
                <span className={`dx-chip nt-${item.status}`}>{STATUS_LABEL[item.status] || item.status}</span>
                <span className="nt-time">{showTime(item.created_at)}</span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
