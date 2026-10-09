// Pure form validation for the login and register pages (no network, no Supabase).

export const MIN_PASSWORD_LENGTH = 8;
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function validateAuthForm({ mode, email, password, confirmPassword }) {
  const errors = {};
  if (!EMAIL_PATTERN.test((email || "").trim())) {
    errors.email = "Enter a valid email address.";
  }
  if (!password) {
    errors.password = "Enter your password.";
  } else if (mode === "register" && password.length < MIN_PASSWORD_LENGTH) {
    errors.password = `Use at least ${MIN_PASSWORD_LENGTH} characters.`;
  }
  if (mode === "register" && password && confirmPassword !== password) {
    errors.confirmPassword = "Passwords do not match.";
  }
  return errors;
}

// Turn Supabase auth errors into short messages that never echo secrets.
export function describeAuthError(error) {
  const message = String(error?.message || "").toLowerCase();
  if (message.includes("invalid login credentials")) return "Incorrect email or password.";
  if (message.includes("email not confirmed")) return "Confirm your email first, then sign in. Check your inbox.";
  if (message.includes("already registered") || message.includes("already been registered")) {
    return "An account with this email already exists. Sign in instead.";
  }
  if (message.includes("rate limit") || error?.status === 429) {
    return "Too many attempts. Wait a minute and try again.";
  }
  if (message.includes("failed to fetch") || message.includes("network")) {
    return "Could not reach the authentication service. Check your connection and try again.";
  }
  const detail = String(error?.message || "").trim().slice(0, 160);
  return detail ? `Authentication failed: ${detail}` : "Authentication failed. Please try again.";
}

const ROUTES = ["/", "/login", "/register", "/app"];

export function parseRoute(hash) {
  const path = (hash || "").replace(/^#/, "") || "/";
  return ROUTES.includes(path) ? path : "/";
}

// Decide where a visitor may be: the workspace needs a session; auth pages redirect signed-in users.
export function guardRoute(route, signedIn) {
  if (route === "/app" && !signedIn) return "/login";
  if ((route === "/login" || route === "/register") && signedIn) return "/app";
  return route;
}
