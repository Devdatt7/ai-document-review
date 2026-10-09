import { useState } from "react";
import { useAuth } from "./AuthContext.jsx";
import { describeAuthError, validateAuthForm } from "./authValidation.js";

export function SiteHeader({ children }) {
  return (
    <header className="app-header">
      <a className="brand" href="#/" aria-label="AI Document Review home">
        <span className="brand-mark" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none">
            <path d="M6 3.75h8l4 4v12.5H6z" />
            <path d="M14 3.75v4h4M9 12h6M9 15.5h3" />
            <path d="m14.5 16 1.5 1.5 3-3" />
          </svg>
        </span>
        <span>AI Document Review</span>
      </a>
      <nav className="site-nav" aria-label="Account">{children}</nav>
    </header>
  );
}

export function LandingPage() {
  const { user, loading } = useAuth();
  const signedIn = Boolean(user);
  return (
    <main className="app">
      <SiteHeader>
        {!loading && (signedIn ? (
          <a className="nav-link primary" href="#/app">Open workspace</a>
        ) : (
          <>
            <a className="nav-link" href="#/login">Log in</a>
            <a className="nav-link primary" href="#/register">Create account</a>
          </>
        ))}
      </SiteHeader>

      <section className="landing-hero">
        <div className="hero-copy">
          <span className="eyebrow">Evidence-led document review</span>
          <h1>Know which claims in your AI-written document to <em>trust</em>.</h1>
          <p>
            Compare a document against your own source material. See which claims the source supports,
            which it contradicts, and which findings deserve a human review first.
          </p>
          <div className="landing-cta">
            <a className="primary-button" href={signedIn ? "#/app" : "#/register"}>
              {signedIn ? "Open workspace" : "Get started free"}
            </a>
            {!signedIn && <a className="secondary-button" href="#/login">I already have an account</a>}
          </div>
          <ul className="hero-points" aria-label="Highlights">
            <li>Every finding quotes its source</li>
            <li>Sorted by priority score</li>
            <li>You make the final call</li>
          </ul>
        </div>

        <figure className="hero-preview" aria-label="Example finding, illustrative only">
          <figcaption className="preview-tag">Example preview</figcaption>
          <div className="preview-claim">
            <span className="preview-badge">CONTRADICTED</span>
            <p>“The maximum reimbursement is ₹50,000.”</p>
          </div>
          <div className="preview-evidence">
            <span>Source evidence</span>
            <p>“Reimbursement is capped at ₹25,000 per claim and is paid within 10 working days.”</p>
          </div>
          <div className="preview-next">
            <span>Suggested next step</span>
            <p>Correct the figure or confirm the policy before sharing.</p>
          </div>
        </figure>
      </section>

      <section className="landing-features" aria-label="How it works">
        <h2 className="section-title">How it works</h2>
        <div className="feature-grid">
          <article>
            <span className="feature-number">01</span>
            <h3>Add your documents</h3>
            <p>Paste or upload the AI-written document and the trusted source it should match.</p>
          </article>
          <article>
            <span className="feature-number">02</span>
            <h3>Check claims against evidence</h3>
            <p>Each important claim is compared with quoted passages from your source.</p>
          </article>
          <article>
            <span className="feature-number">03</span>
            <h3>Review by priority</h3>
            <p>Findings are sorted by priority score so the most consequential issues come first.</p>
          </article>
        </div>
      </section>

      <section className="landing-final">
        <h2>Try it on a sample first</h2>
        <p>The workspace includes offline sample documents, so you can explore a full review before using your own text.</p>
        <a className="primary-button" href={signedIn ? "#/app" : "#/register"}>
          {signedIn ? "Open workspace" : "Create your account"}
        </a>
      </section>

      <footer className="footer">System assessments are evidence-based signals for human review, not a substitute for judgment.</footer>
    </main>
  );
}

function ConfigNotice() {
  return (
    <div className="error" role="alert">
      Sign-in is not configured. Set <code>VITE_SUPABASE_URL</code> and <code>VITE_SUPABASE_ANON_KEY</code> in
      <code> frontend/.env.local</code> and restart the dev server.
    </div>
  );
}

function Field({ id, label, type = "text", value, onChange, error, autoComplete, hint }) {
  const [shown, setShown] = useState(false);
  const isPassword = type === "password";
  return (
    <div className="auth-field">
      <label htmlFor={id}>{label}</label>
      <div className="input-wrap">
        <input id={id} className={isPassword ? "has-toggle" : undefined} type={isPassword && shown ? "text" : type} value={value} autoComplete={autoComplete}
               aria-invalid={Boolean(error)} aria-describedby={error ? `${id}-error` : hint ? `${id}-hint` : undefined}
               onChange={(e) => onChange(e.target.value)} />
        {isPassword && (
          <button type="button" className="toggle-visibility" aria-pressed={shown}
                  aria-label={shown ? `Hide ${label.toLowerCase()}` : `Show ${label.toLowerCase()}`}
                  onClick={() => setShown(!shown)}>
            {shown ? "Hide" : "Show"}
          </button>
        )}
      </div>
      {hint && !error && <span id={`${id}-hint`} className="field-hint">{hint}</span>}
      {error && <span id={`${id}-error`} className="field-error" role="alert">{error}</span>}
    </div>
  );
}

