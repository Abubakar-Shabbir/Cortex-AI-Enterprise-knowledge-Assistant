import { Check, FileUp, MessageSquare } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useSession } from '../auth/SessionContext';
import { timeAgo } from '../lib/timeAgo';

// activity_feed events only ever carry these two icon names - see
// RAG.api.dashboard_views (both dashboard_view and admin_overview_view
// build this list the same way context_processors.sidebar_status does).
const ACTIVITY_ICONS = { 'file-up': FileUp, 'message-square': MessageSquare };

// Port of templates/dashboard/_activity_feed.html - shared verbatim by
// both Admin Overview and User Overview.
export default function ActivityFeedCard({ events }) {
  const { permissions, canViewAdminArea } = useSession();

  return (
    <div className="flex h-full flex-col rounded-xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">
      <div className="flex items-center justify-between border-b border-line px-3.5 py-1.5 dark:border-line-dark">
        <h2 className="text-sm font-semibold text-ink dark:text-ink-dark">Activity Feed</h2>
        {canViewAdminArea && permissions.includes('activity.view_all_logs') && (
          <Link to="/admin/system-logs?tab=activity" className="text-xs font-medium text-primary hover:underline dark:text-primary-soft">View all</Link>
        )}
      </div>
      <div className="divide-y divide-line dark:divide-line-dark">
        {events.length === 0 ? (
          <div className="flex items-center gap-2.5 px-3.5 py-3">
            <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-line/50 text-muted dark:bg-white/5 dark:text-muted-dark">
              <Check className="h-3.5 w-3.5" />
            </div>
            <p className="text-sm text-muted dark:text-muted-dark">You&apos;re all caught up.</p>
          </div>
        ) : (
          events.map((event, index) => {
            const Icon = ACTIVITY_ICONS[event.icon] || MessageSquare;
            return (
              <div key={index} className="flex items-start gap-2.5 px-3.5 py-1.5">
                <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
                  <Icon className="h-3.5 w-3.5" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm text-ink dark:text-ink-dark">{event.text}</p>
                </div>
                <span className="shrink-0 text-xs text-muted dark:text-muted-dark">{timeAgo(event.at)} ago</span>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
