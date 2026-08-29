import { Menu, Moon, Plus, Search, Sun } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { useState } from 'react';
import { useSession } from '../auth/SessionContext';
import { useTheme } from '../hooks/useTheme';
import NotificationBell from './NotificationBell';

// Port of templates/dashboard/_topbar.html. Search submits to the
// Documents page's own ?q= filter, matching the classic topbar's
// behavior exactly.
export default function Topbar({ onOpenSidebar }) {
  const { permissions } = useSession();
  const { isDark, toggle } = useTheme();
  const navigate = useNavigate();
  const [query, setQuery] = useState('');

  const submitSearch = (e) => {
    e.preventDefault();
    navigate(`/documents?q=${encodeURIComponent(query)}`);
  };

  return (
    <header className="sticky top-0 z-20 flex h-16 shrink-0 items-center gap-3 border-b border-line bg-card/90 px-4 backdrop-blur dark:border-line-dark dark:bg-card-dark/90 sm:px-6 lg:px-8">
      <button onClick={onOpenSidebar} className="rounded-lg p-2 text-muted hover:bg-surface dark:text-muted-dark dark:hover:bg-white/5 lg:hidden">
        <Menu className="h-5 w-5" />
      </button>

      <form onSubmit={submitSearch} className="relative hidden max-w-sm flex-1 sm:block">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted dark:text-muted-dark" />
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search documents…"
          className="w-full rounded-lg border border-line bg-surface py-2 pl-9 pr-16 text-sm text-ink placeholder:text-muted focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/15 dark:border-line-dark dark:bg-white/5 dark:text-ink-dark dark:placeholder:text-muted-dark"
        />
      </form>

      <div className="flex-1 sm:hidden"></div>

      <div className="ml-auto flex items-center gap-1.5 sm:gap-2.5">
        <NotificationBell />

        {permissions.includes('pages.documents') && (
          <Link
            to="/documents"
            className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3.5 py-2 text-sm font-semibold text-white shadow-soft transition-colors hover:bg-primary-dark sm:px-4"
          >
            <Plus className="h-4 w-4" /> <span className="hidden sm:inline">Upload</span>
          </Link>
        )}

        <button
          onClick={toggle}
          className="rounded-lg border border-line p-2 text-muted hover:bg-surface dark:border-line-dark dark:text-muted-dark dark:hover:bg-white/5"
          aria-label="Toggle dark mode"
        >
          {isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
        </button>
      </div>
    </header>
  );
}
