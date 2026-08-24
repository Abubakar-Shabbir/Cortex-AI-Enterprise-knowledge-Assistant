import { useState } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { AlertCircle, Eye, EyeOff, Loader2, Lock, UserRound } from 'lucide-react';
import { useSession } from '../auth/SessionContext';
import Logo from '../components/Logo';

// Port of templates/login.html (+ auth_base.html's centered card
// shell, inlined here since this migration doesn't port every auth
// page). Signup/forgot-password/OTP verification stay on the classic
// Django pages (plain <a href> below, full navigation) - only Login
// itself was in scope for this increment.
export default function Login() {
  const { login, authenticated } = useSession();
  const navigate = useNavigate();
  const location = useLocation();

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [rememberMe, setRememberMe] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  if (authenticated) {
    const redirectTo = location.state?.from || '/';
    return <Navigate to={redirectTo} replace />;
  }

  const onSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError('');

    const result = await login(username, password, rememberMe);

    if (result.pendingVerification) {
      window.location.href = result.redirect || '/verify-otp/';
      return;
    }
    if (result.error) {
      setError(result.error);
      setSubmitting(false);
      return;
    }

    navigate(location.state?.from || '/', { replace: true });
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface px-4 dark:bg-surface-dark">
      <div className="w-full max-w-sm rounded-2xl border border-line bg-card p-7 shadow-soft dark:border-line-dark dark:bg-card-dark">
        <div className="mb-6 flex items-center gap-2.5 text-primary dark:text-primary-soft">
          <Logo size="h-9 w-9" />
          <span className="text-base font-semibold text-ink dark:text-ink-dark">Cortex</span>
        </div>

        <h1 className="text-xl font-bold tracking-tight text-ink dark:text-ink-dark">Log in to your account</h1>
        <p className="mb-6 mt-1 text-sm text-muted dark:text-muted-dark">Enter your details below to continue.</p>

        <form onSubmit={onSubmit} className="space-y-4">
          {error && (
            <div role="alert" className="flex items-start gap-2 rounded-lg border border-danger/20 bg-danger/10 px-3.5 py-3 text-sm text-danger dark:text-danger-dark">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
              {error}
            </div>
          )}

          <div className="group">
            <label htmlFor="username" className="mb-1.5 block text-xs font-medium text-muted transition-colors duration-150 group-focus-within:text-primary dark:text-muted-dark dark:group-focus-within:text-primary-soft">Username</label>
            <div className="relative">
              <UserRound className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted transition-colors duration-150 group-focus-within:text-primary dark:text-muted-dark dark:group-focus-within:text-primary-soft" />
              <input
                id="username" type="text" value={username} onChange={(e) => setUsername(e.target.value)}
                placeholder="Enter your username" required autoFocus autoComplete="username"
                className="w-full rounded-lg border border-line bg-surface py-2.5 pl-10 pr-3.5 text-sm text-ink placeholder:text-muted transition-all duration-150 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/15 dark:border-line-dark dark:bg-white/5 dark:text-ink-dark dark:placeholder:text-muted-dark"
              />
            </div>
          </div>

          <div className="group">
            <label htmlFor="password" className="mb-1.5 block text-xs font-medium text-muted transition-colors duration-150 group-focus-within:text-primary dark:text-muted-dark dark:group-focus-within:text-primary-soft">Password</label>
            <div className="relative">
              <Lock className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted transition-colors duration-150 group-focus-within:text-primary dark:text-muted-dark dark:group-focus-within:text-primary-soft" />
              <input
                type={showPassword ? 'text' : 'password'} id="password" value={password} onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter your password" required autoComplete="current-password"
                className="w-full rounded-lg border border-line bg-surface py-2.5 pl-10 pr-10 text-sm text-ink placeholder:text-muted transition-all duration-150 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/15 dark:border-line-dark dark:bg-white/5 dark:text-ink-dark dark:placeholder:text-muted-dark"
              />
              <button
                type="button" onClick={() => setShowPassword((v) => !v)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted transition-colors hover:text-ink dark:text-muted-dark dark:hover:text-ink-dark"
                aria-label={showPassword ? 'Hide password' : 'Show password'}
              >
                {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </div>

          <div className="flex items-center justify-between">
            <label className="flex items-center gap-2 text-sm text-ink dark:text-ink-dark">
              <input type="checkbox" checked={rememberMe} onChange={(e) => setRememberMe(e.target.checked)} className="rounded border-line text-primary focus:ring-primary/30 dark:border-line-dark" />
              Remember me
            </label>
            <a href="/password-reset/" className="text-sm font-medium text-primary transition-colors hover:underline dark:text-primary-soft">Forgot password?</a>
          </div>

          <button
            type="submit" disabled={submitting}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-primary py-2.5 text-sm font-semibold text-white shadow-softer transition-all duration-150 hover:bg-primary-dark active:scale-[0.98] disabled:opacity-70 disabled:active:scale-100"
          >
            {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
            <span>{submitting ? 'Logging in…' : 'Log in'}</span>
          </button>

          <p className="text-center text-sm text-muted dark:text-muted-dark">
            Don't have an account? <a href="/signup/" className="font-semibold text-primary transition-colors hover:underline dark:text-primary-soft">Sign up</a>
          </p>
        </form>
      </div>
    </div>
  );
}
