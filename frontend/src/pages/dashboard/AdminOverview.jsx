import {
  AlertCircle,
  Bot,
  Boxes,
  ChevronDown,
  Cpu,
  Database,
  Eye,
  FileText,
  MessageSquareText,
  MoreHorizontal,
  PlugZap,
  Sparkles,
  Trash2,
} from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAdminOverview, useDeleteDocument } from '../../api/hooks';
import { useSession } from '../../auth/SessionContext';
import ActivityFeedCard from '../../components/ActivityFeedCard';
import { ChartCardSkeleton, ListCardSkeleton, StatCardSkeleton } from '../../components/CardSkeleton';
import ChartCanvas from '../../components/ChartCanvas';
import EmptyState from '../../components/EmptyState';
import KnowledgeSnapshotCard from '../../components/KnowledgeSnapshotCard';
import KpiCard from '../../components/KpiCard';
import QuickActions from '../../components/QuickActions';
import Skeleton from '../../components/Skeleton';
import { useTheme } from '../../hooks/useTheme';
import { timeAgo } from '../../lib/timeAgo';

const CHART_RANGES = [7, 14, 30];
const GRID_COLOR = 'rgba(109, 102, 101, 0.12)';
const PRIMARY = '#8B1E2D';

function SystemStatusCard({ status }) {
  const allHealthy = status?.db_online && status?.pgvector_enabled && status?.llm_configured;

  const rows = [
    { icon: Database, label: 'PostgreSQL', healthy: status?.db_online, healthyText: 'Healthy', unhealthyText: 'Offline' },
    { icon: Boxes, label: 'pgvector', healthy: status?.pgvector_enabled, healthyText: 'Healthy', unhealthyText: 'Not enabled' },
    { icon: Cpu, label: 'Embedding Model', healthy: true, healthyText: 'Healthy', unhealthyText: 'Healthy', title: status?.embedding_model },
    {
      icon: Bot,
      label: `LLM (${status?.llm_provider === 'openrouter' ? 'OpenRouter' : 'Gemini'})`,
      healthy: status?.llm_configured,
      healthyText: 'Healthy',
      unhealthyText: 'Not configured',
      title: status?.llm_model,
    },
    {
      icon: PlugZap,
      label: 'API Services',
      healthy: status?.db_online && status?.llm_configured,
      healthyText: 'Healthy',
      unhealthyText: 'Degraded',
    },
  ];

  return (
    <div className="flex h-full flex-col rounded-xl border border-line bg-card p-3 shadow-soft dark:border-line-dark dark:bg-card-dark">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-ink dark:text-ink-dark">System Status</h2>
        <span className="flex items-center gap-1.5 text-xs font-medium">
          {allHealthy ? (
            <>
              <span className="text-success dark:text-success-dark">All systems operational</span>
              <span className="h-1.5 w-1.5 rounded-full bg-success dark:bg-success-dark" />
            </>
          ) : (
            <>
              <span className="text-warning dark:text-warning-dark">Attention needed</span>
              <span className="h-1.5 w-1.5 rounded-full bg-warning dark:bg-warning-dark" />
            </>
          )}
        </span>
      </div>

      <div className="space-y-1.5 text-sm">
        {rows.map((row) => (
          <div key={row.label} className="flex items-center justify-between">
            <span className="flex items-center gap-2 text-muted dark:text-muted-dark"><row.icon className="h-4 w-4" /> {row.label}</span>
            <span
              title={row.title}
              className={`flex items-center gap-1.5 font-medium ${row.healthy ? 'text-success dark:text-success-dark' : 'text-danger dark:text-danger-dark'}`}
            >
              <span className={`h-1.5 w-1.5 rounded-full ${row.healthy ? 'bg-success dark:bg-success-dark' : 'bg-danger dark:bg-danger-dark'}`} />
              {row.healthy ? row.healthyText : row.unhealthyText}
            </span>
          </div>
        ))}
      </div>

      <Link to="/admin/system-health" className="mt-auto block rounded-lg bg-primary/10 px-3 py-1.5 text-center text-sm font-semibold text-primary transition-colors hover:bg-primary/15 dark:text-primary-soft">
        View System Health
      </Link>
    </div>
  );
}

