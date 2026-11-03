import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import "./index.css";
import App from "./App";
import { AuthProvider } from "./context/AuthContext";
import Toaster from "./components/Toaster";
import ErrorBoundary from "./components/ErrorBoundary";
import { announceFacebookResult, clearConnecting, isConnecting, readFacebookResult } from "./utils/facebookConnect";
import "./auth.css";
import "./clay.css"; // last: the clay + glass look sits on top of every other style file

const facebookReturn = readFacebookResult(window.location.search);

if (facebookReturn && isConnecting()) {
  // This is the small Facebook window coming back: tell the main window and close.
  announceFacebookResult(facebookReturn);
  clearConnecting();
  document.body.textContent = "Done. You can close this window and go back to Marketing AI.";
  window.close();
} else {
  ReactDOM.createRoot(document.getElementById("root")).render(
    <React.StrictMode>
      <ErrorBoundary>
        <BrowserRouter>
          <AuthProvider>
            <App />
            <Toaster />
          </AuthProvider>
        </BrowserRouter>
      </ErrorBoundary>
    </React.StrictMode>
  );
}
