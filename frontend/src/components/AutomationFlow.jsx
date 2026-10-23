import { useEffect, useRef, useState } from "react";
import "../dashboard.css";
import "../automation.css";

const NODES = [
  { icon: "💬", title: "Business input", sub: "You describe it once" },
  { icon: "🧠", title: "AI strategy", sub: "Plan generated" },
  { icon: "✍️", title: "Content", sub: "Posts written" },
  { icon: "🗓️", title: "Schedule", sub: "Best times set" },
  { icon: "🚀", title: "Auto publish", sub: "Posted to Facebook" },
];

const FEED = [
  ["run", "Analyzing business profile…"],
  ["ok", "Profile analyzed"],
  ["run", "Building marketing strategy…"],
  ["ok", "Strategy ready"],
  ["run", "Writing post captions…"],
  ["ok", "Captions generated"],
  ["run", "Scheduling for best engagement time…"],
  ["ok", "Schedule set"],
  ["run", "Publishing to Facebook Page…"],
  ["ok", "Post published"],
];

export function AutomationPipeline() {
  return (
    <div className="dx-card dx-flow dx-rise dx-d1 rounded-3xl p-7">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="dx-eyebrow">Automated workflow</p>
          <h2 className="dx-title text-2xl mt-2">From idea to published post</h2>
        </div>
        <span className="dx-live">
          <span className="dx-online" /> Automation engine ready
        </span>
      </div>

      <div className="dx-nodes">
        {NODES.map((n, i) => (
          <div key={n.title} className="contents">
            <div className="dx-node" style={{ "--d": `${i * 2}s` }}>
              <div className="dx-ring" style={{ "--d": `${i * 2}s` }} />
              <div className="dx-node-ic" style={{ "--d": `${i * 2}s` }}>
                {n.icon}
              </div>
              <b>{n.title}</b>
              <small>{n.sub}</small>
            </div>

            {i < NODES.length - 1 && (
              <div className="dx-link">
                <span
                  className="dx-packet"
                  style={{ "--pd": `${i * 0.5}s` }}
                />
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

export function WorkflowFeed() {
  const [rows, setRows] = useState([]);

  useEffect(() => {
    let i = 0;
    const tick = () => {
      const id = i;
      i += 1;

      const [kind, text] = FEED[id % FEED.length];
      const time = new Date().toLocaleTimeString([], { hour12: false });

      setRows((prev) => {
        if (prev.some((row) => row.id === id)) return prev;
        return [...prev, { id, kind, text, time }].slice(-8);
      });
    };
    const first = setTimeout(tick, 0);
    const timer = setInterval(tick, 1200);
    return () => {
      clearTimeout(first);
      clearInterval(timer);
    };
  }, []);

  return (
    <div className="dx-card dx-rise dx-d2 rounded-3xl p-6 mb-8">
      <div className="mb-3 flex items-center justify-between text-xs dx-faint">
        <b className="text-sm dx-strong">How your automation runs</b>
        <span>workflow preview</span>
      </div>

      <div className="dx-feed">
        {rows.map((r) => (
          <div key={r.id} className="dx-feed-row">
            <span className="dx-feed-t">{r.time}</span>
            <span className={r.kind === "ok" ? "dx-feed-ok" : "dx-feed-run"}>
              {r.kind === "ok" ? "✔" : "›"} {r.text}
            </span>
          </div>
        ))}
      </div>

      <div className="dx-bar">
        <i />
      </div>
    </div>
  );
}

function CountUp({ value }) {
  const [shown, setShown] = useState(value);
  const shownRef = useRef(value);

  useEffect(() => {
    if (typeof value !== "number") return undefined;

    const from = shownRef.current;
    const start = performance.now();
    let frame = 0;

    const step = (now) => {
      const t = Math.min(1, (now - start) / 700);
      const next = Math.round(from + (value - from) * (1 - Math.pow(1 - t, 3)));

      shownRef.current = next;
      setShown(next);

      if (t < 1) frame = requestAnimationFrame(step);
    };

    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [value]);

  return typeof value === "number" ? shown : value;
}

export function StatCard({ value, label, color = "var(--accent)", path, delay = "" }) {
  return (
    <div className={`dx-card dx-hover dx-tilt dx-rise ${delay} rounded-2xl p-5 overflow-hidden`}>
      <div className="dx-stat-n">
        <CountUp value={value} />
      </div>
      <div className="dx-stat-l">{label}</div>
      <svg className="dx-spark" viewBox="0 0 110 44">
        <path d={path} fill="none" style={{ stroke: color }} strokeWidth="2" />
      </svg>
    </div>
  );
}
