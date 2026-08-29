import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Bell, CheckCheck } from 'lucide-react';
import PageHeader from '../components/PageHeader';
import PageSkeleton from '../components/PageSkeleton';
import Spinner from '../components/Spinner';
import { notificationIcon } from '../lib/notificationIcons';
import { timeAgo } from '../lib/timeAgo';
import { useMarkAllNotificationsRead, useMarkNotificationRead, useNotifications } from '../api/hooks';

// Port of templates/notifications/center.html.
export default function Notifications() {
  const [searchParams, setSearchParams] = useSearchParams();
  const activeCategory = searchParams.get('category') || '';
  const page = searchParams.get('page') || '1';

  const { data, isLoading } = useNotifications({ category: activeCategory, page });
  const markRead = useMarkNotificationRead();
  const markAllRead = useMarkAllNotificationsRead();
  const [marking, setMarking] = useState(false);

  const setCategory = (cat) => setSearchParams(cat ? { category: cat } : {});
  const setPage = (p) => setSearchParams({ ...(activeCategory ? { category: activeCategory } : {}), page: String(p) });

  const onMarkAll = async () => {
    setMarking(true);
    try {
      await markAllRead.mutateAsync();
    } finally {
      setMarking(false);
    }
  };

  if (isLoading || !data) return <PageSkeleton variant="list" />;

  return (
    <>
      <PageHeader title="Notifications" subtitle="Everything that's happened across your account." />

      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-1.5">
          <button
            onClick={() => setCategory('')}
            className={`rounded-full border px-3 py-1.5 text-xs font-medium ${!activeCategory ? 'border-primary bg-primary/10 text-primary dark:text-primary-soft' : 'border-line text-ink hover:border-primary/30 dark:border-line-dark dark:text-ink-dark'}`}
          >
            All
          </button>
          {data.categories.map((cat) => (
            <button
              key={cat}
              onClick={() => setCategory(cat)}
              className={`rounded-full border px-3 py-1.5 text-xs font-medium capitalize ${activeCategory === cat ? 'border-primary bg-primary/10 text-primary dark:text-primary-soft' : 'border-line text-ink hover:border-primary/30 dark:border-line-dark dark:text-ink-dark'}`}
            >
              {cat}
            </button>
          ))}
        </div>

        <button
          onClick={onMarkAll} disabled={marking}
          className="inline-flex items-center gap-1.5 rounded-lg border border-line px-3 py-2 text-xs font-medium text-ink transition-colors hover:border-primary/30 hover:text-primary disabled:opacity-60 dark:border-line-dark dark:text-ink-dark"
        >
          {marking ? <Spinner size={14} /> : <CheckCheck className="h-3.5 w-3.5" />} Mark all as read
        </button>
      </div>

      <div className="overflow-hidden rounded-xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">
        {data.results.length > 0 ? (
          <>
            <div className="divide-y divide-line dark:divide-line-dark">
              {data.results.map((notification) => {
                const Icon = notificationIcon(notification.icon);
                return (
                  <a
                    key={notification.id}
                    href={notification.action_url || '#'}
                    onClick={() => { if (!notification.is_read) markRead.mutate(notification.id); }}
                    className={`flex items-start gap-3 px-5 py-4 transition-colors hover:bg-surface dark:hover:bg-white/5 ${!notification.is_read ? 'bg-primary/[0.03] dark:bg-primary/[0.06]' : ''}`}
                  >
                    <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary-soft/50 text-primary dark:bg-primary/15 dark:text-primary-soft">
                      <Icon className="h-4 w-4" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-ink dark:text-ink-dark">{notification.title}</p>
                      <p className="mt-0.5 text-sm text-muted dark:text-muted-dark">{notification.message}</p>
                      <p className="mt-1 text-xs text-muted dark:text-muted-dark">{timeAgo(notification.created_at)} ago</p>
                    </div>
                    {!notification.is_read && <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-primary" title="Unread"></span>}
                  </a>
                );
              })}
            </div>

            {data.num_pages > 1 && (
              <div className="flex items-center justify-between border-t border-line px-5 py-3 dark:border-line-dark">
                <p className="text-xs text-muted dark:text-muted-dark">Page {data.page} of {data.num_pages} · {data.count} total</p>
                <div className="flex gap-2">
                  {data.has_previous && (
                    <button onClick={() => setPage(data.page - 1)} className="rounded-lg border border-line px-3 py-1.5 text-xs font-medium text-ink hover:bg-surface dark:border-line-dark dark:text-ink-dark dark:hover:bg-white/5">Previous</button>
                  )}
                  {data.has_next && (
                    <button onClick={() => setPage(data.page + 1)} className="rounded-lg border border-line px-3 py-1.5 text-xs font-medium text-ink hover:bg-surface dark:border-line-dark dark:text-ink-dark dark:hover:bg-white/5">Next</button>
                  )}
                </div>
              </div>
            )}
          </>
        ) : (
          <div className="flex flex-col items-center justify-center px-6 py-16 text-center">
            <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-primary-soft/40 text-primary dark:bg-primary/10 dark:text-primary-soft">
              <Bell className="h-5 w-5" />
            </div>
            <p className="text-sm font-semibold text-ink dark:text-ink-dark">You're all caught up</p>
            <p className="mt-1 max-w-xs text-sm text-muted dark:text-muted-dark">Notifications about shared documents, AI Tasks, and account activity will show up here.</p>
          </div>
        )}
      </div>
    </>
  );
}
