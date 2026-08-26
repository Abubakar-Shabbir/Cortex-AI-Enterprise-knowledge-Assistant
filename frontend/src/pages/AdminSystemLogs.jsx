import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  Activity, AlertTriangle, ExternalLink, Eye, Filter, FileUp, Globe, Lock, MapPin, RotateCw,
  ShieldAlert, ShieldCheck, Sparkles, Square, Terminal, TriangleAlert, X,
} from 'lucide-react';
import PageHeader from '../components/PageHeader';
import Spinner from '../components/Spinner';
import StatCard from '../components/StatCard';
import EmptyState from '../components/EmptyState';
import AppLoader from '../components/AppLoader';
import { timeAgo } from '../lib/timeAgo';
import {
  fetchAdminErrorGroupDetail, fetchAdminTraceDetail, useAdminSystemLogs, useCancelAiTask,
} from '../api/hooks';

const STATUS_CLASSES = {
  completed: 'bg-success/10 text-success dark:text-success-dark',
  failed: 'bg-danger/10 text-danger dark:text-danger-dark',
  cancelled: 'bg-line text-muted dark:bg-white/10 dark:text-muted-dark',
};
const CATEGORY_CLASSES = {
  success: 'bg-success/10 text-success dark:text-success-dark',
  danger: 'bg-danger/10 text-danger dark:text-danger-dark',
  warning: 'bg-warning/10 text-warning dark:text-warning-dark',
};

