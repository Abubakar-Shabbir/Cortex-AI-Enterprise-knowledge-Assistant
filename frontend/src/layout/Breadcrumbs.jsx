import { ChevronRight, Home } from 'lucide-react';
import { Link, useLocation } from 'react-router-dom';

// Port of templates/partials/_breadcrumbs.html / context_processors.breadcrumbs's
// BREADCRUMB_MAP, scoped to the routes this migration actually covers.
const BREADCRUMB_MAP = {
  '/': [['Dashboard', null]],
  '/documents': [['Documents', null]],
  '/ask': [['AI Search', null]],
};

export default function Breadcrumbs() {
  const location = useLocation();
  const trail = BREADCRUMB_MAP[location.pathname];
  if (!trail) return null;

  return (
    <nav aria-label="Breadcrumb" className="mb-4 flex flex-wrap items-center gap-1.5 text-xs text-muted dark:text-muted-dark">
      <Link to="/" className="flex items-center hover:text-ink dark:hover:text-ink-dark" aria-label="Dashboard">
        <Home className="h-3.5 w-3.5" />
      </Link>
      {trail.map(([label, to]) => (
        <span key={label} className="flex items-center gap-1.5">
          <ChevronRight className="h-3 w-3 shrink-0 text-line dark:text-line-dark" />
          {to ? (
            <Link to={to} className="hover:text-ink dark:hover:text-ink-dark">{label}</Link>
          ) : (
            <span className="font-medium text-ink dark:text-ink-dark">{label}</span>
          )}
        </span>
      ))}
    </nav>
  );
}
