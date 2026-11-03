import { Link } from "react-router-dom";

import {
  AutomationPipeline,
  WorkflowFeed,
  StatCard,
} from "../components/AutomationFlow";
import { SECTIONS } from "../components/sections";
import { useAuth } from "../context/useAuth";
import useWorkspace from "../hooks/useWorkspace";

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

// Overview: the numbers at a glance and a shortcut to every feature page.
export default function Home() {
  const { user } = useAuth();
  const { facebookConnected, checkingFacebook, activity } = useWorkspace();

  return (
    <>
      <div className="dx-card dx-hero dx-rise rounded-3xl p-8">
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
          Welcome {user?.name}. Chat with our AI, create your marketing plan,
          generate social content, and publish directly to your connected
          Facebook Page.
        </p>

        <div className="mt-8 flex flex-wrap gap-4">
          <Link to="/create" className="dx-btn">Start Marketing Plan</Link>
          <Link to="/autopilot" className="dx-btn-ghost">Post in one click</Link>
        </div>
      </div>

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

      <h2 className="dx-title text-2xl mb-4">What would you like to do?</h2>

      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5 mb-8">
        {SECTIONS.filter((section) => section.to !== "/home").map((section, i) => (
          <Link
            key={section.to}
            to={section.to}
            className={`dx-card dx-hover dx-tilt dx-rise dx-d${(i % 4) + 1} dx-shortcut rounded-2xl p-5`}
          >
            <div className="dx-feature-icon">{section.icon}</div>
            <h3 className="dx-title text-xl">{section.label}</h3>
            <p className="text-sm dx-muted mt-2">{section.text}</p>
          </Link>
        ))}
      </div>

      <AutomationPipeline />

      <div className="mt-8">
        <WorkflowFeed />
      </div>
    </>
  );
}
