import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import { AuthProvider, useAuth } from "./AuthContext.jsx";
import { guardRoute, parseRoute } from "./authValidation.js";
import { LandingPage, LoginPage, RegisterPage } from "./pages.jsx";
import "./styles.css";
import "./theme-bw.css";

function Router() {
  const { user, loading, signOut } = useAuth();
  const [hash, setHash] = React.useState(window.location.hash);

  React.useEffect(() => {
    const onChange = () => setHash(window.location.hash);
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);

  const requested = parseRoute(hash);
  const route = loading ? requested : guardRoute(requested, Boolean(user));

  React.useEffect(() => {
    if (route !== requested) window.location.hash = `#${route}`;
  }, [route, requested]);

  if (loading && requested === "/app") return <p className="auth-loading" role="status">Loading…</p>;
  if (route === "/login") return <LoginPage />;
  if (route === "/register") return <RegisterPage />;
  if (route === "/app") return <App user={user} onSignOut={signOut} />;
  return <LandingPage />;
}

createRoot(document.getElementById("root")).render(
  <AuthProvider>
    <Router />
  </AuthProvider>,
);
