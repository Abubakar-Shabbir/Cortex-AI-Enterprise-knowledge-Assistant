import { FileText, Folder, Library, Share2, Star } from 'lucide-react';
import { Link, useLocation } from 'react-router-dom';

const TABS = [
  { key: 'mine', to: '/documents', icon: FileText, label: 'My Documents' },
  { key: 'shared', to: '/documents/shared-with-me', icon: Share2, label: 'Shared With Me' },
  { key: 'org', to: '/documents/org-library', icon: Library, label: 'Organization Library' },
  { key: 'collections', to: '/documents/collections', icon: Folder, label: 'Collections' },
  { key: 'favorites', to: '/documents/favorites', icon: Star, label: 'Favorites' },
];

// Port of templates/partials/_documents_tabs.html.
export default function DocumentsTabs() {
  const { pathname } = useLocation();

  return (
    <div className="mb-6 flex gap-1 overflow-x-auto border-b border-line dark:border-line-dark">
      {TABS.map(({ key, to, icon: Icon, label }) => {
        const active = key === 'collections' ? pathname.startsWith('/documents/collections') : pathname === to;
        return (
          <Link
            key={key}
            to={to}
            className={`shrink-0 border-b-2 px-3.5 py-2.5 text-sm font-medium transition-colors ${
              active ? 'border-primary text-primary dark:border-primary-soft dark:text-primary-soft' : 'border-transparent text-muted hover:text-ink dark:text-muted-dark dark:hover:text-ink-dark'
            }`}
          >
            <span className="flex items-center gap-1.5"><Icon className="h-3.5 w-3.5" /> {label}</span>
          </Link>
        );
      })}
    </div>
  );
}