function RecentUploadsCard({ documents }) {
  return (
    <div className="flex h-full flex-col rounded-xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">
      <div className="flex items-center justify-between border-b border-line px-3.5 py-2 dark:border-line-dark">
        <h2 className="text-sm font-semibold text-ink dark:text-ink-dark">Recent Uploads</h2>
        <Link to="/documents" className="text-xs font-medium text-primary hover:underline dark:text-primary-soft">View all</Link>
      </div>
      <div className="divide-y divide-line dark:divide-line-dark">
        {documents.length === 0 ? (
          <div className="px-3.5 py-4 text-center">
            <p className="text-sm text-muted dark:text-muted-dark">No uploads yet.</p>
          </div>
        ) : (
          documents.map((doc) => (
            <div key={doc.id} className="flex items-center gap-2.5 px-3.5 py-1.5">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <FileText className="h-4 w-4" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium leading-snug text-ink dark:text-ink-dark">{doc.title}</p>
                <p className="mt-0.5 text-xs leading-snug text-muted dark:text-muted-dark">{timeAgo(doc.uploaded_at)} ago</p>
              </div>
              <span className="shrink-0 text-xs text-muted dark:text-muted-dark">{formatBytes(doc.file_size)}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function formatBytes(bytes) {
  if (!bytes) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const i = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
  return `${(bytes / 1024 ** i).toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

const AI_TASK_STATUS_STYLES = {
  completed: 'bg-success/10 text-success dark:text-success-dark',
  failed: 'bg-danger/10 text-danger dark:text-danger-dark',
  running: 'bg-warning/10 text-warning dark:text-warning-dark',
};

function RecentAiTaskRunsCard({ runs }) {
  return (
    <div className="flex h-full flex-col rounded-xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">
      <div className="flex items-center justify-between border-b border-line px-3.5 py-2 dark:border-line-dark">
        <h2 className="text-sm font-semibold text-ink dark:text-ink-dark">Recent AI Task Runs</h2>
        <Link to="/ai-tasks/history" className="text-xs font-medium text-primary hover:underline dark:text-primary-soft">View all</Link>
      </div>
      <div className="divide-y divide-line dark:divide-line-dark">
        {runs.length === 0 ? (
          <div className="px-3.5 py-4 text-center">
            <p className="text-sm text-muted dark:text-muted-dark">No AI Tasks run yet.</p>
            <Link to="/ai-tasks" className="mt-2 inline-block text-sm font-medium text-primary hover:underline dark:text-primary-soft">Run your first AI Task</Link>
          </div>
        ) : (
          runs.map((run) => (
            <Link key={run.id} to={`/ai-tasks/${run.id}/results`} className="flex items-center gap-2.5 px-3.5 py-1.5 hover:bg-surface dark:hover:bg-white/5">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <Sparkles className="h-4 w-4" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium leading-snug text-ink dark:text-ink-dark">{run.task_type_display}</p>
                <p className="mt-0.5 text-xs leading-snug text-muted dark:text-muted-dark">
                  {run.document_count} document{run.document_count === 1 ? '' : 's'} · {timeAgo(run.created_at)} ago
                </p>
              </div>
              <span className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium ${AI_TASK_STATUS_STYLES[run.status] || 'bg-line text-muted dark:bg-white/10 dark:text-muted-dark'}`}>
                {run.status_display}
              </span>
            </Link>
          ))
        )}
      </div>
    </div>
  );
}