function AuthShell({ title, subtitle, children, footer }) {
  return (
    <main className="app">
      <SiteHeader>
        <a className="nav-link" href="#/">← Home</a>
      </SiteHeader>
      <div className="auth-layout">
        <aside className="auth-aside" aria-label="About the product">
          <span className="eyebrow">Evidence-led document review</span>
          <h2>Trust the claims you can back with a source.</h2>
          <ul>
            <li>Every finding quotes the passage it relies on</li>
            <li>Findings are sorted by priority score</li>
            <li>Your review decisions stay in your hands</li>
          </ul>
        </aside>
        <section className="auth-card" aria-labelledby="auth-title">
          <h1 id="auth-title">{title}</h1>
          <p className="auth-subtitle">{subtitle}</p>
          {children}
          <p className="auth-footer">{footer}</p>
        </section>
      </div>
    </main>
  );
}

export function LoginPage() {
  const { signIn, configured } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState({});
  const [formError, setFormError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event) {
    event.preventDefault();
    const found = validateAuthForm({ mode: "login", email, password });
    setErrors(found);
    setFormError("");
    if (Object.keys(found).length) return;
    setBusy(true);
    const { error } = await signIn(email.trim(), password);
    setBusy(false);
    if (error) setFormError(describeAuthError(error));
    else window.location.hash = "#/app";
  }

  return (
    <AuthShell title="Log in" subtitle="Welcome back. Sign in to open your review workspace."
               footer={<>New here? <a href="#/register">Create an account</a></>}>
      {!configured && <ConfigNotice />}
      <form onSubmit={submit} noValidate>
        <Field id="login-email" label="Email" type="email" value={email} onChange={setEmail}
               error={errors.email} autoComplete="email" />
        <Field id="login-password" label="Password" type="password" value={password} onChange={setPassword}
               error={errors.password} autoComplete="current-password" />
        {formError && <div className="error" role="alert">{formError}</div>}
        <button className="primary-button auth-submit" type="submit" disabled={busy || !configured}>
          {busy ? <><span className="spinner" aria-hidden="true" /> Signing in…</> : "Log in"}
        </button>
      </form>
    </AuthShell>
  );
}

export function RegisterPage() {
  const { signUp, configured } = useAuth();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [errors, setErrors] = useState({});
  const [formError, setFormError] = useState("");
  const [confirmationSent, setConfirmationSent] = useState(false);
  const [busy, setBusy] = useState(false);

  async function submit(event) {
    event.preventDefault();
    const found = validateAuthForm({ mode: "register", email, password, confirmPassword });
    setErrors(found);
    setFormError("");
    if (Object.keys(found).length) return;
    setBusy(true);
    const { data, error } = await signUp(email.trim(), password, fullName.trim());
    setBusy(false);
    if (error) {
      setFormError(describeAuthError(error));
    } else if (data.session) {
      window.location.hash = "#/app";
    } else {
      setConfirmationSent(true);
    }
  }

  if (confirmationSent) {
    return (
      <AuthShell title="Check your email" subtitle={`We sent a confirmation link to ${email.trim()}.`}
                 footer={<>Confirmed already? <a href="#/login">Log in</a></>}>
        <p className="body-copy">Open the link in that email to activate your account, then sign in.</p>
      </AuthShell>
    );
  }

  return (
    <AuthShell title="Create your account" subtitle="Register to use the document review workspace."
               footer={<>Already registered? <a href="#/login">Log in</a></>}>
      {!configured && <ConfigNotice />}
      <form onSubmit={submit} noValidate>
        <Field id="register-name" label="Full name (optional)" value={fullName} onChange={setFullName}
               autoComplete="name" />
        <Field id="register-email" label="Email" type="email" value={email} onChange={setEmail}
               error={errors.email} autoComplete="email" />
        <Field id="register-password" label="Password" type="password" value={password} onChange={setPassword}
               error={errors.password} autoComplete="new-password" hint="At least 8 characters." />
        <Field id="register-confirm" label="Confirm password" type="password" value={confirmPassword}
               onChange={setConfirmPassword} error={errors.confirmPassword} autoComplete="new-password" />
        {formError && <div className="error" role="alert">{formError}</div>}
        <button className="primary-button auth-submit" type="submit" disabled={busy || !configured}>
          {busy ? <><span className="spinner" aria-hidden="true" /> Creating account…</> : "Create account"}
        </button>
      </form>
    </AuthShell>
  );
}
