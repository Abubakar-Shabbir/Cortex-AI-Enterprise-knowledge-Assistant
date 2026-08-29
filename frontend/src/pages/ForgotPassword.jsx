import { useState } from 'react';
import { AlertCircle, ArrowLeft, Mail, CheckCircle2 } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import AuthLayout from '../layout/AuthLayout';
import Spinner from '../components/Spinner';
import { usePasswordResetRequest } from '../api/hooks';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

// Port of templates/forgot_password.html.
export default function ForgotPassword() {
  const navigate = useNavigate();
  const request = usePasswordResetRequest();
  const [email, setEmail] = useState('');
  const [error, setError] = useState('');
  const emailValid = email.length > 0 && EMAIL_RE.test(email);

  const onSubmit = async (e) => {
    e.preventDefault();
    setError('');
    try {
      await request.mutateAsync(email);
      navigate('/password-reset/sent');
    } catch (err) {
      // Enumeration-resistant endpoint: an unknown/rate-limited email
      // still redirects to "check your email" (handled server-side by
      // returning ok:true) - this only throws on real field errors
      // (malformed email), matching form.email.errors in the original.
      setError(err.data?.errors?.email?.[0] || err.message);
    }
  };

  return (
    <AuthLayout title="Reset your password">
      <h1 className="auth-pop-in text-xl font-bold tracking-tight text-ink dark:text-ink-dark">Reset your password</h1>
      <p className="mb-6 mt-1 text-sm text-muted dark:text-muted-dark">Enter your account email and we'll send you a link to reset your password.</p>

      <form onSubmit={onSubmit} className="space-y-4">
        {error && (
          <div role="alert" aria-live="polite" className="auth-error-banner flex items-start gap-2 rounded-lg border border-danger/20 bg-danger/10 px-3.5 py-3 text-sm text-danger dark:text-danger-dark">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            {error}
          </div>
        )}

        <div className="group">
          <label htmlFor="email" className="mb-1.5 block text-xs font-medium text-muted transition-colors duration-150 group-focus-within:text-primary dark:text-muted-dark dark:group-focus-within:text-primary-soft">Email</label>
          <div className="relative">
            <Mail className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted transition-colors duration-150 group-focus-within:text-primary dark:text-muted-dark dark:group-focus-within:text-primary-soft" />
            <input
              id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)}
              placeholder="Enter your account email" required autoFocus autoComplete="email"
              className="w-full rounded-lg border border-line bg-surface py-2.5 pl-10 pr-9 text-sm text-ink placeholder:text-muted transition-all duration-150 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/15 dark:border-line-dark dark:bg-white/5 dark:text-ink-dark dark:placeholder:text-muted-dark"
            />
            {emailValid && <CheckCircle2 className="field-valid-icon pointer-events-none absolute right-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-success dark:text-success-dark" />}
          </div>
        </div>

        <button
          type="submit" disabled={request.isPending}
          className="btn-sheen flex w-full items-center justify-center gap-2 rounded-lg bg-primary py-2.5 text-sm font-semibold text-white shadow-softer transition-all duration-150 hover:bg-primary-dark hover:shadow-glow active:scale-[0.98] disabled:opacity-70 disabled:active:scale-100"
        >
          {request.isPending && <Spinner size={20} />}
          <span>{request.isPending ? 'Sending…' : 'Send reset link'}</span>
        </button>

        <p className="text-center text-sm text-muted dark:text-muted-dark">
          <Link to="/login" className="inline-flex items-center gap-1 font-semibold text-primary transition-colors hover:underline dark:text-primary-soft">
            <ArrowLeft className="h-3.5 w-3.5" /> Back to log in
          </Link>
        </p>
      </form>
    </AuthLayout>
  );
}