function TraceDetailModal({ traceId, onClose }) {
  const [state, setState] = useState({ loading: true, data: null });
  useEffect(() => { fetchAdminTraceDetail(traceId).then((data) => setState({ loading: false, data })); }, [traceId]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-line bg-card p-6 shadow-2xl dark:border-line-dark dark:bg-card-dark">
        {state.loading ? <p className="text-sm text-muted dark:text-muted-dark">Loading…</p> : state.data && (
          <div className="space-y-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-xs font-medium uppercase tracking-wide text-muted dark:text-muted-dark">{state.data.source} · <span className="font-mono">{state.data.trace_id}</span></p>
                <p className="text-xs text-muted dark:text-muted-dark">{state.data.created_at}</p>
              </div>
              <button type="button" onClick={onClose} className="flex h-8 w-8 items-center justify-center rounded-lg text-muted hover:bg-surface dark:text-muted-dark dark:hover:bg-white/5"><X className="h-4 w-4" /></button>
            </div>

            <div className="grid grid-cols-3 gap-3 text-center text-xs sm:grid-cols-4">
              <div className="rounded-lg border border-line p-2 dark:border-line-dark"><div className="font-semibold text-ink dark:text-ink-dark">{state.data.total_duration_ms} ms</div><div className="text-muted dark:text-muted-dark">Total Duration</div></div>
              <div className="rounded-lg border border-line p-2 dark:border-line-dark"><div className="font-semibold text-ink dark:text-ink-dark">{state.data.bottleneck_label || '—'}</div><div className="text-muted dark:text-muted-dark">Bottleneck</div></div>
              <div className="rounded-lg border border-line p-2 dark:border-line-dark"><div className="font-semibold text-ink dark:text-ink-dark">{state.data.total_tokens ?? '—'}</div><div className="text-muted dark:text-muted-dark">Total Tokens</div></div>
              <div className="rounded-lg border border-line p-2 dark:border-line-dark"><div className="font-semibold text-ink dark:text-ink-dark">{state.data.retry_count}</div><div className="text-muted dark:text-muted-dark">Retries</div></div>
            </div>

            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted dark:text-muted-dark">Provider</p>
              <p className="text-sm text-ink dark:text-ink-dark">
                {state.data.provider || '—'} / {state.data.model || '—'}
                {state.data.providers_attempted?.length > 1 && <span className="ml-2 text-xs text-warning">fell back across {state.data.providers_attempted.join(' → ')}</span>}
              </p>
            </div>

            {state.data.error_type && (
              <div className="rounded-lg border border-dashed border-danger/30 bg-danger/5 p-3 dark:border-danger-dark/30 dark:bg-danger/10">
                <p className="text-xs font-semibold text-danger dark:text-danger-dark">{state.data.error_type}</p>
                <p className="mt-0.5 text-xs text-muted dark:text-muted-dark">{state.data.error_message}</p>
              </div>
            )}

            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted dark:text-muted-dark">Stage Timeline</p>
              <p className="mb-1.5 text-[11px] text-muted dark:text-muted-dark">
                <TriangleAlert className="inline h-3 w-3 text-warning" /> marks the bottleneck stage ({state.data.bottleneck_label || '—'}); <RotateCw className="inline h-3 w-3 text-muted dark:text-muted-dark" /> marks a stage that retried or fell back across providers.
              </p>
              <div className="space-y-1">
                {state.data.stages?.length > 0 ? state.data.stages.map((stage, idx) => (
                  <div key={idx} className={`flex items-center justify-between rounded-lg border px-3 py-2 text-xs ${stage.tags?.includes('bottleneck') ? 'border-warning/30 bg-warning/5 dark:border-warning-dark/30' : 'border-line dark:border-line-dark'}`}>
                    <span className="flex items-center gap-1.5 text-ink dark:text-ink-dark">
                      {stage.tags?.includes('bottleneck') ? <TriangleAlert className="h-3.5 w-3.5 shrink-0 text-warning" /> : <ShieldCheck className="h-3.5 w-3.5 shrink-0 text-success dark:text-success-dark" />}
                      {stage.tags?.includes('retry') && <RotateCw className="h-3.5 w-3.5 shrink-0 text-muted dark:text-muted-dark" title="retried / fell back" />}
                      <span>{stage.name}</span>
                    </span>
                    <span className="font-mono text-muted dark:text-muted-dark">{stage.duration_ms} ms</span>
                  </div>
                )) : <p className="text-xs text-muted dark:text-muted-dark">No stage data recorded for this request.</p>}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function ErrorDetailModal({ groupId, onClose, onOpenTrace }) {
  const [state, setState] = useState({ loading: true, data: null });
  useEffect(() => { fetchAdminErrorGroupDetail(groupId).then((data) => setState({ loading: false, data })); }, [groupId]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-line bg-card p-6 shadow-2xl dark:border-line-dark dark:bg-card-dark">
        {state.loading ? <p className="text-sm text-muted dark:text-muted-dark">Loading…</p> : state.data && (
          <div className="space-y-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-xs font-medium uppercase tracking-wide text-muted dark:text-muted-dark">{state.data.level} · <span className="font-mono">{state.data.logger_name}</span></p>
                <p className="text-xs text-muted dark:text-muted-dark">First seen {state.data.first_seen} · last seen {state.data.last_seen}</p>
              </div>
              <button type="button" onClick={onClose} className="flex h-8 w-8 items-center justify-center rounded-lg text-muted hover:bg-surface dark:text-muted-dark dark:hover:bg-white/5"><X className="h-4 w-4" /></button>
            </div>

            <div className="grid grid-cols-3 gap-3 text-center text-xs">
              <div className="rounded-lg border border-line p-2 dark:border-line-dark"><div className="font-semibold text-ink dark:text-ink-dark">{state.data.occurrence_count}</div><div className="text-muted dark:text-muted-dark">Occurrences</div></div>
              <div className="rounded-lg border border-line p-2 dark:border-line-dark"><div className="font-semibold text-ink dark:text-ink-dark">{state.data.severity}</div><div className="text-muted dark:text-muted-dark">Severity</div></div>
              <div className="rounded-lg border border-line p-2 dark:border-line-dark"><div className="font-semibold text-ink dark:text-ink-dark">{state.data.error_type || '—'}</div><div className="text-muted dark:text-muted-dark">Exception Type</div></div>
            </div>

            <div className="rounded-lg border border-dashed border-danger/30 bg-danger/5 p-3 dark:border-danger-dark/30 dark:bg-danger/10">
              <p className="whitespace-pre-wrap break-words text-xs text-ink dark:text-ink-dark">{state.data.message}</p>
            </div>

            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted dark:text-muted-dark">Recent Occurrences</p>
              <div className="space-y-1">
                {state.data.occurrences?.length > 0 ? state.data.occurrences.map((occ, idx) => (
                  <div key={idx} className="flex items-center justify-between rounded-lg border border-line px-3 py-2 text-xs dark:border-line-dark">
                    <span className="text-muted dark:text-muted-dark">{occ.timestamp}</span>
                    {occ.trace_exists ? (
                      <button type="button" onClick={() => { onClose(); onOpenTrace(occ.trace_id); }} className="inline-flex items-center gap-1 rounded-lg border border-line px-2 py-1 font-mono text-[11px] text-primary hover:bg-primary/5 dark:border-line-dark">
                        <ExternalLink className="h-3 w-3" /> {occ.trace_id}
                      </button>
                    ) : <span className="font-mono text-[11px] text-muted dark:text-muted-dark">{occ.trace_id || '—'}</span>}
                  </div>
                )) : <p className="text-xs text-muted dark:text-muted-dark">No individual occurrence records kept for this error.</p>}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// Port of templates/admin/system_logs.html - the consolidated Request
// Traces / Error Groups / Activity page.
export default function AdminSystemLogs() {
  const [searchParams, setSearchParams] = useSearchParams();
  const filters = Object.fromEntries(searchParams.entries());
  const { data, isLoading, refetch } = useAdminSystemLogs(filters);
  const cancelRun = useCancelAiTask();
  const [traceId, setTraceId] = useState(null);
  const [errorGroupId, setErrorGroupId] = useState(null);
  const [cancellingId, setCancellingId] = useState(null);

  if (isLoading || !data) return <AppLoader variant="page" />;

  const activeTab = filters.tab || data.default_tab;
  const setTab = (tab) => setSearchParams({ tab });
  const onFilterSubmit = (e) => {
    e.preventDefault();
    const form = new FormData(e.target);
    const next = { tab: activeTab };
    for (const [key, value] of form.entries()) if (value) next[key] = value;
    setSearchParams(next);
  };
  const resetTab = () => setSearchParams({ tab: activeTab });

  const onCancelRun = async (runId) => {
    if (!window.confirm('Stop this AI Task run? Results already produced are kept.')) return;
    setCancellingId(runId);
    try {
      await cancelRun.mutateAsync(runId);
      refetch();
    } catch (err) {
      window.alert(err.data?.error || err.message || 'Could not stop this run.');
    } finally {
      setCancellingId(null);
    }
  };

  return (
    <>
      <PageHeader title="System Logs" subtitle="Every AI request trace, deduped application error, and workspace activity event — one page, one nav entry." />

      {data.can_view_traces && (
        <div className="mb-4 grid grid-cols-2 gap-2.5 sm:grid-cols-4">
          <StatCard icon={Activity} label="Total Requests" value={data.summary.total} numeric />
          <StatCard icon={Terminal} label="Ask AI" value={data.summary.ask_ai} numeric />
          <StatCard icon={Sparkles} label="AI Tasks" value={data.summary.ai_task} numeric />
          <StatCard icon={TriangleAlert} label="Failed" value={data.summary.failed} numeric />
        </div>
      )}

      {(data.can_view_traces && data.can_view_activity) && (
        <div className="mb-3 flex w-fit gap-1 rounded-xl border border-line bg-card p-1 shadow-soft dark:border-line-dark dark:bg-card-dark">
          <button type="button" onClick={() => setTab('traces')} className={`rounded-lg px-3.5 py-1.5 text-sm font-medium transition-colors ${activeTab === 'traces' ? 'bg-primary text-white' : 'text-muted hover:text-ink dark:text-muted-dark dark:hover:text-ink-dark'}`}>Request Traces</button>
          <button type="button" onClick={() => setTab('errors')} className={`rounded-lg px-3.5 py-1.5 text-sm font-medium transition-colors ${activeTab === 'errors' ? 'bg-primary text-white' : 'text-muted hover:text-ink dark:text-muted-dark dark:hover:text-ink-dark'}`}>
            Error Groups {data.eg_total > 0 && <span className="ml-1 rounded-full bg-danger/10 px-1.5 py-0.5 text-[10px] font-semibold text-danger dark:text-danger-dark">{data.eg_total}</span>}
          </button>
          <button type="button" onClick={() => setTab('activity')} className={`rounded-lg px-3.5 py-1.5 text-sm font-medium transition-colors ${activeTab === 'activity' ? 'bg-primary text-white' : 'text-muted hover:text-ink dark:text-muted-dark dark:hover:text-ink-dark'}`}>Activity</button>
        </div>
      )}
      {(data.can_view_traces && !data.can_view_activity) && (
        <div className="mb-3 flex w-fit gap-1 rounded-xl border border-line bg-card p-1 shadow-soft dark:border-line-dark dark:bg-card-dark">
          <button type="button" onClick={() => setTab('traces')} className={`rounded-lg px-3.5 py-1.5 text-sm font-medium transition-colors ${activeTab === 'traces' ? 'bg-primary text-white' : 'text-muted hover:text-ink dark:text-muted-dark dark:hover:text-ink-dark'}`}>Request Traces</button>
          <button type="button" onClick={() => setTab('errors')} className={`rounded-lg px-3.5 py-1.5 text-sm font-medium transition-colors ${activeTab === 'errors' ? 'bg-primary text-white' : 'text-muted hover:text-ink dark:text-muted-dark dark:hover:text-ink-dark'}`}>
            Error Groups {data.eg_total > 0 && <span className="ml-1 rounded-full bg-danger/10 px-1.5 py-0.5 text-[10px] font-semibold text-danger dark:text-danger-dark">{data.eg_total}</span>}
          </button>
        </div>
      )}

      {data.can_view_traces && activeTab === 'traces' && (
        <div>
          {data.active_ai_task_runs?.length > 0 && (
            <div className="mb-3 overflow-hidden rounded-2xl border border-warning/30 bg-warning/5 shadow-soft dark:border-warning-dark/30 dark:bg-warning-dark/10">
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-warning/20 px-4 py-3 dark:border-warning-dark/20">
                <h2 className="flex items-center gap-2 text-sm font-semibold text-ink dark:text-ink-dark">
                  <span className="h-2 w-2 animate-pulse rounded-full bg-warning dark:bg-warning-dark"></span>
                  Active AI Task Runs
                  <span className="rounded-full bg-warning/15 px-2 py-0.5 text-xs font-semibold text-warning dark:text-warning-dark">{data.active_ai_task_runs.length}</span>
                </h2>
                <button type="button" onClick={() => refetch()} className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline dark:text-primary-soft"><RotateCw className="h-3 w-3" /> Refresh</button>
              </div>
              <div className="divide-y divide-warning/15 dark:divide-warning-dark/15">
                {data.active_ai_task_runs.map((run) => (
                  <div key={run.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-2.5">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium ${run.status === 'running' ? 'bg-warning/15 text-warning dark:text-warning-dark' : 'bg-line text-muted dark:bg-white/10 dark:text-muted-dark'}`}>{run.status_display}</span>
                        <Link to={`/ai-tasks/${run.id}/results`} className="text-sm font-medium text-ink hover:text-primary dark:text-ink-dark dark:hover:text-primary-soft">{run.task_type_display}</Link>
                        <span className="text-xs text-muted dark:text-muted-dark">{run.username || '—'} · {run.document_count} doc{run.document_count === 1 ? '' : 's'} · {timeAgo(run.created_at)} ago</span>
                      </div>
                      {run.stuck_pending && (
                        <p className="mt-1 flex items-center gap-1.5 text-xs text-warning dark:text-warning-dark">
                          <AlertTriangle className="h-3 w-3 shrink-0" /> This run may have been interrupted by a server restart — stop it and start a new one.
                        </p>
                      )}
                    </div>
                    <button type="button" onClick={() => onCancelRun(run.id)} disabled={cancellingId === run.id} className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-danger/30 bg-danger/5 px-2.5 py-1 text-xs font-medium text-danger transition-colors hover:bg-danger/10 disabled:cursor-not-allowed disabled:opacity-60 dark:border-danger-dark/30 dark:text-danger-dark dark:hover:bg-danger-dark/10">
                      {cancellingId === run.id ? <Spinner size={12} /> : <Square className="h-3 w-3" />} Stop
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          <form onSubmit={(e) => onFilterSubmit(e)} className="mb-3 grid grid-cols-1 gap-2.5 rounded-2xl border border-line bg-card p-3.5 shadow-soft dark:border-line-dark dark:bg-card-dark sm:grid-cols-2 lg:grid-cols-7">
            <div><label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">Source</label>
              <select name="source" defaultValue={filters.source || ''} className="w-full rounded-lg border border-line bg-transparent px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none dark:border-line-dark dark:text-ink-dark">
                <option value="">Any</option><option value="ask_ai">Ask AI</option><option value="ai_task">AI Task</option>
              </select></div>
            <div><label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">Status</label>
              <select name="status" defaultValue={filters.status || ''} className="w-full rounded-lg border border-line bg-transparent px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none dark:border-line-dark dark:text-ink-dark">
                <option value="">Any</option><option value="completed">Completed</option><option value="failed">Failed</option><option value="running">Running</option><option value="cancelled">Cancelled</option>
              </select></div>
            <div><label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">Provider</label>
              <select name="provider" defaultValue={filters.provider || ''} className="w-full rounded-lg border border-line bg-transparent px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none dark:border-line-dark dark:text-ink-dark">
                <option value="">Any</option>{data.filter_options.providers.map((p) => <option key={p} value={p}>{p}</option>)}
              </select></div>
            <div><label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">Model</label>
              <select name="model" defaultValue={filters.model || ''} className="w-full rounded-lg border border-line bg-transparent px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none dark:border-line-dark dark:text-ink-dark">
                <option value="">Any</option>{data.filter_options.models.map((m) => <option key={m} value={m}>{m}</option>)}
              </select></div>
            <div><label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">Error type</label>
              <select name="error_type" defaultValue={filters.error_type || ''} className="w-full rounded-lg border border-line bg-transparent px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none dark:border-line-dark dark:text-ink-dark">
                <option value="">Any</option>{data.filter_options.error_types.map((e) => <option key={e} value={e}>{e}</option>)}
              </select></div>
            <div><label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">From</label><input type="date" name="date_from" defaultValue={filters.date_from} className="w-full rounded-lg border border-line bg-transparent px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none dark:border-line-dark dark:text-ink-dark" /></div>
            <div><label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">To</label><input type="date" name="date_to" defaultValue={filters.date_to} className="w-full rounded-lg border border-line bg-transparent px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none dark:border-line-dark dark:text-ink-dark" /></div>
            <div className="lg:col-span-2"><label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">Request ID</label><input type="text" name="trace_id" defaultValue={filters.trace_id} placeholder="e.g. 2f986667" className="w-full rounded-lg border border-line bg-transparent px-3 py-2 text-sm text-ink placeholder:text-muted focus:border-primary focus:outline-none dark:border-line-dark dark:text-ink-dark" /></div>
            <div className="flex items-end gap-2 lg:col-span-2">
              <button type="submit" className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-primary-dark"><Filter className="h-4 w-4" /> Apply</button>
              <button type="button" onClick={resetTab} className="inline-flex items-center gap-2 rounded-lg border border-line px-4 py-2 text-sm font-medium text-ink transition-colors hover:bg-surface dark:border-line-dark dark:text-ink-dark dark:hover:bg-white/5">Reset</button>
            </div>
          </form>

          <div className="rounded-2xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">
            {data.traces.length > 0 ? (
              <>
                <div className="overflow-auto">
                  <table className="w-full min-w-[960px] text-left text-sm">
                    <thead className="sticky top-0 z-10 bg-card dark:bg-card-dark">
                      <tr className="border-b border-line text-xs font-semibold uppercase tracking-wide text-muted dark:border-line-dark dark:text-muted-dark">
                        <th className="px-4 py-2.5">Request ID</th><th className="px-3 py-2.5">Source</th><th className="px-3 py-2.5">User</th><th className="px-3 py-2.5">Status</th>
                        <th className="px-3 py-2.5">Provider / Model</th><th className="px-3 py-2.5 text-right">Duration</th><th className="px-3 py-2.5">Bottleneck</th>
                        <th className="px-3 py-2.5 text-right">Tokens</th><th className="px-3 py-2.5">When</th><th className="px-4 py-2.5 text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-line dark:divide-line-dark">
                      {data.traces.map((trace) => (
                        <tr key={trace.trace_id} className="transition-colors hover:bg-surface dark:hover:bg-white/5">
                          <td className="px-4 py-2 font-mono text-xs text-ink dark:text-ink-dark">{trace.trace_id}</td>
                          <td className="px-3 py-2 text-muted dark:text-muted-dark">{trace.source_display}</td>
                          <td className="px-3 py-2 text-muted dark:text-muted-dark">{trace.user || '—'}</td>
                          <td className="px-3 py-2"><span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ${STATUS_CLASSES[trace.status] || 'bg-warning/10 text-warning dark:text-warning-dark'}`}>{trace.status_display}</span></td>
                          <td className="px-3 py-2 text-muted dark:text-muted-dark">
                            {trace.provider || '—'}
                            {trace.providers_attempted?.length > 1 && <span className="ml-1 rounded-full bg-warning/10 px-1.5 py-0.5 text-[10px] font-semibold text-warning" title={`Fell back across ${trace.providers_attempted.join(' → ')}`}>fallback</span>}
                            <div className="text-xs">{trace.model || ''}</div>
                          </td>
                          <td className="px-3 py-2 text-right text-muted dark:text-muted-dark">{trace.total_duration_ms} ms</td>
                          <td className="px-3 py-2 text-muted dark:text-muted-dark">{trace.bottleneck_label || '—'}</td>
                          <td className="px-3 py-2 text-right text-muted dark:text-muted-dark">{trace.total_tokens ?? '—'}</td>
                          <td className="px-3 py-2 text-muted dark:text-muted-dark">{timeAgo(trace.created_at)} ago</td>
                          <td className="px-4 py-2 text-right">
                            <button type="button" onClick={() => setTraceId(trace.trace_id)} className="inline-flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1.5 text-xs font-medium text-ink transition-colors hover:border-primary/30 hover:bg-primary/5 hover:text-primary dark:border-line-dark dark:text-ink-dark dark:hover:bg-primary/10">
                              <Eye className="h-3.5 w-3.5" /> View
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {data.num_pages > 1 && (
                  <div className="flex items-center justify-between border-t border-line px-4 py-2.5 dark:border-line-dark">
                    <p className="text-xs text-muted dark:text-muted-dark">Page {data.page} of {data.num_pages} · {data.total} total</p>
                    <div className="flex gap-2">
                      {data.page > 1 && <button onClick={() => setSearchParams({ ...filters, tab: 'traces', page: String(data.page - 1) })} className="rounded-lg border border-line px-3 py-1.5 text-xs font-medium text-ink hover:bg-surface dark:border-line-dark dark:text-ink-dark dark:hover:bg-white/5">Previous</button>}
                      {data.page < data.num_pages && <button onClick={() => setSearchParams({ ...filters, tab: 'traces', page: String(data.page + 1) })} className="rounded-lg border border-line px-3 py-1.5 text-xs font-medium text-ink hover:bg-surface dark:border-line-dark dark:text-ink-dark dark:hover:bg-white/5">Next</button>}
                    </div>
                  </div>
                )}
              </>
            ) : <EmptyState icon={Terminal} title="No AI requests match these filters" />}
          </div>
        </div>
      )}

      {data.can_view_traces && activeTab === 'errors' && (
        <div>
          <form onSubmit={(e) => onFilterSubmit(e)} className="mb-3 grid grid-cols-1 gap-2.5 rounded-2xl border border-line bg-card p-3.5 shadow-soft dark:border-line-dark dark:bg-card-dark sm:grid-cols-2 lg:grid-cols-6">
            <div><label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">Module</label><input type="text" name="eg_logger" defaultValue={filters.eg_logger} placeholder="e.g. RAG.services.health_service" className="w-full rounded-lg border border-line bg-transparent px-3 py-2 text-sm text-ink placeholder:text-muted focus:border-primary focus:outline-none dark:border-line-dark dark:text-ink-dark" /></div>
            <div><label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">Level</label>
              <select name="eg_level" defaultValue={filters.eg_level || ''} className="w-full rounded-lg border border-line bg-transparent px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none dark:border-line-dark dark:text-ink-dark">
                <option value="">Any</option><option value="WARNING">Warning</option><option value="ERROR">Error</option><option value="CRITICAL">Critical</option>
              </select></div>
            <div className="sm:col-span-2"><label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">Message contains</label><input type="text" name="eg_q" defaultValue={filters.eg_q} placeholder="e.g. connection refused" className="w-full rounded-lg border border-line bg-transparent px-3 py-2 text-sm text-ink placeholder:text-muted focus:border-primary focus:outline-none dark:border-line-dark dark:text-ink-dark" /></div>
            <div><label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">From</label><input type="date" name="eg_date_from" defaultValue={filters.eg_date_from} className="w-full rounded-lg border border-line bg-transparent px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none dark:border-line-dark dark:text-ink-dark" /></div>
            <div><label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">To</label><input type="date" name="eg_date_to" defaultValue={filters.eg_date_to} className="w-full rounded-lg border border-line bg-transparent px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none dark:border-line-dark dark:text-ink-dark" /></div>
            <div className="flex items-end gap-2 sm:col-span-2 lg:col-span-6">
              <button type="submit" className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-primary-dark"><Filter className="h-4 w-4" /> Apply</button>
              <button type="button" onClick={resetTab} className="inline-flex items-center gap-2 rounded-lg border border-line px-4 py-2 text-sm font-medium text-ink transition-colors hover:bg-surface dark:border-line-dark dark:text-ink-dark dark:hover:bg-white/5">Reset</button>
            </div>
          </form>

          <div className="rounded-2xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">
            {data.error_groups.length > 0 ? (
              <>
                <div className="overflow-auto">
                  <table className="w-full min-w-[860px] text-left text-sm">
                    <thead className="sticky top-0 z-10 bg-card dark:bg-card-dark">
                      <tr className="border-b border-line text-xs font-semibold uppercase tracking-wide text-muted dark:border-line-dark dark:text-muted-dark">
                        <th className="px-4 py-2.5">Module</th><th className="px-3 py-2.5">Level</th><th className="px-3 py-2.5">Severity</th><th className="px-3 py-2.5">Message</th>
                        <th className="px-3 py-2.5 text-right">Occurrences</th><th className="px-3 py-2.5">First Seen</th><th className="px-3 py-2.5">Last Seen</th><th className="px-4 py-2.5 text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-line dark:divide-line-dark">
                      {data.error_groups.map((group) => (
                        <tr key={group.id} className="transition-colors hover:bg-surface dark:hover:bg-white/5">
                          <td className="px-4 py-2 font-mono text-xs text-ink dark:text-ink-dark" title={group.logger_name}>{group.logger_name.length > 40 ? `${group.logger_name.slice(0, 40)}…` : group.logger_name}</td>
                          <td className="px-3 py-2"><span className="inline-flex items-center gap-1 rounded-full bg-danger/10 px-2 py-0.5 text-xs font-semibold text-danger dark:text-danger-dark">{group.level}</span></td>
                          <td className="px-3 py-2"><span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ${group.severity === 'critical' ? 'bg-danger/10 text-danger dark:text-danger-dark' : group.severity === 'high' ? 'bg-warning/10 text-warning dark:text-warning-dark' : 'bg-muted/10 text-muted dark:text-muted-dark'}`}>{group.severity}</span></td>
                          <td className="px-3 py-2 text-muted dark:text-muted-dark" title={group.message}>{group.message.length > 60 ? `${group.message.slice(0, 60)}…` : group.message}</td>
                          <td className="px-3 py-2 text-right text-muted dark:text-muted-dark">×{group.occurrence_count}</td>
                          <td className="px-3 py-2 text-muted dark:text-muted-dark">{timeAgo(group.first_seen)} ago</td>
                          <td className="px-3 py-2 text-muted dark:text-muted-dark">{timeAgo(group.last_seen)} ago</td>
                          <td className="px-4 py-2 text-right">
                            <button type="button" onClick={() => setErrorGroupId(group.id)} className="inline-flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1.5 text-xs font-medium text-ink transition-colors hover:border-primary/30 hover:bg-primary/5 hover:text-primary dark:border-line-dark dark:text-ink-dark dark:hover:bg-primary/10">
                              <Eye className="h-3.5 w-3.5" /> View
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {data.eg_num_pages > 1 && (
                  <div className="flex items-center justify-between border-t border-line px-4 py-2.5 dark:border-line-dark">
                    <p className="text-xs text-muted dark:text-muted-dark">Page {data.eg_page} of {data.eg_num_pages} · {data.eg_total} total</p>
                    <div className="flex gap-2">
                      {data.eg_page > 1 && <button onClick={() => setSearchParams({ ...filters, tab: 'errors', eg_page: String(data.eg_page - 1) })} className="rounded-lg border border-line px-3 py-1.5 text-xs font-medium text-ink hover:bg-surface dark:border-line-dark dark:text-ink-dark dark:hover:bg-white/5">Previous</button>}
                      {data.eg_page < data.eg_num_pages && <button onClick={() => setSearchParams({ ...filters, tab: 'errors', eg_page: String(data.eg_page + 1) })} className="rounded-lg border border-line px-3 py-1.5 text-xs font-medium text-ink hover:bg-surface dark:border-line-dark dark:text-ink-dark dark:hover:bg-white/5">Next</button>}
                    </div>
                  </div>
                )}
              </>
            ) : <EmptyState icon={ShieldCheck} title="No errors captured" message="Every logger.warning()/error()/exception() call app-wide flows here automatically - nothing recent matches these filters." />}
          </div>
        </div>
      )}

      {data.can_view_activity && activeTab === 'activity' && (
        <div>
          <div className={`mb-3 grid grid-cols-2 gap-2.5 ${data.can_view_activity_location ? 'sm:grid-cols-4' : 'sm:grid-cols-2'}`}>
            <StatCard icon={Activity} label="Total Events" value={data.act_summary.total_events} numeric />
            {data.can_view_activity_location && (
              <>
                <StatCard icon={Globe} label="Tracked IPs" value={data.act_summary.tracked_ips} numeric />
                <StatCard icon={MapPin} label="Countries" value={data.act_summary.countries} numeric />
              </>
            )}
            <StatCard icon={ShieldAlert} label="Security Alerts" value={data.act_summary.security_alerts} numeric />
          </div>

          {!data.can_view_activity_location && (
            <div className="mb-3 flex items-center gap-2 rounded-xl border border-line bg-card px-3.5 py-2.5 text-xs text-muted shadow-soft dark:border-line-dark dark:bg-card-dark dark:text-muted-dark">
              <Lock className="h-3.5 w-3.5 shrink-0" /> IP address and location are hidden - your role doesn't hold the "View IP & location data" permission.
            </div>
          )}

          <form onSubmit={(e) => onFilterSubmit(e)} className="mb-3 grid grid-cols-1 gap-2.5 rounded-2xl border border-line bg-card p-3.5 shadow-soft dark:border-line-dark dark:bg-card-dark sm:grid-cols-2 lg:grid-cols-6">
            <div><label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">Event type</label>
              <select name="act_type" defaultValue={filters.act_type || ''} className="w-full rounded-lg border border-line bg-transparent px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none dark:border-line-dark dark:text-ink-dark">
                <option value="">Any</option>{data.activity_types.map((t) => <option key={t} value={t}>{t}</option>)}
              </select></div>
            <div><label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">Actor</label><input type="text" name="act_actor" defaultValue={filters.act_actor} placeholder="username" className="w-full rounded-lg border border-line bg-transparent px-3 py-2 text-sm text-ink placeholder:text-muted focus:border-primary focus:outline-none dark:border-line-dark dark:text-ink-dark" /></div>
            <div><label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">Description contains</label><input type="text" name="act_q" defaultValue={filters.act_q} placeholder="e.g. deleted" className="w-full rounded-lg border border-line bg-transparent px-3 py-2 text-sm text-ink placeholder:text-muted focus:border-primary focus:outline-none dark:border-line-dark dark:text-ink-dark" /></div>
            {data.can_view_activity_location && (
              <div><label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">IP / Location</label><input type="text" name="act_location" defaultValue={filters.act_location} placeholder="IP, city, country…" className="w-full rounded-lg border border-line bg-transparent px-3 py-2 text-sm text-ink placeholder:text-muted focus:border-primary focus:outline-none dark:border-line-dark dark:text-ink-dark" /></div>
            )}
            <div><label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">From</label><input type="date" name="act_date_from" defaultValue={filters.act_date_from} className="w-full rounded-lg border border-line bg-transparent px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none dark:border-line-dark dark:text-ink-dark" /></div>
            <div><label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">To</label><input type="date" name="act_date_to" defaultValue={filters.act_date_to} className="w-full rounded-lg border border-line bg-transparent px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none dark:border-line-dark dark:text-ink-dark" /></div>
            <div className="flex items-end gap-2 sm:col-span-2 lg:col-span-6">
              <button type="submit" className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-primary-dark"><Filter className="h-4 w-4" /> Apply</button>
              <button type="button" onClick={resetTab} className="inline-flex items-center gap-2 rounded-lg border border-line px-4 py-2 text-sm font-medium text-ink transition-colors hover:bg-surface dark:border-line-dark dark:text-ink-dark dark:hover:bg-white/5">Reset</button>
            </div>
          </form>

          <div className="rounded-2xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">
            {data.activity_results.length > 0 ? (
              <>
                <div className="overflow-auto">
                  <table className={`w-full text-left text-sm ${data.can_view_activity_location ? 'min-w-[860px]' : 'min-w-[640px]'}`}>
                    <thead className="sticky top-0 z-10 bg-card dark:bg-card-dark">
                      <tr className="border-b border-line text-xs font-semibold uppercase tracking-wide text-muted dark:border-line-dark dark:text-muted-dark">
                        <th className="px-4 py-2.5">Event</th><th className="px-3 py-2.5">Type</th><th className="px-3 py-2.5">Actor</th>
                        {data.can_view_activity_location && <th className="px-3 py-2.5">IP / Location</th>}
                        <th className="px-4 py-2.5 text-right">When</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-line dark:divide-line-dark">
                      {data.activity_results.map((event, idx) => (
                        <tr key={idx} className="transition-colors hover:bg-surface dark:hover:bg-white/5">
                          <td className="px-4 py-2">
                            <span className="flex items-center gap-2 text-ink dark:text-ink-dark">
                              <span className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full ${CATEGORY_CLASSES[event.category] || 'bg-primary/10 text-primary dark:text-primary-soft'}`}>
                                {event.icon === 'file-up' ? <FileUp className="h-3.5 w-3.5" /> : <Activity className="h-3.5 w-3.5" />}
                              </span>
                              {event.text}
                            </span>
                          </td>
                          <td className="px-3 py-2"><span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${CATEGORY_CLASSES[event.category] || 'bg-muted/10 text-muted dark:text-muted-dark'}`}>{event.type}</span></td>
                          <td className="px-3 py-2 text-muted dark:text-muted-dark">{event.actor}</td>
                          {data.can_view_activity_location && (
                            <td className="px-3 py-2">
                              {event.ip_address ? (
                                <div className="flex flex-col leading-tight">
                                  <span className="font-mono text-xs text-ink dark:text-ink-dark">{event.ip_address}</span>
                                  {event.location ? (
                                    <span className="flex items-center gap-1 text-xs text-muted dark:text-muted-dark"><MapPin className="h-3 w-3 shrink-0" /> {event.location}</span>
                                  ) : <span className="text-xs text-muted dark:text-muted-dark">Location unknown</span>}
                                </div>
                              ) : <span className="text-xs text-muted dark:text-muted-dark">—</span>}
                            </td>
                          )}
                          <td className="px-4 py-2 text-right text-muted dark:text-muted-dark">{timeAgo(event.at)} ago</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {data.act_num_pages > 1 && (
                  <div className="flex items-center justify-between border-t border-line px-4 py-2.5 dark:border-line-dark">
                    <p className="text-xs text-muted dark:text-muted-dark">Page {data.act_page} of {data.act_num_pages} · {data.act_total} total</p>
                    <div className="flex gap-2">
                      {data.act_has_previous && <button onClick={() => setSearchParams({ ...filters, tab: 'activity', act_page: String(data.act_page - 1) })} className="rounded-lg border border-line px-3 py-1.5 text-xs font-medium text-ink hover:bg-surface dark:border-line-dark dark:text-ink-dark dark:hover:bg-white/5">Previous</button>}
                      {data.act_has_next && <button onClick={() => setSearchParams({ ...filters, tab: 'activity', act_page: String(data.act_page + 1) })} className="rounded-lg border border-line px-3 py-1.5 text-xs font-medium text-ink hover:bg-surface dark:border-line-dark dark:text-ink-dark dark:hover:bg-white/5">Next</button>}
                    </div>
                  </div>
                )}
              </>
            ) : <EmptyState title="No activity matches these filters" />}
          </div>
        </div>
      )}

      {traceId && <TraceDetailModal traceId={traceId} onClose={() => setTraceId(null)} onOpenTrace={setTraceId} />}
      {errorGroupId && <ErrorDetailModal groupId={errorGroupId} onClose={() => setErrorGroupId(null)} onOpenTrace={setTraceId} />}
    </>
  );
}
