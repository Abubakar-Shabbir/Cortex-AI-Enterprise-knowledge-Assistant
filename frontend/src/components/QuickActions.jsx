import { ArrowUpRight, BarChart3, Compass, MessageSquare, Settings, Sparkles, Upload, Users } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useSession } from '../auth/SessionContext';

// Port of templates/dashboard/_quick_actions.html - shared verbatim by
// both Admin Overview and User Overview (same partial in Django).
const QUICK_ACTION_COLORS = {
  primary: { hover: 'hover:border-primary/40 hover:bg-primary/5 dark:hover:bg-primary/10', iconBg: 'bg-primary/10', iconColor: 'text-primary' },
  info: { hover: 'hover:border-info/40 hover:bg-info/5 dark:hover:bg-info/10', iconBg: 'bg-info/10', iconColor: 'text-info' },
  success: { hover: 'hover:border-success/40 hover:bg-success/5 dark:hover:bg-success/10', iconBg: 'bg-success/10', iconColor: 'text-success' },
  accent: { hover: 'hover:border-accent/40 hover:bg-accent/5 dark:hover:bg-accent/10', iconBg: 'bg-accent/10', iconColor: 'text-accent' },
};

function QuickAction({ to, icon: Icon, color, title, desc }) {
  const { hover, iconBg, iconColor } = QUICK_ACTION_COLORS[color];

  return (
    <Link
      to={to}
      className={`group relative flex items-start gap-3 overflow-hidden rounded-xl border border-line p-3 shadow-softer transition-all duration-200 hover:-translate-y-0.5 hover:shadow-soft dark:border-line-dark ${hover}`}
    >
      <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-xl transition-transform duration-200 group-hover:scale-105 ${iconBg} ${iconColor}`}>
        <Icon className="h-4 w-4" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold leading-snug text-ink dark:text-ink-dark">{title}</p>
        <p className="mt-0.5 text-xs leading-snug text-muted dark:text-muted-dark">{desc}</p>
      </div>
      <ArrowUpRight className={`h-4 w-4 shrink-0 -translate-x-1 opacity-0 transition-all duration-200 group-hover:translate-x-0 group-hover:opacity-100 ${iconColor}`} />
    </Link>
  );
}

export default function QuickActions() {
  const { permissions, canViewAdminArea } = useSession();
  const has = (code) => permissions.includes(code);

  return (
    <div className="min-w-0 rounded-xl border border-line bg-card p-3 shadow-soft dark:border-line-dark dark:bg-card-dark">
      <div className="mb-2">
        <h2 className="text-sm font-semibold text-ink dark:text-ink-dark">Quick Actions</h2>
        <p className="mt-0.5 text-xs leading-snug text-muted dark:text-muted-dark">Jump straight to what you use most</p>
      </div>

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3 sm:[&>*:last-child:nth-child(odd)]:col-span-2 lg:[&>*:last-child:not(:nth-child(3n))]:col-span-full">
        {has('pages.documents') && (
          <QuickAction to="/documents" icon={Upload} color="primary" title="Upload Document" desc="Add new documents" />
        )}
        {has('pages.ask_ai') && (
          <QuickAction to="/ask" icon={MessageSquare} color="info" title="Ask AI" desc="Question your documents" />
        )}
        {has('pages.knowledge_base') && (
          <QuickAction to="/knowledge" icon={Compass} color="success" title="Knowledge Center" desc="Explore topics" />
        )}
        {has('pages.ai_tasks') && (
          <QuickAction to="/ai-tasks" icon={Sparkles} color="accent" title="AI Tasks" desc="Run a guided operation" />
        )}
        {canViewAdminArea && has('users.view_all') && (
          <QuickAction to="/admin/users" icon={Users} color="primary" title="Manage Users" desc="Roles & access" />
        )}
        {has('pages.analytics') && (
          <QuickAction to="/analytics" icon={BarChart3} color="success" title="View Analytics" desc="Explore insights" />
        )}
        {canViewAdminArea && has('settings.manage_llm') && (
          <QuickAction to="/admin/settings" icon={Settings} color="accent" title="System Settings" desc="Configure system" />
        )}
      </div>
    </div>
  );
}
