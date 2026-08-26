import { useEffect, useRef, useState } from 'react';
import { Bell } from 'lucide-react';
import { Link } from 'react-router-dom';
import { notificationIcon } from '../lib/notificationIcons';
import { useMarkNotificationRead, useNotificationList, useNotificationUnreadCount } from '../api/hooks';

// Port of templates/dashboard/_topbar.html's notificationBell() Alpine
// component - polls the unread count every 25s, lazy-fetches the list
// only when first opened, marks read on click.
export default function NotificationBell() {
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);
  const unread = useNotificationUnreadCount();
  const list = useNotificationList(10);
  const markRead = useMarkNotificationRead();

  useEffect(() => {
    const onClickOutside = (e) => {
      if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', onClickOutside);
    return () => document.removeEventListener('mousedown', onClickOutside);
  }, []);

  const toggleOpen = () => {
    const next = !open;
    setOpen(next);
    if (next && !list.dataUpdatedAt) list.refetch();
  };

  const unreadCount = unread.data?.count || 0;
  const items = list.data?.notifications || [];

  const onItemClick = (n) => {
    if (!n.is_read) markRead.mutate(n.id);
  };

  return (
    <div ref={rootRef} className="relative">
      <button onClick={toggleOpen} className="relative rounded-lg p-2 text-muted hover:bg-surface dark:text-muted-dark dark:hover:bg-white/5" aria-label="Notifications">
        <Bell className="h-4 w-4" />
        {unreadCount > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-0.5 text-[9px] font-semibold text-white">
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div className="fade-in-up absolute right-0 z-30 mt-2 w-80 rounded-xl border border-line bg-card p-2 shadow-soft dark:border-line-dark dark:bg-card-dark">
          <div className="flex items-center justify-between px-2 py-1.5">
            <span className="text-xs font-semibold uppercase tracking-wide text-muted dark:text-muted-dark">Notifications</span>
            <Link to="/notifications" onClick={() => setOpen(false)} className="text-xs font-medium text-primary hover:underline dark:text-primary-soft">View all</Link>
          </div>

          {list.isFetching && !list.data && (
            <p className="px-2 py-3 text-sm text-muted dark:text-muted-dark">Loading…</p>
          )}

          {items.map((n) => {
            const Icon = notificationIcon(n.icon);
            return (
              <a
                key={n.id}
                href={n.action_url || '#'}
                onClick={() => onItemClick(n)}
                className={`flex items-start gap-2.5 rounded-lg px-2 py-2 hover:bg-surface dark:hover:bg-white/5 ${!n.is_read ? 'bg-primary/5 dark:bg-primary/10' : ''}`}
              >
                <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary-soft/50 text-primary dark:bg-primary/15 dark:text-primary-soft">
                  <Icon className="h-3.5 w-3.5" />
                </div>
                <div className="min-w-0">
                  <p className="truncate text-sm text-ink dark:text-ink-dark">{n.title}</p>
                  <p className="truncate text-xs text-muted dark:text-muted-dark">{n.message}</p>
                </div>
              </a>
            );
          })}

          {!list.isFetching && list.dataUpdatedAt && items.length === 0 && (
            <p className="px-2 py-3 text-sm text-muted dark:text-muted-dark">You're all caught up.</p>
          )}
        </div>
      )}
    </div>
  );
}
