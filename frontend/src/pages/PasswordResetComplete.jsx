import { CheckCircle } from 'lucide-react';
import { Link } from 'react-router-dom';
import AuthLayout from '../layout/AuthLayout';

// Port of templates/password_reset_complete.html.
export default function PasswordResetComplete() {
  return (
    <AuthLayout title="Password updated">
      <div className="auth-success-icon auth-pop-in mb-2 flex h-11 w-11 items-center justify-center rounded-xl bg-success/10 text-success dark:text-success-dark">
        <CheckCircle className="h-5 w-5" />
      </div>

      <h1 className="text-xl font-bold tracking-tight text-ink dark:text-ink-dark">Password updated</h1>
      <p className="mt-1 text-sm text-muted dark:text-muted-dark">Your password has been changed. You can now log in with your new password.</p>

      <Link to="/login" className="mt-6 flex items-center justify-center gap-2 rounded-lg bg-primary py-2.5 text-center text-sm font-semibold text-white shadow-softer transition-all duration-150 hover:bg-primary-dark hover:shadow-glow active:scale-[0.98]">
        Log in
      </Link>
    </AuthLayout>
  );
}
