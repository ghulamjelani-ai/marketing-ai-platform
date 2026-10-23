import { Routes, Route, Navigate } from "react-router-dom";
import Login from "./pages/Login";
import Signup from "./pages/Signup";
import Home from "./pages/Home";
import Intro from "./pages/Intro";
import Scheduled from "./pages/Scheduled";
import { useAuth } from "./context/AuthContext";
import "./auth.css";
import "./theme.css";

function ProtectedRoute({ children }) {
  const { user, authLoading } = useAuth();

  if (authLoading) {
    return (
      <div className="au-page">
        <div className="au-card rounded-3xl px-8 py-6 text-center">
          <h2 className="font-classic text-3xl font-bold" style={{ color: "var(--text)" }}>
            Loading...
          </h2>
          <p className="text-sm mt-2" style={{ color: "color-mix(in srgb, var(--text) 60%, transparent)" }}>
            Checking your account.
          </p>
        </div>
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  return children;
}

export default function App() {
  const { user, authLoading } = useAuth();

  if (authLoading) {
    return (
      <div className="au-page">
        <div className="au-card rounded-3xl px-8 py-6 text-center">
          <h2 className="font-classic text-3xl font-bold" style={{ color: "var(--text)" }}>
            Marketing AI
          </h2>
          <p className="text-sm mt-2" style={{ color: "color-mix(in srgb, var(--text) 60%, transparent)" }}>
            Preparing your workspace...
          </p>
        </div>
      </div>
    );
  }

  return (
    <Routes>
      <Route
        path="/"
        element={user ? <Navigate to="/home" replace /> : <Intro />}
      />

      <Route
        path="/login"
        element={user ? <Navigate to="/home" replace /> : <Login />}
      />

      <Route
        path="/signup"
        element={user ? <Navigate to="/home" replace /> : <Signup />}
      />

      <Route
        path="/home"
        element={
          <ProtectedRoute>
            <Home />
          </ProtectedRoute>
        }
      />

      <Route
        path="/scheduled"
        element={
          <ProtectedRoute>
            <Scheduled />
          </ProtectedRoute>
        }
      />
    </Routes>
  );
}