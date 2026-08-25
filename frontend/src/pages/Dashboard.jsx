import {
  Activity,
  AlertCircle,
  ArrowRight,
  Bot,
  CheckCircle2,
  Clock3,
  Database,
  FileText,
  MessageSquare,
  Upload,
  Zap,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import { useDashboard } from '../api/hooks';
import PageHeader from '../components/PageHeader';
import StatCard from '../components/StatCard';
import MiniStatCard from '../components/MiniStatCard';

function StatusBadge({ status }) {
  const normalized = String(status || '').toLowerCase();

  const styles = {
    completed:
      'bg-success/10 text-success dark:text-success-dark',
    processed:
      'bg-success/10 text-success dark:text-success-dark',
    processing:
      'bg-warning/10 text-warning dark:text-warning-dark',
    pending:
      'bg-warning/10 text-warning dark:text-warning-dark',
    failed:
      'bg-danger/10 text-danger dark:text-danger-dark',
    error:
      'bg-danger/10 text-danger dark:text-danger-dark',
  };

  return (
    <span
      className={`inline-flex rounded-full px-2.5 py-1 text-[11px] font-semibold ${
        styles[normalized] ||
        'bg-surface text-muted dark:bg-white/5 dark:text-muted-dark'
      }`}
    >
      {status || 'Unknown'}
    </span>
  );
}

function LoadingCard() {
  return (
    <div className="animate-pulse rounded-xl border border-line bg-card p-5 dark:border-line-dark dark:bg-card-dark">
      <div className="h-3 w-24 rounded bg-surface dark:bg-white/10" />
      <div className="mt-4 h-7 w-16 rounded bg-surface dark:bg-white/10" />
    </div>
  );
}

function EmptyState({ icon: Icon, title, description }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-12 text-center">
      <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary/10 text-primary dark:bg-primary/15 dark:text-primary-soft">
        <Icon className="h-5 w-5" />
      </div>

      <p className="mt-3 text-sm font-semibold text-ink dark:text-ink-dark">
        {title}
      </p>

      <p className="mt-1 max-w-sm text-xs text-muted dark:text-muted-dark">
        {description}
      </p>
    </div>
  );
}

