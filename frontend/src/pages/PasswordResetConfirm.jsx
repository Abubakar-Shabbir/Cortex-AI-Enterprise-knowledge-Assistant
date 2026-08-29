import { useState } from 'react';
import { Link, Navigate, useParams } from 'react-router-dom';
import { AlertCircle, Eye, EyeOff, Link2Off, Lock } from 'lucide-react';
import AuthLayout from '../layout/AuthLayout';
import Spinner from '../components/Spinner';
import { usePasswordResetConfirm, usePasswordResetValidate } from '../api/hooks';

// Port of templates/password_reset_confirm.html — validlink is
// resolved via GET /api/auth/password-reset/validate/<uidb64>/<token>/
// on mount instead of arriving pre-rendered from the server.
export default function PasswordResetConfirm() {
  const { uidb64, token } = useParams();
  const validate = usePasswordResetValidate(uidb64, token);
  const confirm = usePasswordResetConfirm(uidb64, token);

  const [password1, setPassword1] = useState('');
  const [password2, setPassword2] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [fieldErrors, setFieldErrors] = useState({});
  const [nonFieldError, setNonFieldError] = useState('');
  const [done, setDone] = useState(false);

  if (validate.isLoading) {
    return (
      <AuthLayout title="Set a new password">
        <div className="flex flex-col items-center gap-3 py-10">
          <Spinner size={40} className="text-primary dark:text-primary-soft" label="Loading" />
        </div>
      </AuthLayout>
    );
  }

  const validLink = validate.isSuccess && validate.data?.valid;

  const onSubmit = async (e) => {
    e.preventDefault();
    setFieldErrors({});
    setNonFieldError('');
    try {
      await confirm.mutateAsync({ new_password1: password1, new_password2: password2 });
      setDone(true);
    } catch (err) {
      if (err.data?.errors) {
        const { __all__: nonField, ...rest } = err.data.errors;
        setFieldErrors(rest);
        if (nonField?.length) setNonFieldError(nonField[0]);
      } else {
        setNonFieldError(err.message);
      }
    }
  };

  if (done) {
    return <Navigate to="/reset/done" replace />;
  }

  return (
    <AuthLayout title="Set a new password">
      {validLink ? (
        <>
          <h1 className="auth-pop-in text-xl font-bold tracking-tight text-ink dark:text-ink-dark">Set a new password</h1>
          <p className="mb-6 mt-1 text-sm text-muted dark:text-muted-dark">Choose a new password for your account.</p>

          <form onSubmit={onSubmit} className="space-y-4">
            {nonFieldError && (
              <div role="alert" aria-live="polite" className="auth-error-banner flex items-start gap-2 rounded-lg border border-danger/20 bg-danger/10 px-3.5 py-3 text-sm text-danger dark:text-danger-dark">
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                {nonFieldError}
              </div>
            )}

            <div className="group">
              <label htmlFor="id_new_password1" className="mb-1.5 block text-xs font-medium text-muted transition-colors duration-150 group-focus-within:text-primary dark:text-muted-dark dark:group-focus-within:text-primary-soft">New password</label>
              <div className="relative">
                <Lock className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted transition-colors duration-150 group-focus-within:text-primary dark:text-muted-dark dark:group-focus-within:text-primary-soft" />
                <input
                  type={showPassword ? 'text' : 'password'} id="id_new_password1" value={password1} onChange={(e) => setPassword1(e.target.value)}
                  placeholder="Create a new password" required autoComplete="new-password"
                  className={`w-full rounded-lg border ${fieldErrors.new_password1 ? 'border-danger' : 'border-line dark:border-line-dark'} bg-surface py-2.5 pl-10 pr-9 text-sm text-ink placeholder:text-muted transition-all duration-150 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/15 dark:bg-white/5 dark:text-ink-dark dark:placeholder:text-muted-dark`}
                />
                <button type="button" onClick={() => setShowPassword((v) => !v)} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted transition-colors hover:text-ink dark:text-muted-dark dark:hover:text-ink-dark" aria-label={showPassword ? 'Hide password' : 'Show password'}>
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
              {fieldErrors.new_password1 && <p className="mt-1 text-xs text-danger dark:text-danger-dark">{fieldErrors.new_password1[0]}</p>}
            </div>

            <div className="group">
              <label htmlFor="id_new_password2" className="mb-1.5 block text-xs font-medium text-muted transition-colors duration-150 group-focus-within:text-primary dark:text-muted-dark dark:group-focus-within:text-primary-soft">Confirm new password</label>
              <div className="relative">
                <Lock className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted transition-colors duration-150 group-focus-within:text-primary dark:text-muted-dark dark:group-focus-within:text-primary-soft" />
                <input
                  type={showConfirm ? 'text' : 'password'} id="id_new_password2" value={password2} onChange={(e) => setPassword2(e.target.value)}
                  placeholder="Re-enter new password" required autoComplete="new-password"
                  className={`w-full rounded-lg border ${fieldErrors.new_password2 ? 'border-danger' : 'border-line dark:border-line-dark'} bg-surface py-2.5 pl-10 pr-9 text-sm text-ink placeholder:text-muted transition-all duration-150 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/15 dark:bg-white/5 dark:text-ink-dark dark:placeholder:text-muted-dark`}
                />
                <button type="button" onClick={() => setShowConfirm((v) => !v)} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted transition-colors hover:text-ink dark:text-muted-dark dark:hover:text-ink-dark" aria-label={showConfirm ? 'Hide password' : 'Show password'}>
                  {showConfirm ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
              {fieldErrors.new_password2 && <p className="mt-1 text-xs text-danger dark:text-danger-dark">{fieldErrors.new_password2[0]}</p>}
            </div>

            <button
              type="submit" disabled={confirm.isPending}
              className="btn-sheen flex w-full items-center justify-center gap-2 rounded-lg bg-primary py-2.5 text-sm font-semibold text-white shadow-softer transition-all duration-150 hover:bg-primary-dark hover:shadow-glow active:scale-[0.98] disabled:opacity-70 disabled:active:scale-100"
            >
              {confirm.isPending && <Spinner size={20} />}
              <span>{confirm.isPending ? 'Saving…' : 'Set new password'}</span>
            </button>
          </form>
        </>
      ) : (
        <>
          <div className="auth-pop-in mb-2 flex h-11 w-11 items-center justify-center rounded-xl bg-danger/10 text-danger dark:text-danger-dark">
            <Link2Off className="h-5 w-5" />
          </div>

          <h1 className="text-xl font-bold tracking-tight text-ink dark:text-ink-dark">This link is invalid or has expired</h1>
          <p className="mt-1 text-sm text-muted dark:text-muted-dark">Reset links only work once and expire after a short time. Request a new one below.</p>

          <Link to="/password-reset" className="mt-6 flex items-center justify-center gap-2 rounded-lg bg-primary py-2.5 text-center text-sm font-semibold text-white shadow-softer transition-all duration-150 hover:bg-primary-dark hover:shadow-glow active:scale-[0.98]">
            Request a new link
          </Link>
        </>
      )}
    </AuthLayout>
  );
}
