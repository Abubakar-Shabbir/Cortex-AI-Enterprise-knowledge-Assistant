import { useEffect, useRef, useState } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { AlertCircle, MailCheck, RefreshCw, ShieldCheck } from 'lucide-react';
import AuthLayout from '../layout/AuthLayout';
import Spinner from '../components/Spinner';
import { useSession } from '../auth/SessionContext';
import { useResendOtp, useVerifyOtp, useVerifyOtpStatus } from '../api/hooks';

const RESEND_COOLDOWN_DEFAULT = 60;

// Port of templates/verify_otp.html — six boxed digits drive the UX,
// mirroring the Alpine component's focus/paste/backspace handling and
// resend-cooldown progress bar.
export default function VerifyOtp() {
  const navigate = useNavigate();
  const { refresh } = useSession();
  const status = useVerifyOtpStatus();
  const verify = useVerifyOtp();
  const resend = useResendOtp();

  const [digits, setDigits] = useState(['', '', '', '', '', '']);
  const [error, setError] = useState('');
  const [cooldown, setCooldown] = useState(RESEND_COOLDOWN_DEFAULT);
  const [cooldownTotal, setCooldownTotal] = useState(RESEND_COOLDOWN_DEFAULT);
  const inputsRef = useRef([]);
  const startedRef = useRef(false);

  useEffect(() => {
    if (!startedRef.current) {
      startedRef.current = true;
      inputsRef.current[0]?.focus();
    }
  }, []);

  useEffect(() => {
    if (cooldown <= 0) return undefined;
    const t = setInterval(() => setCooldown((c) => c - 1), 1000);
    return () => clearInterval(t);
  }, [cooldown]);

  if (status.isLoading) {
    return (
      <AuthLayout title="Verify your email">
        <div className="flex flex-col items-center gap-3 py-10">
          <Spinner size={40} className="text-primary dark:text-primary-soft" label="Loading" />
        </div>
      </AuthLayout>
    );
  }
  if (status.data && !status.data.pending) return <Navigate to="/signup" replace />;

  const code = digits.join('');
  const isComplete = digits.every((d) => d !== '');

  const focusDigit = (i) => inputsRef.current[i]?.focus();

  const handleInput = (i, value) => {
    const val = value.replace(/[^0-9]/g, '').slice(-1);
    setDigits((prev) => {
      const next = [...prev];
      next[i] = val;
      return next;
    });
    if (val && i < 5) focusDigit(i + 1);
  };

  const handleKeydown = (i, e) => {
    if (e.key === 'Backspace' && !digits[i] && i > 0) focusDigit(i - 1);
  };

  const handlePaste = (e) => {
    e.preventDefault();
    const pasted = (e.clipboardData || window.clipboardData).getData('text').replace(/[^0-9]/g, '').slice(0, 6);
    if (!pasted) return;
    const next = ['', '', '', '', '', ''];
    for (let i = 0; i < 6; i++) next[i] = pasted[i] || '';
    setDigits(next);
    focusDigit(Math.min(pasted.length, 6) - 1);
  };

  const startCooldown = (seconds) => {
    setCooldownTotal(seconds);
    setCooldown(seconds);
  };

  const onSubmit = async (e) => {
    e.preventDefault();
    setError('');
    try {
      await verify.mutateAsync(code);
      await refresh();
      navigate('/', { replace: true });
    } catch (err) {
      setDigits(['', '', '', '', '', '']);
      focusDigit(0);
      setError(err.message);
    }
  };

  const onResend = async () => {
    if (cooldown > 0 || resend.isPending) return;
    setDigits(['', '', '', '', '', '']);
    focusDigit(0);
    try {
      const data = await resend.mutateAsync();
      startCooldown(data.cooldown_seconds || RESEND_COOLDOWN_DEFAULT);
    } catch (err) {
      if (err.data?.cooldown_seconds) startCooldown(err.data.cooldown_seconds);
    }
  };

  return (
    <AuthLayout title="Verify your email">
      <div className="auth-pop-in mb-2 flex h-11 w-11 items-center justify-center rounded-xl bg-primary-soft/40 text-primary dark:bg-primary/10 dark:text-primary-soft">
        <MailCheck className="h-5 w-5" />
      </div>

      <h1 className="text-xl font-bold tracking-tight text-ink dark:text-ink-dark">Verify your email</h1>
      <p className="mb-6 mt-1 text-sm text-muted dark:text-muted-dark">
        We sent a 6-digit code to <span className="font-medium text-ink dark:text-ink-dark">{status.data?.masked_email}</span>. Enter it below to finish setting up your account.
      </p>

      <form onSubmit={onSubmit} className="space-y-5">
        {error && (
          <div role="alert" aria-live="polite" className="auth-error-banner flex items-start gap-2 rounded-lg border border-danger/20 bg-danger/10 px-3.5 py-3 text-sm text-danger dark:text-danger-dark">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            {error}
          </div>
        )}

        <div>
          <label className="mb-2 block text-xs font-medium text-muted dark:text-muted-dark">Verification code</label>
          <div className="flex justify-between gap-2" onPaste={handlePaste}>
            {digits.map((d, i) => (
              <input
                key={i}
                ref={(el) => { inputsRef.current[i] = el; }}
                type="text" inputMode="numeric" pattern="[0-9]*" maxLength={1} autoComplete="one-time-code"
                aria-label={`Digit ${i + 1} of 6`}
                value={d}
                onChange={(e) => handleInput(i, e.target.value)}
                onKeyDown={(e) => handleKeydown(i, e)}
                className={`h-14 w-full min-w-0 rounded-xl border bg-surface text-center text-2xl font-bold text-ink transition-all duration-150 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/15 dark:bg-white/5 dark:text-ink-dark ${d ? 'border-primary text-primary dark:text-primary-soft' : 'border-line dark:border-line-dark'}`}
              />
            ))}
          </div>
          <p className={`mt-2 flex items-center gap-1.5 text-xs transition-opacity duration-300 ${isComplete ? 'text-success dark:text-success-dark opacity-100' : 'opacity-0'}`}>
            <ShieldCheck className="h-3.5 w-3.5" /> Code entered — ready to verify
          </p>
        </div>

        <button
          type="submit" disabled={verify.isPending || !isComplete}
          className="btn-sheen flex w-full items-center justify-center gap-2 rounded-lg bg-primary py-2.5 text-sm font-semibold text-white shadow-softer transition-all duration-150 hover:bg-primary-dark hover:shadow-glow active:scale-[0.98] disabled:opacity-50 disabled:active:scale-100"
        >
          {verify.isPending ? <Spinner size={16} /> : <ShieldCheck className="h-4 w-4" />}
          <span>{verify.isPending ? 'Verifying…' : 'Verify email'}</span>
        </button>

        <div className="text-center text-sm text-muted dark:text-muted-dark">
          <p>Didn't get a code?</p>
          <button
            type="button" onClick={onResend} disabled={cooldown > 0 || resend.isPending}
            className="mt-1.5 inline-flex items-center gap-1.5 font-semibold text-primary transition-colors hover:underline disabled:text-muted disabled:no-underline dark:text-primary-soft dark:disabled:text-muted-dark"
          >
            {resend.isPending ? <Spinner size={14} /> : <RefreshCw className="h-3.5 w-3.5" />}
            {cooldown > 0 ? <span>Resend in {cooldown}s</span> : resend.isPending ? <span>Sending…</span> : <span>Resend code</span>}
          </button>
          {cooldown > 0 && (
            <div className="mx-auto mt-2 h-0.5 w-24 overflow-hidden rounded-full bg-line dark:bg-line-dark">
              <div className="h-full rounded-full bg-primary/50 transition-all duration-1000 ease-linear dark:bg-primary-soft/50" style={{ width: `${(cooldown / cooldownTotal) * 100}%` }}></div>
            </div>
          )}
        </div>
      </form>
    </AuthLayout>
  );
}