export default function Dashboard() {
  const { data, isLoading, isError, refetch } = useDashboard();

  if (isError) {
    return (
      <div>
        <PageHeader
          title="Dashboard"
          subtitle="Overview of your document intelligence workspace."
        />

        <div className="rounded-xl border border-danger/20 bg-danger/5 p-6 dark:border-danger-dark/20 dark:bg-danger/10">
          <div className="flex items-start gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-danger/10 text-danger dark:text-danger-dark">
              <AlertCircle className="h-5 w-5" />
            </div>

            <div>
              <h2 className="text-sm font-semibold text-ink dark:text-ink-dark">
                Unable to load dashboard
              </h2>

              <p className="mt-1 text-xs text-muted dark:text-muted-dark">
                The dashboard API could not be reached. Please try again.
              </p>

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

  const stats = data?.stats || data?.statistics || {};
  const processing = data?.processing || {};
  const recentDocuments =
    data?.recent_documents || data?.recentDocuments || [];
  const recentQueries =
    data?.recent_queries || data?.recentQueries || [];

  const totalDocuments =
    stats.total_documents ??
    stats.documents ??
    data?.total_documents ??
    0;

  const processedDocuments =
    stats.processed_documents ??
    stats.processed ??
    data?.processed_documents ??
    0;

  const totalQueries =
    stats.total_queries ??
    stats.queries ??
    data?.total_queries ??
    0;

  const totalChunks =
    stats.total_chunks ??
    stats.chunks ??
    data?.total_chunks ??
    0;

  const processingCount =
    processing.processing ??
    stats.processing ??
    0;

  const failedCount =
    processing.failed ??
    stats.failed ??
    0;

  const embeddedCount =
    processing.embedded ??
    stats.embedded ??
    0;

  const successRate =
    processing.success_rate ??
    stats.success_rate ??
    0;

  return (
    <div className="space-y-6">

      {/* ========================================================= */}
      {/* HEADER */}
      {/* ========================================================= */}

      <PageHeader
        title="Dashboard"
        subtitle="Overview of your document intelligence workspace."
      />

      {/* ========================================================= */}
      {/* QUICK ACTIONS */}
      {/* ========================================================= */}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">

        <Link
          to="/documents"
          className="group rounded-xl border border-line bg-card p-4 shadow-soft transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/30 hover:shadow-md dark:border-line-dark dark:bg-card-dark dark:hover:border-primary-soft/30"
        >
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary dark:bg-primary/15 dark:text-primary-soft">
              <Upload className="h-5 w-5" />
            </div>

            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold text-ink dark:text-ink-dark">
                Upload Document
              </p>
              <p className="mt-0.5 text-xs text-muted dark:text-muted-dark">
                Add a new document to your knowledge base.
              </p>
            </div>

            <ArrowRight className="h-4 w-4 text-muted transition-transform group-hover:translate-x-1 dark:text-muted-dark" />
          </div>
        </Link>

        <Link
          to="/ask"
          className="group rounded-xl border border-line bg-card p-4 shadow-soft transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/30 hover:shadow-md dark:border-line-dark dark:bg-card-dark dark:hover:border-primary-soft/30"
        >
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary dark:bg-primary/15 dark:text-primary-soft">
              <Bot className="h-5 w-5" />
            </div>

            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold text-ink dark:text-ink-dark">
                Ask AI
              </p>
              <p className="mt-0.5 text-xs text-muted dark:text-muted-dark">
                Search your documents using natural language.
              </p>
            </div>

            <ArrowRight className="h-4 w-4 text-muted transition-transform group-hover:translate-x-1 dark:text-muted-dark" />
          </div>
        </Link>

        <Link
          to="/documents"
          className="group rounded-xl border border-line bg-card p-4 shadow-soft transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/30 hover:shadow-md dark:border-line-dark dark:bg-card-dark dark:hover:border-primary-soft/30"
        >
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary dark:bg-primary/15 dark:text-primary-soft">
              <FileText className="h-5 w-5" />
            </div>

            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold text-ink dark:text-ink-dark">
                Manage Documents
              </p>
              <p className="mt-0.5 text-xs text-muted dark:text-muted-dark">
                Browse, process and organize your files.
              </p>
            </div>

            <ArrowRight className="h-4 w-4 text-muted transition-transform group-hover:translate-x-1 dark:text-muted-dark" />
          </div>
        </Link>

      </div>

      {/* ========================================================= */}
      {/* MAIN STATISTICS */}
      {/* ========================================================= */}

      <section>
        <div className="mb-3 flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold text-ink dark:text-ink-dark">
              Workspace Overview
            </h2>

            <p className="mt-0.5 text-xs text-muted dark:text-muted-dark">
              Current activity across your workspace.
            </p>
          </div>
        </div>

        {isLoading ? (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <LoadingCard />
            <LoadingCard />
            <LoadingCard />
            <LoadingCard />
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">

            <StatCard
              icon={FileText}
              label="Total Documents"
              value={totalDocuments}
              numeric
            />

            <StatCard
              icon={CheckCircle2}
              label="Processed Documents"
              value={processedDocuments}
              numeric
            />

            <StatCard
              icon={MessageSquare}
              label="AI Queries"
              value={totalQueries}
              numeric
            />

            <StatCard
              icon={Database}
              label="Indexed Chunks"
              value={totalChunks}
              numeric
            />

          </div>
        )}
      </section>

      {/* ========================================================= */}
      {/* PROCESSING OVERVIEW */}
      {/* ========================================================= */}

      <section>
        <div className="mb-3">
          <h2 className="text-sm font-semibold text-ink dark:text-ink-dark">
            Processing Overview
          </h2>

          <p className="mt-0.5 text-xs text-muted dark:text-muted-dark">
            Current document processing and indexing status.
          </p>
        </div>

        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">

          <MiniStatCard
            icon={Clock3}
            label="Processing"
            value={processingCount}
            numeric
            iconBg="bg-warning/10"
            iconColor="text-warning"
          />

          <MiniStatCard
            icon={CheckCircle2}
            label="Embedded"
            value={embeddedCount}
            numeric
            iconBg="bg-success/10"
            iconColor="text-success"
          />

          <MiniStatCard
            icon={AlertCircle}
            label="Failed"
            value={failedCount}
            numeric
            iconBg="bg-danger/10"
            iconColor="text-danger"
          />

          <MiniStatCard
            icon={Activity}
            label="Success Rate"
            value={`${successRate}%`}
            iconBg="bg-primary/10"
            iconColor="text-primary"
          />

        </div>
      </section>

      {/* ========================================================= */}
      {/* RECENT ACTIVITY */}
      {/* ========================================================= */}

      <div className="grid gap-6 xl:grid-cols-2">

        {/* ======================================================= */}
        {/* RECENT DOCUMENTS */}
        {/* ======================================================= */}

        <section className="overflow-hidden rounded-xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">

          <div className="flex items-center justify-between border-b border-line px-5 py-4 dark:border-line-dark">

            <div>
              <h2 className="text-sm font-semibold text-ink dark:text-ink-dark">
                Recent Documents
              </h2>

              <p className="mt-0.5 text-xs text-muted dark:text-muted-dark">
                Recently uploaded documents.
              </p>
            </div>

            <Link
              to="/documents"
              className="flex items-center gap-1 text-xs font-semibold text-primary hover:underline dark:text-primary-soft"
            >
              View all
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>

          </div>

          {isLoading ? (
            <div className="space-y-3 p-5">
              <div className="h-12 animate-pulse rounded-lg bg-surface dark:bg-white/5" />
              <div className="h-12 animate-pulse rounded-lg bg-surface dark:bg-white/5" />
              <div className="h-12 animate-pulse rounded-lg bg-surface dark:bg-white/5" />
            </div>
          ) : recentDocuments.length === 0 ? (
            <EmptyState
              icon={FileText}
              title="No documents yet"
              description="Upload your first document to start building your knowledge base."
            />
          ) : (
            <div className="divide-y divide-line dark:divide-line-dark">

              {recentDocuments.slice(0, 6).map((document, index) => (
                <div
                  key={document.id ?? index}
                  className="flex items-center gap-3 px-5 py-3.5 transition-colors hover:bg-surface/60 dark:hover:bg-white/[0.03]"
                >

                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary dark:bg-primary/15 dark:text-primary-soft">
                    <FileText className="h-4 w-4" />
                  </div>

                  <div className="min-w-0 flex-1">

                    <p
                      className="truncate text-sm font-medium text-ink dark:text-ink-dark"
                      title={document.name || document.title}
                    >
                      {document.name || document.title || 'Untitled document'}
                    </p>

                    <p className="mt-0.5 text-[11px] text-muted dark:text-muted-dark">
                      {document.file_type ||
                        document.type ||
                        'Document'}
                      {document.created_at
                        ? ` · ${new Date(
                            document.created_at
                          ).toLocaleDateString()}`
                        : ''}
                    </p>

                  </div>

                  <StatusBadge
                    status={
                      document.status ||
                      document.processing_status ||
                      'Unknown'
                    }
                  />

                </div>
              ))}

            </div>
          )}

        </section>

        {/* ======================================================= */}
        {/* RECENT QUERIES */}
        {/* ======================================================= */}

        <section className="overflow-hidden rounded-xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">

          <div className="flex items-center justify-between border-b border-line px-5 py-4 dark:border-line-dark">

            <div>
              <h2 className="text-sm font-semibold text-ink dark:text-ink-dark">
                Recent AI Queries
              </h2>

              <p className="mt-0.5 text-xs text-muted dark:text-muted-dark">
                Latest questions asked to your knowledge base.
              </p>
            </div>

            <Link
              to="/ask"
              className="flex items-center gap-1 text-xs font-semibold text-primary hover:underline dark:text-primary-soft"
            >
              Ask AI
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>

          </div>

          {isLoading ? (
            <div className="space-y-3 p-5">
              <div className="h-12 animate-pulse rounded-lg bg-surface dark:bg-white/5" />
              <div className="h-12 animate-pulse rounded-lg bg-surface dark:bg-white/5" />
              <div className="h-12 animate-pulse rounded-lg bg-surface dark:bg-white/5" />
            </div>
          ) : recentQueries.length === 0 ? (
            <EmptyState
              icon={MessageSquare}
              title="No queries yet"
              description="Ask AI a question to see your recent searches here."
            />
          ) : (
            <div className="divide-y divide-line dark:divide-line-dark">

              {recentQueries.slice(0, 6).map((query, index) => (
                <div
                  key={query.id ?? index}
                  className="px-5 py-3.5 transition-colors hover:bg-surface/60 dark:hover:bg-white/[0.03]"
                >

                  <div className="flex items-start gap-3">

                    <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary dark:bg-primary/15 dark:text-primary-soft">
                      <MessageSquare className="h-3.5 w-3.5" />
                    </div>

                    <div className="min-w-0 flex-1">

                      <p className="line-clamp-2 text-sm font-medium text-ink dark:text-ink-dark">
                        {query.question ||
                          query.query ||
                          'Untitled query'}
                      </p>

                      <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted dark:text-muted-dark">

                        {query.response_time_ms != null && (
                          <span className="flex items-center gap-1">
                            <Zap className="h-3 w-3" />
                            {query.response_time_ms} ms
                          </span>
                        )}

                        {query.confidence != null && (
                          <span>
                            Confidence {query.confidence}%
                          </span>
                        )}

                        {query.created_at && (
                          <span>
                            {new Date(
                              query.created_at
                            ).toLocaleDateString()}
                          </span>
                        )}

                      </div>

                    </div>

                  </div>

                </div>
              ))}

            </div>
          )}

        </section>

      </div>

    </div>
  );
}