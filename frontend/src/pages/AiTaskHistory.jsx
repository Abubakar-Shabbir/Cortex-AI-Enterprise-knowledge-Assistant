import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Eye, Sparkles, Trash2 } from 'lucide-react';
import PageHeader from '../components/PageHeader';
import EmptyState from '../components/EmptyState';
import AppLoader from '../components/AppLoader';
import Spinner from '../components/Spinner';
import { useAiTaskHistory, useDeleteAiTask } from '../api/hooks';

const STATUS_CLASSES = {
  completed: 'bg-success/10 text-success dark:text-success-dark',
  failed: 'bg-danger/10 text-danger dark:text-danger-dark',
  running: 'bg-warning/10 text-warning dark:text-warning-dark',
};
const STATUS_DOT_CLASSES = { completed: 'bg-success', failed: 'bg-danger', running: 'bg-warning' };

// Port of templates/ai_tasks/history.html.
export default function AiTaskHistory() {
  const [searchParams, setSearchParams] = useSearchParams();
  const page = searchParams.get('page') || '1';
  const { data, isLoading, refetch } = useAiTaskHistory({ page });
  const deleteRun = useDeleteAiTask();
  const [deletingId, setDeletingId] = useState(null);

  if (isLoading || !data) return <AppLoader variant="page" />;

  const onDelete = async (runId) => {
    if (!window.confirm('Delete this AI Task run and its results? This cannot be undone.')) return;
    setDeletingId(runId);
    try {
      await deleteRun.mutateAsync(runId);
      refetch();
    } catch (err) {
      window.alert(err.data?.error || err.message || 'Could not delete this run.');
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <>
      <PageHeader title="AI Task History" subtitle="Every guided AI Task you've run, and its results." />
      <div className="mb-4 -mt-4 flex justify-end">
        <Link to="/ai-tasks" className="inline-flex items-center gap-2 rounded-lg bg-primary px-3.5 py-2 text-sm font-semibold text-white transition-colors hover:bg-primary-dark">
          <Sparkles className="h-4 w-4" /> New AI Task
        </Link>
      </div>

      <div className="overflow-hidden rounded-xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">
        {data.results.length > 0 ? (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="sticky top-0 border-b border-line bg-surface dark:border-line-dark dark:bg-white/5">
                  <tr className="text-xs font-semibold uppercase tracking-wide text-muted dark:text-muted-dark">
                    <th className="px-5 py-3.5">Task</th>
                    <th className="px-5 py-3.5">Documents</th>
                    <th className="px-5 py-3.5">Status</th>
                    <th className="px-5 py-3.5">Started</th>
                    <th className="px-5 py-3.5 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line dark:divide-line-dark">
                  {data.results.map((run) => {
                    const isActive = run.status === 'pending' || run.status === 'running';
                    return (
                      <tr key={run.id} className="transition-colors hover:bg-surface dark:hover:bg-white/5">
                        <td className="px-5 py-3.5">
                          <div className="flex items-center gap-2.5">
                            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary-soft/50 text-primary dark:bg-primary/15 dark:text-primary-soft">
                              <Sparkles className="h-4 w-4" />
                            </div>
                            <span className="font-medium text-ink dark:text-ink-dark">{run.task_type_display}</span>
                          </div>
                        </td>
                        <td className="px-5 py-3.5 text-muted dark:text-muted-dark">{run.document_count} document{run.document_count === 1 ? '' : 's'}</td>
                        <td className="px-5 py-3.5">
                          <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${STATUS_CLASSES[run.status] || 'bg-line text-muted dark:bg-white/10 dark:text-muted-dark'}`}>
                            <span className={`h-1.5 w-1.5 rounded-full ${STATUS_DOT_CLASSES[run.status] || 'bg-muted'}`}></span>
                            {run.status_display}
                          </span>
                        </td>
                        <td className="whitespace-nowrap px-5 py-3.5 text-muted dark:text-muted-dark">{new Date(run.created_at).toLocaleString('en-US', { month: 'short', day: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false })}</td>
                        <td className="px-5 py-3.5 text-right">
                          <div className="inline-flex items-center gap-1.5">
                            <Link to={`/ai-tasks/${run.id}/results`} className="inline-flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-xs font-medium text-ink transition-colors hover:border-primary/30 hover:bg-primary/5 hover:text-primary dark:border-line-dark dark:text-ink-dark dark:hover:bg-primary/10">
                              <Eye className="h-3.5 w-3.5" /> View
                            </Link>
                            {isActive ? (
                              <span title="Stop this run first (from the View page) before deleting it." className="inline-flex cursor-not-allowed items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-xs font-medium text-muted opacity-60 dark:border-line-dark dark:text-muted-dark">
                                <Trash2 className="h-3.5 w-3.5" /> Delete
                              </span>
                            ) : (
                              <button
                                type="button" onClick={() => onDelete(run.id)} disabled={deletingId === run.id}
                                className="inline-flex items-center gap-1.5 rounded-lg border border-danger/30 bg-danger/5 px-3 py-1.5 text-xs font-medium text-danger transition-colors hover:bg-danger/10 disabled:cursor-not-allowed disabled:opacity-60 dark:border-danger-dark/30 dark:text-danger-dark dark:hover:bg-danger-dark/10"
                              >
                                {deletingId === run.id ? <Spinner size={14} /> : <Trash2 className="h-3.5 w-3.5" />} Delete
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {data.num_pages > 1 && (
              <div className="flex items-center justify-between border-t border-line px-5 py-3.5 dark:border-line-dark">
                <p className="text-xs text-muted dark:text-muted-dark">Page {data.page} of {data.num_pages}</p>
                <div className="flex gap-1.5">
                  {data.has_previous && <button onClick={() => setSearchParams({ page: String(data.page - 1) })} className="rounded-lg border border-line px-3 py-1.5 text-xs font-medium text-ink hover:bg-surface dark:border-line-dark dark:text-ink-dark dark:hover:bg-white/5">Previous</button>}
                  {data.has_next && <button onClick={() => setSearchParams({ page: String(data.page + 1) })} className="rounded-lg border border-line px-3 py-1.5 text-xs font-medium text-ink hover:bg-surface dark:border-line-dark dark:text-ink-dark dark:hover:bg-white/5">Next</button>}
                </div>
              </div>
            )}
          </>
        ) : (
          <EmptyState icon={Sparkles} title="No AI Tasks run yet" message="Run your first guided AI Task over a set of documents." actionTo="/ai-tasks" actionLabel="Start an AI Task" />
        )}
      </div>
    </>
  );
}
