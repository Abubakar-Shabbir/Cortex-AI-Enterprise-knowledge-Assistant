import { ArrowLeft, MailCheck } from 'lucide-react';
import { Link } from 'react-router-dom';
import AuthLayout from '../layout/AuthLayout';

// Port of templates/password_reset_sent.html.
export default function PasswordResetSent() {
  return (
    <AuthLayout title="Check your email">
      <div className="auth-pop-in mb-2 flex h-11 w-11 items-center justify-center rounded-xl bg-primary-soft/40 text-primary dark:bg-primary/10 dark:text-primary-soft">
        <MailCheck className="h-5 w-5" />
      </div>

      <h1 className="text-xl font-bold tracking-tight text-ink dark:text-ink-dark">Check your email</h1>
      <p className="mt-1 text-sm text-muted dark:text-muted-dark">
        If an account exists for the email you entered, we've sent a link to reset your password. The link expires shortly, so use it soon.
      </p>

      <Link to="/login" className="mt-6 flex items-center justify-center gap-1.5 text-sm font-semibold text-primary transition-colors hover:underline dark:text-primary-soft">
        <ArrowLeft className="h-3.5 w-3.5" /> Back to log in
      </Link>
    </AuthLayout>
  );
}
