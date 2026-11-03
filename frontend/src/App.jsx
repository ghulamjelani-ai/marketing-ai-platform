import { lazy, Suspense } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { useAuth } from "./context/useAuth";
import "./auth.css";
import "./theme.css";

// Each page is loaded when it is first opened, so the first screen downloads less code.
const Login = lazy(() => import("./pages/Login"));
const Signup = lazy(() => import("./pages/Signup"));
const Home = lazy(() => import("./pages/Home"));
const Intro = lazy(() => import("./pages/Intro"));
const Scheduled = lazy(() => import("./pages/Scheduled"));
const AutopilotPage = lazy(() => import("./pages/AutopilotPage"));
const CreatePost = lazy(() => import("./pages/CreatePost"));
const WeekPlan = lazy(() => import("./pages/WeekPlan"));
const History = lazy(() => import("./pages/History"));
const DashboardLayout = lazy(() => import("./components/DashboardLayout"));
const VerifyOtp = lazy(() => import("./pages/VerifyOtp"));
const ForgotPassword = lazy(() => import("./pages/ForgotPassword"));

function PageLoading() {
  return (
    <div className="au-page" role="status" aria-live="polite">
      <div className="au-card rounded-3xl px-8 py-6 text-center">
        <p className="text-sm" style={{ color: "color-mix(in srgb, var(--text) 60%, transparent)" }}>
          Loading...
        </p>
      </div>
    </div>
  );
}
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
  const { user, authLoading, otpPending } = useAuth();

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

  // A Google sign-in waiting for its email code sees only the code screen.
  if (otpPending && !user) {
    return (
      <Suspense fallback={<PageLoading />}>
        <VerifyOtp />
      </Suspense>
    );
  }

  return (
    <Suspense fallback={<PageLoading />}>
    <Routes>
      <Route path="/" element={<Intro />} />

      <Route
        path="/login"
        element={user ? <Navigate to="/home" replace /> : <Login />}
      />

      <Route
        path="/forgot-password"
        element={user ? <Navigate to="/home" replace /> : <ForgotPassword />}
      />

      <Route
        path="/signup"
        element={user ? <Navigate to="/home" replace /> : <Signup />}
      />

      <Route
        element={
          <ProtectedRoute>
            <DashboardLayout />
          </ProtectedRoute>
        }
      >
        <Route path="/home" element={<Home />} />
        <Route path="/autopilot" element={<AutopilotPage />} />
        <Route path="/create" element={<CreatePost />} />
        <Route path="/plan" element={<WeekPlan />} />
        <Route path="/scheduled" element={<Scheduled />} />
        <Route path="/history" element={<History />} />
      </Route>

      <Route path="*" element={<Navigate to={user ? "/home" : "/"} replace />} />
    </Routes>
    </Suspense>
  );
}