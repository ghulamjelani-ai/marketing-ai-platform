import { useAuth } from "../context/AuthContext";
import { Link, useNavigate } from "react-router-dom";
import "../dashboard.css";
import "../automation.css";
import ThemeToggle from "./ThemeToggle";

export default function Navbar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    navigate("/login");
  };

  return (
    <header className="dx-nav">
      <div className="max-w-7xl mx-auto px-5 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <svg
            className="dx-gear"
            viewBox="0 0 24 24"
            fill="none"
            strokeWidth="1.6"
            style={{ stroke: "var(--accent)" }}
          >
            <circle cx="12" cy="12" r="3" />
            <path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1" />
          </svg>
          <div>
            <h2 className="dx-brand">Marketing AI</h2>
            <p className="dx-tagline">Smart Plans. Premium Posts. Social Growth.</p>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <div className="hidden md:block">
            <span className="dx-live">
              <span className="dx-online" /> Automation running
            </span>
          </div>

          {user?.photo && (
            <img src={user.photo} alt={user.name} className="dx-avatar" />
          )}

          <div className="hidden sm:block text-right">
            <p className="dx-user-name">{user?.name}</p>
            <p className="dx-user-email">{user?.email}</p>
          </div>

          <Link to="/scheduled" className="dx-btn-ghost dx-btn-sm">
            🗓️ Scheduled posts
          </Link>

          <ThemeToggle />

          <button onClick={handleLogout} className="dx-btn-ghost dx-btn-sm">
            Logout
          </button>
        </div>
      </div>
    </header>
  );
}
