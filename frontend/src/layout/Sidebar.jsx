import {
  BarChart3, FileDown, FileText, HeartPulse, Home, LogOut, MessageSquare, Search, Settings, Share2,
  Shield, Sparkles, Terminal, Users, UserRound, ChevronDown, Sun, Moon,
} from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useSession } from '../auth/SessionContext';
import { useTheme } from '../hooks/useTheme';
import Logo from '../components/Logo';
import NavItem from './NavItem';

// Port of templates/dashboard/_sidebar.html - every item is a React
// Router route (zero full-page reloads), permission-gated exactly
// like the Django template.
export default function Sidebar({ open, onClose }) {
  const { permissions, canViewAdminArea, user, role, logout } = useSession();
  const { isDark, toggle } = useTheme();
  const [menuOpen, setMenuOpen] = useState(false);

  const has = (code) => permissions.includes(code);

  const initials = `${(user?.first_name || user?.username || '?')[0] || ''}${(user?.last_name || '')[0] || ''}`.toUpperCase();

  return (
    <>
      {open && (
        <div className="fixed inset-0 z-30 bg-black/40 lg:hidden" onClick={onClose} />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-40 flex h-dvh w-64 flex-col bg-gradient-to-b from-sidebar to-sidebar-deep text-ink-dark shadow-[1px_0_0_rgba(255,255,255,0.04)] transition-transform duration-200 lg:translate-x-0 ${
          open ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <Link to="/" className="relative flex h-16 shrink-0 items-center gap-2.5 overflow-hidden border-b border-white/10 px-5">
          <div className="pointer-events-none absolute -left-6 -top-10 h-28 w-28 rounded-full bg-primary/25 blur-2xl"></div>
          <div className="relative text-primary-soft"><Logo size="h-8 w-8" /></div>
          <div className="relative leading-tight">
            <div className="text-sm font-semibold text-white">Cortex</div>
            <div className="text-[11px] text-muted-dark">Admin Panel</div>
          </div>
        </Link>

        <nav className="sidebar-scroll flex-1 space-y-1 overflow-y-auto px-3 py-4 text-sm">
          <NavItem to="/" icon={Home} label="Overview" />

          {(has('pages.ask_ai') || has('pages.documents') || has('pages.knowledge_base') || has('pages.ai_tasks')) && (
            <>
              <div className="mb-1.5 mt-4 px-3 text-[11px] font-semibold uppercase tracking-wide text-muted-dark">Workspace</div>
              {has('pages.documents') && <NavItem to="/documents" icon={FileText} label="Documents" />}
              {has('pages.knowledge_base') && <NavItem to="/knowledge" activeMatch="/knowledge" icon={Share2} label="Knowledge Base" />}
              {has('pages.ask_ai') && <NavItem to="/ask" icon={MessageSquare} label="Ask AI" />}
              {has('pages.ai_tasks') && <NavItem to="/ai-tasks" activeMatch="/ai-tasks" icon={Sparkles} label="AI Tasks" />}
            </>
          )}

          {(has('pages.analytics') || has('pages.reports') || has('queries.view_all_logs')) && (
            <>
              <div className="mb-1.5 mt-4 px-3 text-[11px] font-semibold uppercase tracking-wide text-muted-dark">Insights</div>
              {has('pages.analytics') && <NavItem to="/analytics" icon={BarChart3} label="Analytics" />}
              {has('pages.reports') && <NavItem to="/reports" icon={FileDown} label="Reports" />}
              {has('queries.view_all_logs') && <NavItem to="/admin/queries" icon={Search} label="Queries" />}
            </>
          )}

          {canViewAdminArea && (
            <>
              <div className="mb-1.5 mt-4 px-3 text-[11px] font-semibold uppercase tracking-wide text-muted-dark">Administration</div>
              {has('users.view_all') && <NavItem to="/admin/users" icon={Users} label="Users" />}
              {has('roles.manage') && <NavItem to="/admin/roles" icon={Shield} label="Roles" />}
              {(has('settings.manage_llm') || has('settings.manage_chunking') || has('settings.manage_retrieval') || has('settings.manage_embedding') || has('settings.manage_database')) && (
                <NavItem to="/admin/settings" icon={Settings} label="Settings" />
              )}
              {has('system.view_health') && <NavItem to="/admin/system-health" icon={HeartPulse} label="System Health" />}
              {(has('system.view_ai_logs') || has('activity.view_all_logs')) && <NavItem to="/admin/system-logs" icon={Terminal} label="System Logs" />}
            </>
          )}

          <div className="my-3 border-t border-white/10"></div>
          <NavItem to="/profile" icon={UserRound} label="Profile" />
        </nav>

        <div className="border-t border-white/10 p-3">
          <div className="relative">
            <button onClick={() => setMenuOpen((v) => !v)} className="flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-left transition-colors duration-150 hover:bg-primary/15">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-primary-light to-primary-dark text-xs font-semibold text-white ring-2 ring-white/10">
                {initials || 'U'}
              </div>
              <div className="min-w-0 flex-1 leading-tight">
                <div className="truncate text-sm font-medium text-white">{user?.first_name || user?.username}</div>
                <div className="truncate text-xs text-muted-dark">{role || 'Member'}</div>
              </div>
              <ChevronDown className={`h-4 w-4 shrink-0 text-muted-dark transition-transform duration-150 ${menuOpen ? 'rotate-180' : ''}`} />
            </button>

            {menuOpen && (
              <div className="absolute bottom-full left-0 z-30 mb-2 w-56 rounded-xl border border-white/10 bg-sidebar-soft p-1.5 shadow-soft">
                <Link to="/profile" onClick={() => setMenuOpen(false)} className="flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-ink-dark transition-colors duration-150 hover:bg-primary/15">
                  <UserRound className="h-4 w-4 text-muted-dark" /> Profile
                </Link>
                <div className="my-1 border-t border-white/10"></div>
                <button
                  onClick={() => logout()}
                  className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-sm text-danger-dark transition-colors duration-150 hover:bg-danger/10"
                >
                  <LogOut className="h-4 w-4" /> Logout
                </button>
              </div>
            )}
          </div>

          <button
            onClick={toggle}
            className="mt-2 flex w-full items-center justify-between gap-2.5 rounded-lg px-3 py-2.5 text-sm font-medium text-muted-dark transition-colors duration-150 hover:bg-primary/15 hover:text-white"
          >
            <span className="flex items-center gap-2.5">
              {isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
              {isDark ? 'Dark Mode' : 'Light Mode'}
            </span>
            <span className="relative h-5 w-9 rounded-full bg-white/10">
              <span className={`absolute top-0.5 left-0.5 h-4 w-4 rounded-full bg-white transition-transform ${isDark ? 'translate-x-4' : ''}`}></span>
            </span>
          </button>
        </div>
      </aside>
    </>
  );
}
