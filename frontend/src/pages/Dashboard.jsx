import {
  ArrowUpRight, BarChart3, Calendar, Check, Compass, FileText, HardDrive, MessageSquare, Sparkles, Timer, Upload,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import { useSession } from '../auth/SessionContext';
import { useDashboard } from '../api/hooks';
import MiniStatCard from '../components/MiniStatCard';
import { timeAgo } from '../lib/timeAgo';

// Port of templates/user_dashboard.html + its _welcome/_quick_actions/
// _activity_feed partials. Admin Overview (templates/dashboard.html,
// the charts/KPI-trend variant shown to Admin-role users) is not part
// of this increment - every authenticated account sees this simpler
// User Overview in the SPA for now (see the final migration report).
export default function Dashboard() {
  const { user, permissions, canViewAdminArea } = useSession();
  const { data, isLoading } = useDashboard();
  const has = (code) => permissions.includes(code);

  const hasAnyModule = has('pages.documents') || has('pages.ask_ai') || has('pages.knowledge_base') || has('pages.ai_tasks') || has('pages.analytics') || canViewAdminArea;

  const hour = new Date().getHours();
  const greeting = hour < 12 ? 'morning' : hour < 18 ? 'afternoon' : 'evening';
  const today = new Date().toLocaleDateString(undefined, { month: 'long', day: 'numeric', year: 'numeric' });

  return (
    <div>
      <div className="relative mb-2.5 overflow-hidden rounded-2xl border border-line bg-gradient-to-br from-primary/[0.07] via-card to-card p-5 shadow-soft dark:border-line-dark dark:from-primary/15 dark:via-card-dark dark:to-card-dark">
        <div aria-hidden="true" className="pointer-events-none absolute -right-8 -top-16 h-44 w-44 rounded-full bg-primary/10 blur-3xl dark:bg-primary/20"></div>
        <div aria-hidden="true" className="pointer-events-none absolute -bottom-20 right-32 h-36 w-36 rounded-full bg-accent/10 blur-3xl dark:bg-accent/20"></div>
        <div className="relative flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-xl font-bold leading-snug tracking-tight text-ink dark:text-ink-dark">
              Good {greeting}, {user?.first_name || user?.username} <span aria-hidden="true">👋</span>
            </h1>
            <p className="mt-1 text-sm text-muted dark:text-muted-dark">Here's what's happening in your workspace today.</p>
          </div>
          <div className="inline-flex items-center gap-1.5 self-start rounded-lg border border-line bg-card/90 px-2.5 py-1.5 text-xs font-medium text-ink shadow-softer backdrop-blur-sm dark:border-line-dark dark:bg-card-dark/80 dark:text-ink-dark">
            <Calendar className="h-3.5 w-3.5 text-muted dark:text-muted-dark" /> {today}
          </div>
        </div>
      </div>

      {!hasAnyModule ? (
        <div className="rounded-xl border border-dashed border-line bg-card p-10 text-center dark:border-line-dark dark:bg-card-dark">
          <p className="text-sm font-medium text-ink dark:text-ink-dark">No modules assigned yet</p>
          <p className="mx-auto mt-1 max-w-sm text-xs text-muted dark:text-muted-dark">Your role doesn't grant access to any workspace features yet. An Admin can grant access from Roles.</p>
        </div>
      ) : isLoading ? (
        <div className="py-16 text-center text-sm text-muted dark:text-muted-dark">Loading…</div>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-[repeat(auto-fit,minmax(180px,1fr))] fade-in-up">
            {has('pages.documents') && <MiniStatCard icon={FileText} iconBg="bg-primary/10" iconColor="text-primary" label="My Documents" value={data.stats.total_documents} numeric />}
            {has('pages.ask_ai') && <MiniStatCard icon={MessageSquare} iconBg="bg-info/10" iconColor="text-info" label="Questions Asked" value={data.stats.questions_asked} numeric />}
            {has('pages.ask_ai') && <MiniStatCard icon={Timer} iconBg="bg-warning/10" iconColor="text-warning" label="Avg Response Time" value={data.stats.avg_response_time} />}
            {has('pages.documents') && <MiniStatCard icon={HardDrive} iconBg="bg-success/10" iconColor="text-success" label="Storage Used" value={data.stats.storage_used} />}
            {has('pages.ai_tasks') && <MiniStatCard icon={Sparkles} iconBg="bg-accent/10" iconColor="text-accent" label="AI Task Runs" value={data.stats.ai_task_runs} numeric />}
            {has('pages.knowledge_base') && <MiniStatCard icon={Compass} iconBg="bg-success/10" iconColor="text-success" label="Topics" value={data.knowledge_overview.total_entities} numeric />}
          </div>

          <div className="mt-2">
            <QuickActions has={has} canViewAdminArea={canViewAdminArea} />
          </div>

          <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
            {has('pages.documents') && (
              <ListCard
                title="Recent Documents" viewAllTo="/documents"
                items={data.recent_documents}
                empty="No documents uploaded yet."
                emptyCta={{ to: '/documents', label: 'Upload your first document' }}
                icon={FileText}
                renderItem={(doc) => (
                  <>
                    <p className="truncate text-sm font-medium leading-snug text-ink dark:text-ink-dark">{doc.title}</p>
                    <p className="mt-0.5 text-xs leading-snug text-muted dark:text-muted-dark">{doc.file_type?.toUpperCase()} · {doc.chunk_count} chunks · {timeAgo(doc.uploaded_at)} ago</p>
                  </>
                )}
              />
            )}

            {has('pages.ask_ai') && (
              <ListCard
                title="Recent Questions" viewAllTo="/ask"
                items={data.recent_questions}
                empty="No questions asked yet."
                emptyCta={{ to: '/ask', label: 'Ask your first question' }}
                icon={MessageSquare}
                renderItem={(log) => (
                  <>
                    <p className="truncate text-sm font-medium leading-snug text-ink dark:text-ink-dark">{log.question}</p>
                    <p className="mt-0.5 text-xs leading-snug text-muted dark:text-muted-dark">{log.confidence}% confidence · {timeAgo(log.created_at)} ago</p>
                  </>
                )}
              />
            )}

            <div className="flex h-full flex-col rounded-xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">
              <div className="flex items-center justify-between border-b border-line px-3.5 py-1.5 dark:border-line-dark">
                <h2 className="text-sm font-semibold text-ink dark:text-ink-dark">Activity Feed</h2>
              </div>
              <div className="divide-y divide-line dark:divide-line-dark">
                {data.activity_feed.length ? data.activity_feed.map((event, i) => (
                  <div key={i} className="flex items-start gap-2.5 px-3.5 py-1.5">
                    <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
                      <BarChart3 className="h-3.5 w-3.5" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm text-ink dark:text-ink-dark">{event.text}</p>
                    </div>
                    <span className="shrink-0 text-xs text-muted dark:text-muted-dark">{timeAgo(event.at)} ago</span>
                  </div>
                )) : (
                  <div className="flex items-center gap-2.5 px-3.5 py-3">
                    <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-line/50 text-muted dark:bg-white/5 dark:text-muted-dark">
                      <Check className="h-3.5 w-3.5" />
                    </div>
                    <p className="text-sm text-muted dark:text-muted-dark">You're all caught up.</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function ListCard({ title, viewAllTo, items, empty, emptyCta, icon: Icon, renderItem }) {
  return (
    <div className="flex h-full flex-col rounded-xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">
      <div className="flex items-center justify-between border-b border-line px-3.5 py-1.5 dark:border-line-dark">
        <h2 className="text-sm font-semibold text-ink dark:text-ink-dark">{title}</h2>
        <Link to={viewAllTo} className="text-xs font-medium text-primary hover:underline dark:text-primary-soft">View all</Link>
      </div>
      <div className="divide-y divide-line dark:divide-line-dark">
        {items.length ? items.map((item) => (
          <div key={item.id} className="flex items-center gap-2.5 px-3.5 py-1.5">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Icon className="h-4 w-4" />
            </div>
            <div className="min-w-0 flex-1">{renderItem(item)}</div>
          </div>
        )) : (
          <div className="flex items-center gap-2.5 px-3.5 py-3">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-line/50 text-muted dark:bg-white/5 dark:text-muted-dark">
              <Icon className="h-4 w-4" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-sm text-muted dark:text-muted-dark">{empty}</p>
              <Link to={emptyCta.to} className="text-xs font-medium text-primary hover:underline dark:text-primary-soft">{emptyCta.label}</Link>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function QuickActions({ has, canViewAdminArea }) {
  const actions = [
    has('pages.documents') && { to: '/documents', icon: Upload, color: 'primary', title: 'Upload Document', subtitle: 'Add new documents' },
    has('pages.ask_ai') && { to: '/ask', icon: MessageSquare, color: 'info', title: 'Ask AI', subtitle: 'Question your documents' },
  ].filter(Boolean);

  if (!actions.length) return null;

  return (
    <div className="min-w-0 rounded-xl border border-line bg-card p-3 shadow-soft dark:border-line-dark dark:bg-card-dark">
      <div className="mb-2">
        <h2 className="text-sm font-semibold text-ink dark:text-ink-dark">Quick Actions</h2>
        <p className="mt-0.5 text-xs leading-snug text-muted dark:text-muted-dark">Jump straight to what you use most</p>
      </div>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {actions.map((a) => (
          <Link
            key={a.to}
            to={a.to}
            className={`group relative flex items-start gap-3 overflow-hidden rounded-xl border border-line p-3 shadow-softer transition-all duration-200 hover:-translate-y-0.5 hover:border-${a.color}/40 hover:bg-${a.color}/5 hover:shadow-soft dark:border-line-dark dark:hover:bg-${a.color}/10`}
          >
            <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-${a.color}/10 text-${a.color} transition-transform duration-200 group-hover:scale-105`}>
              <a.icon className="h-4 w-4" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold leading-snug text-ink dark:text-ink-dark">{a.title}</p>
              <p className="mt-0.5 text-xs leading-snug text-muted dark:text-muted-dark">{a.subtitle}</p>
            </div>
            <ArrowUpRight className={`h-4 w-4 shrink-0 text-${a.color} opacity-0 transition-all duration-200 group-hover:translate-x-0 group-hover:opacity-100 -translate-x-1`} />
          </Link>
        ))}
      </div>
    </div>
  );
}