function DocumentsOverTimeCard({ data, hasDocuments, range, onRangeChange }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    function onClickOutside(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener('mousedown', onClickOutside);
    return () => document.removeEventListener('mousedown', onClickOutside);
  }, []);

  const chartConfig = {
    type: 'bar',
    data: {
      labels: data?.labels || [],
      datasets: [
        {
          type: 'bar',
          label: 'New that day',
          data: data?.daily || [],
          yAxisID: 'yDaily',
          backgroundColor: 'rgba(139, 30, 45, 0.25)',
          hoverBackgroundColor: 'rgba(139, 30, 45, 0.4)',
          borderRadius: 3,
          maxBarThickness: 22,
        },
        {
          type: 'line',
          label: 'Total documents',
          data: data?.series || [],
          yAxisID: 'yTotal',
          borderColor: PRIMARY,
          backgroundColor: (context) => {
            const { ctx, chartArea } = context.chart;
            if (!chartArea) return null;
            const gradient = ctx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
            gradient.addColorStop(0, 'rgba(139, 30, 45, 0.22)');
            gradient.addColorStop(1, 'rgba(139, 30, 45, 0)');
            return gradient;
          },
          fill: true,
          tension: 0.35,
          pointRadius: 0,
          pointHoverRadius: 4,
          pointHoverBackgroundColor: PRIMARY,
          pointHoverBorderColor: '#fff',
          pointHoverBorderWidth: 2,
          borderWidth: 2.5,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label(item) {
              const suffix = item.dataset.yAxisID === 'yDaily' ? ' new' : ' total';
              return ` ${item.dataset.label}: ${item.formattedValue}${suffix}`;
            },
          },
        },
      },
      scales: {
        x: { grid: { display: false } },
        yTotal: { position: 'left', grid: { color: GRID_COLOR }, beginAtZero: true, ticks: { precision: 0 } },
        yDaily: {
          position: 'right',
          grid: { drawOnChartArea: false },
          beginAtZero: true,
          suggestedMax: Math.max(1, ...(data?.daily || [0])) * 3,
          ticks: { precision: 0, maxTicksLimit: 3 },
        },
      },
    },
  };

  return (
    <div className="min-w-0 rounded-xl border border-line bg-card p-3 shadow-soft dark:border-line-dark dark:bg-card-dark">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-ink dark:text-ink-dark">Documents Over Time</h2>
        {hasDocuments && (
          <div className="relative" ref={ref}>
            <button
              type="button"
              onClick={() => setOpen((o) => !o)}
              className="inline-flex items-center gap-1 rounded-lg border border-line px-2 py-1 text-xs font-medium text-ink transition-colors hover:bg-surface dark:border-line-dark dark:text-ink-dark dark:hover:bg-white/5"
            >
              {range} Days <ChevronDown className={`h-3 w-3 transition-transform ${open ? 'rotate-180' : ''}`} />
            </button>
            {open && (
              <div className="absolute right-0 z-20 mt-1 w-28 rounded-xl border border-line bg-card p-1.5 shadow-soft dark:border-line-dark dark:bg-card-dark">
                {CHART_RANGES.map((option) => (
                  <button
                    key={option}
                    type="button"
                    onClick={() => { onRangeChange(option); setOpen(false); }}
                    className={`block w-full rounded-lg px-3 py-1.5 text-left text-sm ${option === range ? 'font-semibold text-primary dark:text-primary-soft' : 'text-ink hover:bg-surface dark:text-ink-dark dark:hover:bg-white/5'}`}
                  >
                    {option} Days
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {hasDocuments ? (
        <>
          <div className="relative h-40 w-full"><ChartCanvas config={chartConfig} /></div>
          <div className="mt-2 flex items-center gap-3 text-[11px] text-muted dark:text-muted-dark">
            <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-primary" /> Total documents</span>
            <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm bg-primary/30" /> New that day</span>
          </div>
        </>
      ) : (
        <EmptyState icon={AlertCircle} title="No activity yet" message="Upload a document to start tracking growth over time." actionTo="/documents" actionLabel="Go to Documents" />
      )}
    </div>
  );
}

function DocumentTypesCard({ data, isDark }) {
  const breakdown = data?.breakdown || [];

  const chartConfig = {
    type: 'doughnut',
    data: {
      labels: breakdown.map((item) => item.type),
      datasets: [{
        data: breakdown.map((item) => item.count),
        backgroundColor: breakdown.map((item) => item.color),
        hoverOffset: 6,
        borderWidth: 2,
        borderColor: isDark ? '#1c1414' : '#fff',
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '72%',
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label(item) {
              const entry = breakdown[item.dataIndex];
              return ` ${entry.type}: ${entry.count} (${entry.percent}%)`;
            },
          },
        },
      },
    },
  };

  return (
    <div className="rounded-xl border border-line bg-card p-3 shadow-soft dark:border-line-dark dark:bg-card-dark">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-ink dark:text-ink-dark">Document Types</h2>
        <Link to="/documents" className="text-xs font-medium text-primary hover:underline dark:text-primary-soft">View all</Link>
      </div>

      {breakdown.length > 0 ? (
        <>
          <div className="relative mx-auto h-24 w-24">
            <ChartCanvas config={chartConfig} />
            <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-lg font-bold leading-tight text-ink dark:text-ink-dark">{data.total}</span>
              <span className="text-xs text-muted dark:text-muted-dark">Total</span>
            </div>
          </div>
          <div className="mt-2.5 space-y-1.5">
            {breakdown.map((item) => (
              <div key={item.type} className="flex items-center justify-between text-xs">
                <span className="flex items-center gap-2 font-medium text-ink dark:text-ink-dark">
                  <span className="h-2 w-2 rounded-full" style={{ backgroundColor: item.color }} />
                  {item.type}
                </span>
                <span className="text-muted dark:text-muted-dark">{item.percent}% ({item.count})</span>
              </div>
            ))}
          </div>
        </>
      ) : (
        <EmptyState icon={FileText} title="No documents yet" message="Upload a document to see its type breakdown here." actionTo="/documents" actionLabel="Go to Documents" />
      )}
    </div>
  );
}

const DOC_STATUS_STYLES = {
  Processed: 'bg-success/10 text-success dark:text-success-dark',
  Partial: 'bg-warning/10 text-warning dark:text-warning-dark',
};

function RecentDocumentsTable({ rows }) {
  const [openRowId, setOpenRowId] = useState(null);
  const deleteMutation = useDeleteDocument();

  return (
    <div className="rounded-xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">
      <div className="flex items-center justify-between border-b border-line px-3.5 py-2 dark:border-line-dark">
        <h2 className="text-sm font-semibold text-ink dark:text-ink-dark">Recent Documents</h2>
        <Link to="/documents" className="text-xs font-medium text-primary hover:underline dark:text-primary-soft">View all</Link>
      </div>

      {rows.length === 0 ? (
        <EmptyState icon={FileText} title="No documents yet" message="Upload your first document to see it here." />
      ) : (
        <div className="max-h-[260px] overflow-auto">
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead className="sticky top-0 z-10 bg-card dark:bg-card-dark">
              <tr className="border-b border-line text-xs font-semibold uppercase tracking-wide text-muted dark:border-line-dark dark:text-muted-dark">
                <th className="px-3.5 py-2">Name</th>
                <th className="px-2.5 py-2">Owner</th>
                <th className="px-2.5 py-2">Type</th>
                <th className="px-2.5 py-2 text-right">Chunks</th>
                <th className="px-2.5 py-2 text-right">Size</th>
                <th className="px-2.5 py-2">Uploaded</th>
                <th className="px-2.5 py-2">Status</th>
                <th className="px-3.5 py-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line dark:divide-line-dark">
              {rows.map((doc) => (
                <tr key={doc.id} className="transition-colors hover:bg-surface dark:hover:bg-white/5">
                  <td className="max-w-[220px] truncate px-3.5 py-2 font-medium text-ink dark:text-ink-dark">
                    <span className="flex items-center gap-2.5">
                      <FileText className="h-4 w-4 shrink-0 text-primary dark:text-primary-soft" />
                      <span className="truncate">{doc.title}</span>
                    </span>
                  </td>
                  <td className="px-2.5 py-2 text-muted dark:text-muted-dark">{doc.owner}</td>
                  <td className="px-2.5 py-2 text-muted dark:text-muted-dark">{doc.file_type}</td>
                  <td className="px-2.5 py-2 text-right text-muted dark:text-muted-dark">{doc.chunk_count}</td>
                  <td className="px-2.5 py-2 text-right text-muted dark:text-muted-dark">{doc.size}</td>
                  <td className="px-2.5 py-2 text-muted dark:text-muted-dark">{timeAgo(doc.uploaded_at)} ago</td>
                  <td className="px-2.5 py-2">
                    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${DOC_STATUS_STYLES[doc.status] || 'bg-muted/10 text-muted dark:text-muted-dark'}`}>
                      {doc.status}
                    </span>
                  </td>
                  <td className="px-3.5 py-2 text-right">
                    <div className="relative inline-block text-left">
                      <button
                        type="button"
                        onClick={() => setOpenRowId((id) => (id === doc.id ? null : doc.id))}
                        className="rounded-lg p-1.5 text-muted hover:bg-surface dark:text-muted-dark dark:hover:bg-white/5"
                        aria-label="Row actions"
                      >
                        <MoreHorizontal className="h-4 w-4" />
                      </button>
                      {openRowId === doc.id && (
                        <div className="absolute right-0 z-20 mt-1 w-40 rounded-xl border border-line bg-card p-1.5 shadow-soft dark:border-line-dark dark:bg-card-dark">
                          <Link to="/documents" className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-ink hover:bg-surface dark:text-ink-dark dark:hover:bg-white/5">
                            <Eye className="h-3.5 w-3.5 text-muted dark:text-muted-dark" /> View
                          </Link>
                          <button
                            type="button"
                            onClick={() => {
                              setOpenRowId(null);
                              if (window.confirm('Delete this document?')) deleteMutation.mutate(doc.id);
                            }}
                            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm text-danger hover:bg-danger/10 dark:text-danger-dark"
                          >
                            <Trash2 className="h-3.5 w-3.5" /> Delete
                          </button>
                        </div>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default function AdminOverview() {
  const [range, setRange] = useState(7);
  const { data, isLoading, isError, refetch } = useAdminOverview(range);
  const { permissions } = useSession();
  const { isDark } = useTheme();
  const has = (code) => permissions.includes(code);

  if (isLoading) {
    return (
      <div>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-[repeat(auto-fit,minmax(200px,1fr))]">
          {Array.from({ length: 5 }).map((_, i) => <StatCardSkeleton key={i} />)}
        </div>
        <div className="mt-2 grid grid-cols-1 gap-2 xl:grid-cols-[minmax(0,1fr)_minmax(240px,340px)]">
          <ChartCardSkeleton />
          <ChartCardSkeleton height="h-24" />
        </div>
        <div className="mt-2">
          <ListCardSkeleton rows={5} />
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
    );
  }

  const stats = data?.stats || {};
  const kpiTrends = data?.kpi_trends || {};
  const knowledgeOverview = data?.knowledge_overview || {};

  return (
    <div>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-[repeat(auto-fit,minmax(200px,1fr))] fade-in-up">
        {has('pages.documents') && (
          <>
            <KpiCard icon={FileText} iconBg="bg-primary/10" iconColor="text-primary" label="Total Documents" value={stats.total_documents} numeric trend={kpiTrends.documents} trendLabel="vs last 7 days" chartColor="#8B1E2D" />
            <KpiCard icon={Boxes} iconBg="bg-warning/10" iconColor="text-warning" label="Total Chunks" value={stats.total_chunks} numeric trend={kpiTrends.chunks} trendLabel="vs last 7 days" chartColor="#C77700" />
            <KpiCard icon={Database} iconBg="bg-success/10" iconColor="text-success" label="Storage Used" value={stats.storage_used} trend={kpiTrends.storage} trendLabel="vs last 7 days" chartColor="#1F7A4D" />
          </>
        )}
        {has('pages.ask_ai') && (
          <KpiCard icon={MessageSquareText} iconBg="bg-info/10" iconColor="text-info" label="Queries Today" value={stats.today_queries} numeric trend={kpiTrends.queries} trendLabel="vs yesterday" chartColor="#2A78D6" />
        )}
        {has('pages.ai_tasks') && (
          <KpiCard icon={Sparkles} iconBg="bg-accent/10" iconColor="text-accent" label="AI Task Runs" value={stats.ai_task_runs} numeric trend={kpiTrends.ai_tasks} trendLabel="vs last 7 days" chartColor="#4A3AA7" />
        )}
      </div>

      {has('pages.documents') && (
        <>
          <div className="mt-2 grid grid-cols-1 gap-2 xl:grid-cols-[minmax(0,1fr)_minmax(240px,340px)]">
            <DocumentsOverTimeCard data={data?.documents_over_time} hasDocuments={!!stats.total_documents} range={range} onRangeChange={setRange} />
            <DocumentTypesCard data={data?.document_types} isDark={isDark} />
          </div>

          <div className="mt-2">
            <RecentDocumentsTable rows={data?.recent_documents_table || []} />
          </div>
        </>
      )}

      <div className="mt-2">
        <QuickActions />
      </div>

      <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2 sm:[&>*:last-child:nth-child(odd)]:col-span-2">
        <SystemStatusCard status={data?.system_status} />
        {has('pages.knowledge_base') && (
          <KnowledgeSnapshotCard data={knowledgeOverview} showChart />
        )}
        {has('pages.documents') && (
          <RecentUploadsCard documents={data?.recent_documents || []} />
        )}
        {has('pages.ai_tasks') && (
          <RecentAiTaskRunsCard runs={data?.recent_ai_task_runs || []} />
        )}
        <ActivityFeedCard events={data?.activity_feed || []} />
      </div>
    </div>
  );
}
