import { Inbox } from 'lucide-react';
import { Link } from 'react-router-dom';

// Port of templates/partials/_empty_state.html. `actionTo` uses React
// Router (internal SPA nav); pass `actionHref` instead for a link to a
// page this migration hasn't ported yet.
export default function EmptyState({ icon: Icon = Inbox, title, message, actionTo, actionHref, actionLabel }) {
  return (
    <div className="flex flex-col items-center justify-center px-5 py-14 text-center">
      <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-primary-soft/40 text-primary dark:bg-primary/10 dark:text-primary-soft">
        <Icon className="h-5 w-5" />
      </div>
      <p className="text-sm font-medium text-ink dark:text-ink-dark">{title}</p>
      {message && <p className="mt-1 max-w-xs text-xs text-muted dark:text-muted-dark">{message}</p>}
      {actionTo && <Link to={actionTo} className="mt-3 text-sm font-medium text-primary hover:underline dark:text-primary-soft">{actionLabel}</Link>}
      {actionHref && <a href={actionHref} className="mt-3 text-sm font-medium text-primary hover:underline dark:text-primary-soft">{actionLabel}</a>}
    </div>
  );
}
