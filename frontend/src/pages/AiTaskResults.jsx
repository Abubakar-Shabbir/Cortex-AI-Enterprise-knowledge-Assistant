import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  AlertTriangle, Check, Download, OctagonX, Plus, Sparkles, Square, Trash2, X, XCircle,
} from 'lucide-react';
import AppLoader from '../components/AppLoader';
import EmptyState from '../components/EmptyState';
import Spinner from '../components/Spinner';
import ResultRow from '../components/ai_tasks/ResultRow';
import { getApiBaseUrl } from '../api/client';
import { timeAgo } from '../lib/timeAgo';
import { useAiTaskResults, useAiTaskStatus, useCancelAiTask, useDeleteAiTask } from '../api/hooks';

const STATUS_LABELS = { pending: 'Pending', running: 'Running', completed: 'Completed', failed: 'Failed', cancelled: 'Cancelled' };
const STATUS_BADGE_CLASSES = {
  completed: 'bg-success/10 text-success dark:text-success-dark',
  failed: 'bg-danger/10 text-danger dark:text-danger-dark',
  cancelled: 'bg-line text-muted dark:bg-white/10 dark:text-muted-dark',
  running: 'bg-warning/10 text-warning dark:text-warning-dark',
  pending: 'bg-line text-muted dark:bg-white/10 dark:text-muted-dark',
};

