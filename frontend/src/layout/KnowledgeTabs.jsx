import { Compass, GitBranch, Lightbulb, Quote, Share2 } from 'lucide-react';
import { Link, useLocation } from 'react-router-dom';

const TABS = [
  { key: 'browse', to: '/knowledge', icon: Compass, label: 'Explore Topics' },
  { key: 'relationships', to: '/knowledge/relationships', icon: GitBranch, label: 'Relationships' },
  { key: 'graph', to: '/knowledge/graph', icon: Share2, label: 'Graph' },
  { key: 'insights', to: '/knowledge/insights', icon: Lightbulb, label: 'Insights' },
  { key: 'citations', to: '/knowledge/citations', icon: Quote, label: 'Citations' },
];

// Port of templates/partials/_kb_tabs.html.
export default function KnowledgeTabs() {
  const { pathname } = useLocation();

  return (
    <div className="mb-6 flex flex-wrap gap-1 overflow-x-auto rounded-xl border border-line bg-surface p-1 shadow-softer dark:border-line-dark dark:bg-white/5">
      {TABS.map(({ key, to, icon: Icon, label }) => {
        const active = pathname === to;
        return (
          <Link
            key={key}
            to={to}
            className={`inline-flex shrink-0 items-center gap-1.5 rounded-lg px-3.5 py-2 text-sm font-medium transition-all duration-150 ${
              active ? 'bg-primary text-white shadow-soft' : 'text-muted hover:bg-card hover:text-ink dark:text-muted-dark dark:hover:bg-white/10 dark:hover:text-ink-dark'
            }`}
          >
            <Icon className="h-3.5 w-3.5" /> {label}
          </Link>
        );
      })}
    </div>
  );
}
