import { useParams, Link } from 'react-router-dom';
import { ArrowLeft, Shield } from 'lucide-react';
import PageSkeleton from '../components/PageSkeleton';
import { timeAgo, timeUntil } from '../lib/timeAgo';
import { useAdminUserProfile } from '../api/hooks';

const HEALTH_CLASSES = {
  success: 'bg-success/10 text-success dark:text-success-dark',
  warning: 'bg-warning/10 text-warning dark:text-warning-dark',
  danger: 'bg-danger/10 text-danger dark:text-danger-dark',
  neutral: 'bg-muted/10 text-muted dark:text-muted-dark',
};

// Read-only port of templates/admin/user_profile.html - the enterprise
// profile summary (completion, activity, devices, role) for one user,
// viewed by an Admin. Editing another user's profile fields from here
// isn't ported in this pass - the self-service Profile page already
// covers the edit-your-own-profile pattern.
export default function AdminUserProfile() {
  const { userId } = useParams();
  const { data, isLoading } = useAdminUserProfile(userId);

  if (isLoading || !data) return <PageSkeleton variant="detail" />;

  const { user, profile, completion, activity_summary: activitySummary, account_health: accountHealth, is_online: isOnline, last_active: lastActive, login_history: loginHistory, active_sessions: activeSessions } = data;
  const initials = `${(user.first_name || user.username || '?')[0] || ''}${(user.last_name || '')[0] || ''}`.toUpperCase();

  return (
    <>
      <Link to="/admin/users" className="mb-4 inline-flex items-center gap-1.5 text-xs font-medium text-muted hover:text-ink dark:text-muted-dark dark:hover:text-ink-dark">
        <ArrowLeft className="h-3.5 w-3.5" /> Back to Users
      </Link>

      <div className="mb-4 overflow-hidden rounded-2xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">
        <div className="h-14 bg-gradient-to-r from-primary-light to-primary-dark"></div>
        <div className="px-5 pb-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
            <div className="relative -mt-9 shrink-0">
              {profile.avatar_url ? (
                <img src={profile.avatar_url} alt="" className="h-[72px] w-[72px] rounded-full object-cover ring-4 ring-card dark:ring-card-dark" />
              ) : (
                <div className="flex h-[72px] w-[72px] items-center justify-center rounded-full bg-gradient-to-br from-primary-light to-primary-dark text-xl font-semibold text-white ring-4 ring-card dark:ring-card-dark">{initials}</div>
              )}
              <span className={`absolute bottom-0.5 right-0.5 h-3 w-3 rounded-full ring-2 ring-card dark:ring-card-dark ${isOnline ? 'bg-success' : 'bg-muted'}`}></span>
            </div>
            <div className="min-w-0 flex-1 pb-0.5">
              <div className="flex flex-wrap items-center gap-1.5">
                <h2 className="truncate text-base font-bold text-ink dark:text-ink-dark">{`${user.first_name} ${user.last_name}`.trim() || user.username}</h2>
                <span className={`inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${HEALTH_CLASSES[accountHealth.category] || HEALTH_CLASSES.neutral}`}>{accountHealth.label}</span>
                <span className="inline-flex items-center gap-1 rounded-full bg-accent/10 px-1.5 py-0.5 text-[10px] font-medium text-accent">
                  <Shield className="h-2.5 w-2.5" /> {user.role_name || 'Unassigned'}
                </span>
                {!user.is_active && <span className="inline-flex items-center gap-1 rounded-full bg-danger/10 px-1.5 py-0.5 text-[10px] font-semibold text-danger dark:text-danger-dark">Suspended</span>}
              </div>
              <p className={`mt-0.5 text-xs ${profile.headline ? 'font-medium text-primary dark:text-primary-soft' : 'italic text-muted dark:text-muted-dark'}`}>{profile.headline || 'No professional headline set yet'}</p>
              <p className="mt-1 flex flex-wrap items-center gap-x-2.5 gap-y-0.5 text-[11px] text-muted dark:text-muted-dark">
                <span className="flex items-center gap-1">
                  <span className={`h-1.5 w-1.5 rounded-full ${isOnline ? 'bg-success' : 'bg-muted'}`}></span>
                  {isOnline ? 'Online now' : `Last active ${timeAgo(lastActive)} ago`}
                </span>
                {profile.job_title && <span>{profile.job_title}</span>}
                {profile.department && <span>· {profile.department}</span>}
              </p>
              <p className="mt-1 text-[11px] text-muted dark:text-muted-dark">{user.email} · @{user.username}</p>
            </div>
            <div className="shrink-0">
              <span className="text-lg font-bold tracking-tight text-ink dark:text-ink-dark">{completion.percent}%</span>
              <span className="text-[11px] text-muted dark:text-muted-dark"> complete</span>
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="rounded-xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">
          <div className="border-b border-line px-5 py-3 dark:border-line-dark"><h2 className="text-sm font-semibold text-ink dark:text-ink-dark">Activity Summary</h2></div>
          <div className="space-y-2 px-5 py-4 text-sm">
            <div className="flex items-center justify-between"><span className="text-muted dark:text-muted-dark">Documents Owned</span><span className="font-medium text-ink dark:text-ink-dark">{activitySummary.documents_owned}</span></div>
            <div className="flex items-center justify-between"><span className="text-muted dark:text-muted-dark">Questions Asked</span><span className="font-medium text-ink dark:text-ink-dark">{activitySummary.queries_asked}</span></div>
            <div className="flex items-center justify-between"><span className="text-muted dark:text-muted-dark">AI Task Runs</span><span className="font-medium text-ink dark:text-ink-dark">{activitySummary.ai_task_runs}</span></div>
            <div className="flex items-center justify-between"><span className="text-muted dark:text-muted-dark">Activity Events</span><span className="font-medium text-ink dark:text-ink-dark">{activitySummary.activity_events}</span></div>
            <div className="flex items-center justify-between border-t border-line pt-2 dark:border-line-dark"><span className="text-muted dark:text-muted-dark">Member For</span><span className="font-medium text-ink dark:text-ink-dark">{activitySummary.account_age_days} days</span></div>
          </div>
        </div>

        <div className="rounded-xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">
          <div className="border-b border-line px-5 py-3 dark:border-line-dark"><h2 className="text-sm font-semibold text-ink dark:text-ink-dark">Login History</h2></div>
          <div className="space-y-2 px-5 py-4 text-xs">
            {loginHistory.length > 0 ? loginHistory.slice(0, 5).map((entry, idx) => (
              <div key={idx}>
                <p className="font-medium text-ink dark:text-ink-dark">{new Date(entry.at).toLocaleString('en-US', { month: 'short', day: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false })} <span className="font-normal text-muted dark:text-muted-dark">({timeAgo(entry.at)} ago)</span></p>
                <p className="text-muted dark:text-muted-dark">{entry.device_type} · {entry.browser} · {entry.os}{entry.ip_address ? ` · ${entry.ip_address}` : ''}{entry.location ? ` · ${entry.location}` : ''}</p>
              </div>
            )) : <p className="text-muted dark:text-muted-dark">No login history recorded yet.</p>}
          </div>
        </div>
      </div>

      <div className="mt-4 rounded-xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">
        <div className="border-b border-line px-5 py-3 dark:border-line-dark"><h2 className="text-sm font-semibold text-ink dark:text-ink-dark">Active Sessions ({activeSessions.length})</h2></div>
        <div className="space-y-1.5 px-5 py-4 text-xs">
          {activeSessions.length > 0 ? activeSessions.map((session) => (
            <div key={session.session_key} className="flex items-center gap-2">
              <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${session.is_current ? 'bg-success' : 'bg-muted'}`}></span>
              <span className="text-ink dark:text-ink-dark">Session</span>
              <span className="text-muted dark:text-muted-dark">· expires in {timeUntil(session.expire_date)}</span>
            </div>
          )) : <p className="text-muted dark:text-muted-dark">No active sessions.</p>}
        </div>
      </div>
    </>
  );
}
