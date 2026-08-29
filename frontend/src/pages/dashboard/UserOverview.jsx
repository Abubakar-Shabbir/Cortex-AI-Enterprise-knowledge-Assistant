import {
  AlertCircle,
  Calendar,
  ChevronDown,
  Compass,
  FileText,
  HardDrive,
  Lock,
  MessageSquare,
  Sparkles,
  Timer,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import { useDashboard } from '../../api/hooks';
import { useSession } from '../../auth/SessionContext';
import ActivityFeedCard from '../../components/ActivityFeedCard';
import { ListCardSkeleton, StatCardSkeleton } from '../../components/CardSkeleton';
import EmptyState from '../../components/EmptyState';
import KnowledgeSnapshotCard from '../../components/KnowledgeSnapshotCard';
import MiniStatCard from '../../components/MiniStatCard';
import QuickActions from '../../components/QuickActions';
import Skeleton from '../../components/Skeleton';
import { timeAgo } from '../../lib/timeAgo';

function greetingWord() {
  const hour = new Date().getHours();
  if (hour < 12) return 'morning';
  if (hour < 18) return 'afternoon';
  return 'evening';
}

// Port of templates/dashboard/_welcome.html.
function Welcome({ name }) {
  const today = new Date().toLocaleDateString('en-US', {
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  });

  return (
    <div className="relative mb-2.5 overflow-hidden rounded-2xl border border-line bg-gradient-to-br from-primary/[0.07] via-card to-card p-5 shadow-soft dark:border-line-dark dark:from-primary/15 dark:via-card-dark dark:to-card-dark">
      <div aria-hidden="true" className="pointer-events-none absolute -right-8 -top-16 h-44 w-44 rounded-full bg-primary/10 blur-3xl dark:bg-primary/20" />
      <div aria-hidden="true" className="pointer-events-none absolute -bottom-20 right-32 h-36 w-36 rounded-full bg-accent/10 blur-3xl dark:bg-accent/20" />

      <div className="relative flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-bold leading-snug tracking-tight text-ink dark:text-ink-dark">
            Good {greetingWord()}, {name} <span aria-hidden="true">👋</span>
          </h1>
          <p className="mt-1 text-sm text-muted dark:text-muted-dark">Here&apos;s what&apos;s happening in your workspace today.</p>
        </div>

        <div className="inline-flex items-center gap-1.5 self-start rounded-lg border border-line bg-card/90 px-2.5 py-1.5 text-xs font-medium text-ink shadow-softer backdrop-blur-sm dark:border-line-dark dark:bg-card-dark/80 dark:text-ink-dark">
          <Calendar className="h-3.5 w-3.5 text-muted dark:text-muted-dark" />
          {today}
          <ChevronDown className="h-3.5 w-3.5 text-muted dark:text-muted-dark" />
        </div>
      </div>
    </div>
  );
}

export default function UserOverview() {
  const { data, isLoading, isError, refetch } = useDashboard();
  const { user, permissions, canViewAdminArea } = useSession();
  const has = (code) => permissions.includes(code);
  const displayName = user?.first_name || user?.username || '';

  if (isLoading) {
    return (
      <div>
        <Welcome name={displayName} />
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-[repeat(auto-fit,minmax(180px,1fr))]">
          {Array.from({ length: 4 }).map((_, i) => <StatCardSkeleton key={i} />)}
        </div>
        <div className="mt-2 rounded-xl border border-line bg-card p-3 shadow-soft dark:border-line-dark dark:bg-card-dark">
          <Skeleton className="h-3.5 w-32" />
          <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-16 rounded-xl" />)}
          </div>
        </div>
        <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => <ListCardSkeleton key={i} />)}
        </div>
      </div>
    );
  }

  if (isError) {
    return (
      <div>
        <Welcome name={displayName} />
        <div className="rounded-xl border border-danger/20 bg-danger/5 p-6 dark:border-danger-dark/20 dark:bg-danger/10">
          <div className="flex items-start gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-danger/10 text-danger dark:text-danger-dark">
              <AlertCircle className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-ink dark:text-ink-dark">Unable to load dashboard</h2>
              <p className="mt-1 text-xs text-muted dark:text-muted-dark">The dashboard could not be reached. Please try again.</p>
              <button
                type="button"
                onClick={() => refetch()}
                className="mt-3 rounded-lg bg-primary px-3 py-2 text-xs font-semibold text-white hover:bg-primary-dark"
              >
                Try again
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const stats = data?.stats || {};
  const knowledgeOverview = data?.knowledge_overview || {};
  const recentDocuments = data?.recent_documents || [];
  const recentQuestions = data?.recent_questions || [];
  const recentAiTaskRuns = data?.recent_ai_task_runs || [];
  const activityFeed = data?.activity_feed || [];

  const hasAnyModule =
    has('pages.documents') ||
    has('pages.ask_ai') ||
    has('pages.knowledge_base') ||
    has('pages.ai_tasks') ||
    has('pages.analytics') ||
    canViewAdminArea;

  return (
    <div>
      <Welcome name={displayName} />

      {!hasAnyModule ? (
        <EmptyState
          icon={Lock}
          title="No modules assigned yet"
          message="Your role doesn't grant access to any workspace features yet. An Admin can grant access from Roles."
        />
      ) : (
        <>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-[repeat(auto-fit,minmax(180px,1fr))] fade-in-up">
            {has('pages.documents') && (
              <MiniStatCard icon={FileText} iconBg="bg-primary/10" iconColor="text-primary" label="My Documents" value={stats.total_documents} numeric />
            )}
            {has('pages.ask_ai') && (
              <>
                <MiniStatCard icon={MessageSquare} iconBg="bg-info/10" iconColor="text-info" label="Questions Asked" value={stats.questions_asked} numeric />
                <MiniStatCard icon={Timer} iconBg="bg-warning/10" iconColor="text-warning" label="Avg Response Time" value={stats.avg_response_time} />
              </>
            )}
            {has('pages.documents') && (
              <MiniStatCard icon={HardDrive} iconBg="bg-success/10" iconColor="text-success" label="Storage Used" value={stats.storage_used} />
            )}
            {has('pages.ai_tasks') && (
              <MiniStatCard icon={Sparkles} iconBg="bg-accent/10" iconColor="text-accent" label="AI Task Runs" value={stats.ai_task_runs} numeric />
            )}
            {has('pages.knowledge_base') && (
              <MiniStatCard icon={Compass} iconBg="bg-success/10" iconColor="text-success" label="Topics" value={knowledgeOverview.total_entities} numeric />
            )}
          </div>

          <div className="mt-2">
            <QuickActions />
          </div>

          <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2 sm:[&>*:last-child:nth-child(odd)]:col-span-2">
            {has('pages.documents') && (
              <div className="flex h-full flex-col rounded-xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">
                <div className="flex items-center justify-between border-b border-line px-3.5 py-1.5 dark:border-line-dark">
                  <h2 className="text-sm font-semibold text-ink dark:text-ink-dark">Recent Documents</h2>
                  <Link to="/documents" className="text-xs font-medium text-primary hover:underline dark:text-primary-soft">View all</Link>
                </div>
                <div className="divide-y divide-line dark:divide-line-dark">
                  {recentDocuments.length === 0 ? (
                    <div className="flex items-center gap-2.5 px-3.5 py-3">
                      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-line/50 text-muted dark:bg-white/5 dark:text-muted-dark">
                        <FileText className="h-4 w-4" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="text-sm text-muted dark:text-muted-dark">No documents uploaded yet.</p>
                        <Link to="/documents" className="text-xs font-medium text-primary hover:underline dark:text-primary-soft">Upload your first document</Link>
                      </div>
                    </div>
                  ) : (
                    recentDocuments.map((doc) => (
                      <div key={doc.id} className="flex items-center gap-2.5 px-3.5 py-1.5">
                        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                          <FileText className="h-4 w-4" />
                        </div>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-medium leading-snug text-ink dark:text-ink-dark">{doc.title}</p>
                          <p className="mt-0.5 text-xs leading-snug text-muted dark:text-muted-dark">
                            {String(doc.file_type || '').toUpperCase()} · {doc.chunk_count} chunks · {timeAgo(doc.uploaded_at)} ago
                          </p>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            )}

            {has('pages.ask_ai') && (
              <div className="flex h-full flex-col rounded-xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">
                <div className="flex items-center justify-between border-b border-line px-3.5 py-1.5 dark:border-line-dark">
                  <h2 className="text-sm font-semibold text-ink dark:text-ink-dark">Recent Questions</h2>
                  <Link to="/history" className="text-xs font-medium text-primary hover:underline dark:text-primary-soft">View all</Link>
                </div>
                <div className="divide-y divide-line dark:divide-line-dark">
                  {recentQuestions.length === 0 ? (
                    <div className="flex items-center gap-2.5 px-3.5 py-3">
                      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-line/50 text-muted dark:bg-white/5 dark:text-muted-dark">
                        <MessageSquare className="h-4 w-4" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="text-sm text-muted dark:text-muted-dark">No questions asked yet.</p>
                        <Link to="/ask" className="text-xs font-medium text-primary hover:underline dark:text-primary-soft">Ask your first question</Link>
                      </div>
                    </div>
                  ) : (
                    recentQuestions.map((log) => (
                      <div key={log.id} className="flex items-center gap-2.5 px-3.5 py-1.5">
                        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                          <MessageSquare className="h-4 w-4" />
                        </div>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-medium leading-snug text-ink dark:text-ink-dark">{log.question}</p>
                          <p className="mt-0.5 text-xs leading-snug text-muted dark:text-muted-dark">
                            {log.confidence}% confidence · {timeAgo(log.created_at)} ago
                          </p>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            )}

            {has('pages.knowledge_base') && (
              <KnowledgeSnapshotCard data={knowledgeOverview} />
            )}

            <ActivityFeedCard events={activityFeed} />

            {has('pages.ai_tasks') && (
              <div className="flex h-full flex-col rounded-xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">
                <div className="flex items-center justify-between border-b border-line px-3.5 py-1.5 dark:border-line-dark">
                  <h2 className="text-sm font-semibold text-ink dark:text-ink-dark">Recent AI Task Runs</h2>
                  <Link to="/ai-tasks/history" className="text-xs font-medium text-primary hover:underline dark:text-primary-soft">View all</Link>
                </div>
                <div className="divide-y divide-line dark:divide-line-dark">
                  {recentAiTaskRuns.length === 0 ? (
                    <div className="flex items-center gap-2.5 px-3.5 py-3">
                      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-line/50 text-muted dark:bg-white/5 dark:text-muted-dark">
                        <Sparkles className="h-4 w-4" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="text-sm text-muted dark:text-muted-dark">No AI Tasks run yet.</p>
                        <Link to="/ai-tasks" className="text-xs font-medium text-primary hover:underline dark:text-primary-soft">Run your first AI Task</Link>
                      </div>
                    </div>
                  ) : (
                    recentAiTaskRuns.map((run) => (
                      <Link
                        key={run.id}
                        to={`/ai-tasks/${run.id}/results`}
                        className="flex items-center gap-2.5 px-3.5 py-1.5 hover:bg-surface dark:hover:bg-white/5"
                      >
                        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                          <Sparkles className="h-4 w-4" />
                        </div>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-medium leading-snug text-ink dark:text-ink-dark">{run.task_type_display}</p>
                          <p className="mt-0.5 text-xs leading-snug text-muted dark:text-muted-dark">
                            {run.status_display} · {timeAgo(run.created_at)} ago
                          </p>
                        </div>
                      </Link>
                    ))
                  )}
                </div>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