// Port of templates/ai_tasks/wizard.html's run branch (steps 5-6:
// live pipeline stepper, polling while pending/running, results).
export default function AiTaskResults() {
  const { runId } = useParams();
  const navigate = useNavigate();
  const { data, isLoading, refetch } = useAiTaskResults(runId);
  const status = useAiTaskStatus(runId);
  const cancelRun = useCancelAiTask();
  const deleteRun = useDeleteAiTask();

  const [stopError, setStopError] = useState('');
  const [deleteError, setDeleteError] = useState('');
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  const lastTerminalStatusRef = useRef(null);

  // Once the run has gone terminal (polling stops itself via
  // useAiTaskStatus's refetchInterval callback), pull the finished
  // results if they haven't been fetched under this terminal status yet.
  useEffect(() => {
    const polledStatus = status.data?.status;
    if (!polledStatus || polledStatus === 'pending' || polledStatus === 'running') return;
    if (lastTerminalStatusRef.current === polledStatus) return;
    lastTerminalStatusRef.current = polledStatus;
    if (data && data.run.status !== polledStatus) refetch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status.data?.status]);

  if (isLoading || !data) return <AppLoader variant="page" />;

  const run = { ...data.run, ...(status.data || {}) };
  const isActive = run.status === 'pending' || run.status === 'running';
  const isTerminal = !isActive;
  const canStop = isActive && !run.cancel_requested;
  const resultCount = status.data?.result_count ?? data.result_count;
  const progressPercent = run.document_count ? Math.min(100, Math.round((resultCount / run.document_count) * 100)) : 0;
  const statusLabel = run.cancel_requested && isActive ? 'Stopping…' : (STATUS_LABELS[run.status] || run.status);
  const statusBadgeClass = run.cancel_requested && isActive ? 'bg-danger/10 text-danger dark:text-danger-dark' : (STATUS_BADGE_CLASSES[run.status] || STATUS_BADGE_CLASSES.pending);

  const stage1Class = run.status === 'pending'
    ? 'border-warning bg-warning/10 text-warning dark:border-warning-dark dark:text-warning-dark'
    : 'border-success bg-success/10 text-success dark:border-success-dark dark:text-success-dark';
  const stage2Class = run.status === 'pending'
    ? 'border-line text-muted dark:border-line-dark dark:text-muted-dark'
    : run.status === 'running'
      ? 'border-warning bg-warning/10 text-warning dark:border-warning-dark dark:text-warning-dark'
      : 'border-success bg-success/10 text-success dark:border-success-dark dark:text-success-dark';
  const stage3Class = !isTerminal
    ? 'border-line text-muted dark:border-line-dark dark:text-muted-dark'
    : run.status === 'completed'
      ? 'border-success bg-success/10 text-success dark:border-success-dark dark:text-success-dark'
      : 'border-danger bg-danger/10 text-danger dark:border-danger-dark dark:text-danger-dark';
  const stage3BarClass = run.status === 'completed' ? 'bg-success dark:bg-success-dark' : 'bg-danger dark:bg-danger-dark';
  const stage3Label = { completed: 'Done', failed: 'Failed', cancelled: 'Cancelled' }[run.status] || 'Done';

  const onStop = async () => {
    if (cancelRun.isPending || run.cancel_requested) return;
    setStopError('');
    try {
      await cancelRun.mutateAsync(runId);
      status.refetch();
    } catch (err) {
      setStopError(err.data?.error || err.message || 'Could not stop this run.');
    }
  };

  const onDelete = async () => {
    if (deleteRun.isPending || isActive) return;
    setDeleteError('');
    try {
      await deleteRun.mutateAsync(runId);
      navigate('/ai-tasks/history');
    } catch (err) {
      setDeleteError(err.data?.error || err.message || 'Could not delete this run.');
    }
  };

  const exportUrl = `${getApiBaseUrl()}/api/ai-tasks/${runId}/export.csv`;

  return (
    <>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-ink dark:text-ink-dark">{run.task_type_display}</h1>
          <p className="mt-1 text-sm text-muted dark:text-muted-dark">Started {timeAgo(run.created_at)} ago</p>
        </div>
      </div>

      <div className="mb-6 overflow-hidden rounded-xl border border-line bg-card p-5 shadow-soft dark:border-line-dark dark:bg-card-dark">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-3">
            <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-semibold ${statusBadgeClass}`}>
              {isActive && <span className="h-2 w-2 animate-pulse rounded-full bg-current"></span>}
              {run.status === 'completed' && <Check className="h-3.5 w-3.5" />}
              {run.status === 'failed' && <XCircle className="h-3.5 w-3.5" />}
              {run.status === 'cancelled' && <OctagonX className="h-3.5 w-3.5" />}
              <span>{statusLabel}</span>
            </span>
            <span className="text-sm text-muted dark:text-muted-dark">{resultCount} of {run.document_count} document{run.document_count === 1 ? '' : 's'} processed</span>
          </div>

          <div className="flex items-center gap-2">
            {canStop && (
              <button type="button" onClick={onStop} disabled={cancelRun.isPending} className="inline-flex items-center gap-1.5 rounded-lg border border-danger/30 bg-danger/5 px-3 py-1.5 text-sm font-medium text-danger transition-colors hover:bg-danger/10 disabled:cursor-not-allowed disabled:opacity-60 dark:border-danger-dark/30 dark:text-danger-dark dark:hover:bg-danger-dark/10">
                {cancelRun.isPending ? <Spinner size={14} /> : <Square className="h-3.5 w-3.5" />}
                <span>{cancelRun.isPending ? 'Stopping…' : 'Stop'}</span>
              </button>
            )}
            <a href={exportUrl} className="inline-flex items-center gap-2 rounded-lg border border-line px-3.5 py-2 text-sm font-medium text-ink transition-colors hover:border-primary/30 hover:bg-primary/5 hover:text-primary dark:border-line-dark dark:text-ink-dark dark:hover:bg-primary/10">
              <Download className="h-4 w-4" /> Export CSV
            </a>
            {!isActive && (
              confirmingDelete ? (
                <div className="flex items-center gap-1.5">
                  <span className="text-xs text-muted dark:text-muted-dark">Delete this run and its results?</span>
                  <button type="button" onClick={onDelete} disabled={deleteRun.isPending} className="inline-flex items-center gap-1.5 rounded-lg border border-danger/30 bg-danger/5 px-3 py-1.5 text-xs font-medium text-danger transition-colors hover:bg-danger/10 disabled:opacity-60 dark:border-danger-dark/30 dark:text-danger-dark">
                    {deleteRun.isPending ? <Spinner size={14} /> : <Trash2 className="h-3.5 w-3.5" />} Confirm
                  </button>
                  <button type="button" onClick={() => setConfirmingDelete(false)} className="rounded-lg border border-line px-2 py-1.5 text-xs font-medium text-ink hover:bg-surface dark:border-line-dark dark:text-ink-dark dark:hover:bg-white/5"><X className="h-3.5 w-3.5" /></button>
                </div>
              ) : (
                <button type="button" onClick={() => setConfirmingDelete(true)} className="inline-flex items-center gap-1.5 rounded-lg border border-danger/30 bg-danger/5 px-3.5 py-2 text-sm font-medium text-danger transition-colors hover:bg-danger/10 dark:border-danger-dark/30 dark:text-danger-dark dark:hover:bg-danger-dark/10">
                  <Trash2 className="h-4 w-4" /> Delete
                </button>
              )
            )}
            <Link to="/ai-tasks" className="inline-flex items-center gap-2 rounded-lg bg-primary px-3.5 py-2 text-sm font-semibold text-white transition-colors hover:bg-primary-dark">
              <Plus className="h-4 w-4" /> New AI Task
            </Link>
          </div>
        </div>

        {stopError && <p className="mt-3 text-xs font-medium text-danger dark:text-danger-dark">{stopError}</p>}
        {deleteError && <p className="mt-3 text-xs font-medium text-danger dark:text-danger-dark">{deleteError}</p>}

        <div className="mt-5 flex items-center">
          <div className="flex flex-col items-center gap-1.5">
            <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full border-2 transition-colors duration-300 ${stage1Class}`}>
              {run.status === 'pending' ? <Spinner size={16} /> : <Check className="h-4 w-4" />}
            </div>
            <span className="text-[11px] font-medium text-ink dark:text-ink-dark">Queued</span>
          </div>

          <div className="mx-2 h-0.5 flex-1 rounded-full bg-line dark:bg-line-dark">
            <div className="h-full rounded-full bg-primary transition-all duration-500" style={{ width: run.status === 'pending' ? '0%' : '100%' }}></div>
          </div>

          <div className="flex flex-col items-center gap-1.5">
            <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full border-2 transition-colors duration-300 ${stage2Class}`}>
              {isTerminal ? <Check className="h-4 w-4" /> : run.status === 'running' ? <Spinner size={16} /> : <span className="text-xs font-semibold">2</span>}
            </div>
            <span className={`text-[11px] font-medium ${run.status === 'pending' ? 'text-muted dark:text-muted-dark' : 'text-ink dark:text-ink-dark'}`}>Processing</span>
          </div>

          <div className="mx-2 h-0.5 flex-1 rounded-full bg-line dark:bg-line-dark">
            <div className={`h-full rounded-full transition-all duration-500 ${isTerminal ? stage3BarClass : 'bg-line dark:bg-line-dark'}`} style={{ width: isTerminal ? '100%' : '0%' }}></div>
          </div>

          <div className="flex flex-col items-center gap-1.5">
            <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full border-2 transition-colors duration-300 ${stage3Class}`}>
              {run.status === 'completed' ? <Check className="h-4 w-4" /> : (run.status === 'failed' || run.status === 'cancelled') ? <X className="h-4 w-4" /> : <span className="text-xs font-semibold">3</span>}
            </div>
            <span className={`text-[11px] font-medium ${isTerminal ? 'text-ink dark:text-ink-dark' : 'text-muted dark:text-muted-dark'}`}>{stage3Label}</span>
          </div>
        </div>

        {run.status === 'running' && (
          <div className="mt-5">
            <div className="mb-1 flex items-center justify-between text-xs text-muted dark:text-muted-dark">
              <span>Generating results</span>
              <span>{progressPercent}%</span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-line dark:bg-line-dark">
              <div className="h-full rounded-full bg-gradient-to-r from-primary to-accent transition-all duration-700 ease-out" style={{ width: `${progressPercent}%` }}></div>
            </div>
          </div>
        )}
      </div>

      {run.error_message && (
        <div className="mb-6 flex items-start gap-2.5 rounded-lg border border-warning/20 bg-warning/10 px-3.5 py-3 text-sm text-warning dark:text-warning-dark">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" /> {run.error_message}
        </div>
      )}

      {data.corpus_results.length > 0 && (
        <div className="mb-6 space-y-4">
          {data.corpus_results.map((result) => <ResultRow key={result.id} result={result} isCorpus />)}
        </div>
      )}

      {data.per_document_results.length > 0 ? (
        <div className="space-y-4">
          {data.per_document_results.map((result) => <ResultRow key={result.id} result={result} isCorpus={false} />)}
        </div>
      ) : data.corpus_results.length === 0 && run.status === 'completed' ? (
        <EmptyState icon={Sparkles} title="No results" message="This run completed without producing any results." />
      ) : null}

      {data.per_document_results.length === 0 && data.corpus_results.length === 0 && run.status === 'pending' && (
        <div className="mt-6 flex items-center justify-center gap-2 rounded-xl border border-line bg-card p-8 text-sm text-muted shadow-soft dark:border-line-dark dark:bg-card-dark dark:text-muted-dark">
          <Spinner size={16} />
          Waiting for a worker to pick this up - results appear here as they're ready.
        </div>
      )}
    </>
  );
}
