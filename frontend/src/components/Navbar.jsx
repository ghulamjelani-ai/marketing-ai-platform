import { useAuth } from "../context/useAuth";
import { Link, useNavigate } from "react-router-dom";
import "../dashboard.css";
import "../automation.css";
import ThemeToggle from "./ThemeToggle";
import BrandMark from "./BrandMark";

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
        <Link to="/home" className="flex items-center gap-3" aria-label="Marketing AI overview">
          <BrandMark size={40} />
          <div>
            <h2 className="dx-brand">Marketing AI</h2>
            <p className="dx-tagline">Smart Plans. Premium Posts. Social Growth.</p>
          </div>
        </Link>

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

          <ThemeToggle />

          <button onClick={handleLogout} className="dx-btn-ghost dx-btn-sm">
            Logout
          </button>
        </div>
      </div>
    </header>
  );
}
