import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { CheckCircle2, Download, Eye, Filter, Flag, Gauge, GitBranch, Lock, Search, Timer, X } from 'lucide-react';
import PageHeader from '../components/PageHeader';
import StatCard from '../components/StatCard';
import EmptyState from '../components/EmptyState';
import AppLoader from '../components/AppLoader';
import { getApiBaseUrl } from '../api/client';
import { timeAgo } from '../lib/timeAgo';
import { fetchAdminQueryDetail, useAdminQueries, useToggleQueryFlag } from '../api/hooks';

function DetailModal({ logId, onClose }) {
  const [state, setState] = useState({ loading: true, data: null });

  useEffect(() => {
    fetchAdminQueryDetail(logId).then((data) => setState({ loading: false, data }));
  }, [logId]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-line bg-card p-6 shadow-2xl dark:border-line-dark dark:bg-card-dark">
        {state.loading ? (
          <p className="text-sm text-muted dark:text-muted-dark">Loading…</p>
        ) : state.data ? (
          <div className="space-y-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-xs font-medium uppercase tracking-wide text-muted dark:text-muted-dark">Query by {state.data.owner}</p>
                <p className="text-xs text-muted dark:text-muted-dark">{state.data.created_at}</p>
              </div>
              <button type="button" onClick={onClose} className="flex h-8 w-8 items-center justify-center rounded-lg text-muted hover:bg-surface dark:text-muted-dark dark:hover:bg-white/5"><X className="h-4 w-4" /></button>
            </div>

            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted dark:text-muted-dark">Question</p>
              <p className="rounded-lg bg-surface p-3 text-sm text-ink dark:bg-white/5 dark:text-ink-dark">{state.data.question}</p>
            </div>

            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted dark:text-muted-dark">Answer</p>
              <p className="whitespace-pre-wrap rounded-lg bg-surface p-3 text-sm text-ink dark:bg-white/5 dark:text-ink-dark">{state.data.answer}</p>
            </div>

            <div className="grid grid-cols-3 gap-3 text-center text-xs">
              <div className="rounded-lg border border-line p-2 dark:border-line-dark">
                <div className="font-semibold text-ink dark:text-ink-dark">{state.data.confidence}%</div>
                <div className="text-muted dark:text-muted-dark">Confidence</div>
              </div>
              <div className="rounded-lg border border-line p-2 dark:border-line-dark">
                <div className="font-semibold text-ink dark:text-ink-dark">{state.data.response_time_ms} ms</div>
                <div className="text-muted dark:text-muted-dark">Response Time</div>
              </div>
              <div className="rounded-lg border border-line p-2 dark:border-line-dark">
                <div className="font-semibold text-ink dark:text-ink-dark">{state.data.sources?.length || 0}</div>
                <div className="text-muted dark:text-muted-dark">Sources</div>
              </div>
            </div>

            {state.data.sources?.length > 0 && (
              <div>
                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted dark:text-muted-dark">Source References</p>
                <div className="space-y-2">
                  {state.data.sources.map((src, idx) => (
                    <div key={idx} className="rounded-lg border border-line p-2.5 text-xs dark:border-line-dark">
                      <div className="mb-1 font-medium text-ink dark:text-ink-dark">{src.document || 'Document'} · chunk {src.chunk_number}</div>
                      <div className="text-muted dark:text-muted-dark">{src.content}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : null}
      </div>
    </div>
  );
}

// Port of templates/admin/queries.html.
export default function AdminQueries() {
  const [searchParams, setSearchParams] = useSearchParams();
  const filters = Object.fromEntries(searchParams.entries());
  const { data, isLoading } = useAdminQueries(filters);
  const toggleFlag = useToggleQueryFlag();
  const [detailId, setDetailId] = useState(null);

  if (isLoading || !data) return <AppLoader variant="page" />;

  const onFilterSubmit = (e) => {
    e.preventDefault();
    const form = new FormData(e.target);
    const next = {};
    for (const [key, value] of form.entries()) if (value) next[key] = value;
    setSearchParams(next);
  };

  const setPage = (p) => setSearchParams({ ...filters, page: String(p) });
  const exportUrl = `${getApiBaseUrl()}/api/admin/queries/export.csv?${searchParams.toString()}`;

  return (
    <>
      <PageHeader title="Queries" subtitle="Every question asked across the workspace, with search, filters, and analytics. Question/answer content stays private unless you hold the auditing permission." />

      <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <StatCard icon={Search} label="Total Queries" value={data.analytics.total} numeric />
        <StatCard icon={CheckCircle2} label="Answered" value={data.analytics.answered_pct} sublabel="% of all queries" numeric />
        <StatCard icon={Gauge} label="Avg Confidence" value={data.analytics.avg_confidence} sublabel="percent" numeric />
        <StatCard icon={Timer} label="Avg Response" value={data.analytics.avg_response_time} sublabel="milliseconds" numeric />
        <StatCard icon={Flag} label="Flagged" value={data.analytics.flagged_count} numeric />
        <StatCard icon={GitBranch} label="Top Method" value={data.analytics.top_method} />
      </div>

      <div className="mb-4 rounded-2xl border border-line bg-card p-4 shadow-soft dark:border-line-dark dark:bg-card-dark">
        <form key={searchParams.toString()} onSubmit={onFilterSubmit} className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-6">
          {data.can_view_content && (
            <div className="lg:col-span-2">
              <label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">Search content</label>
              <input type="text" name="q" defaultValue={filters.q} placeholder="Question or answer text…" className="w-full rounded-lg border border-line bg-transparent px-3 py-2 text-sm text-ink placeholder:text-muted focus:border-primary focus:outline-none dark:border-line-dark dark:text-ink-dark" />
            </div>
          )}
          <div>
            <label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">Owner</label>
            <input type="text" name="owner" defaultValue={filters.owner} placeholder="Username…" className="w-full rounded-lg border border-line bg-transparent px-3 py-2 text-sm text-ink placeholder:text-muted focus:border-primary focus:outline-none dark:border-line-dark dark:text-ink-dark" />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">Scope</label>
            <select name="scope" defaultValue={filters.scope || ''} className="w-full rounded-lg border border-line bg-transparent px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none dark:border-line-dark dark:text-ink-dark">
              <option value="">Everyone</option>
              <option value="mine">My own queries</option>
              <option value="others">Other members' queries</option>
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">Status</label>
            <select name="status" defaultValue={filters.status || ''} className="w-full rounded-lg border border-line bg-transparent px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none dark:border-line-dark dark:text-ink-dark">
              <option value="">Any</option>
              <option value="answered">Answered</option>
              <option value="not_found">No Answer Found</option>
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">Method</label>
            <select name="method" defaultValue={filters.method || ''} className="w-full rounded-lg border border-line bg-transparent px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none dark:border-line-dark dark:text-ink-dark">
              <option value="">Any</option>
              {data.search_methods.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">Min. confidence</label>
            <select name="min_confidence" defaultValue={filters.min_confidence || ''} className="w-full rounded-lg border border-line bg-transparent px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none dark:border-line-dark dark:text-ink-dark">
              <option value="">Any</option>
              <option value="25">25%+</option>
              <option value="50">50%+</option>
              <option value="75">75%+</option>
              <option value="90">90%+</option>
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">Sort</label>
            <select name="sort" defaultValue={filters.sort || 'newest'} className="w-full rounded-lg border border-line bg-transparent px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none dark:border-line-dark dark:text-ink-dark">
              <option value="newest">Newest first</option>
              <option value="oldest">Oldest first</option>
              <option value="confidence_high">Confidence: high → low</option>
              <option value="confidence_low">Confidence: low → high</option>
              <option value="slowest">Slowest first</option>
              <option value="fastest">Fastest first</option>
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">From</label>
            <input type="date" name="date_from" defaultValue={filters.date_from} className="w-full rounded-lg border border-line bg-transparent px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none dark:border-line-dark dark:text-ink-dark" />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">To</label>
            <input type="date" name="date_to" defaultValue={filters.date_to} className="w-full rounded-lg border border-line bg-transparent px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none dark:border-line-dark dark:text-ink-dark" />
          </div>
          <label className="flex items-center gap-2 self-end pb-2 text-sm text-ink dark:text-ink-dark">
            <input type="checkbox" name="flagged" value="1" defaultChecked={filters.flagged === '1'} className="h-4 w-4 rounded border-line text-primary focus:ring-primary dark:border-line-dark" />
            Flagged only
          </label>
          <div className="flex items-end gap-2 lg:col-span-2">
            <button type="submit" className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-primary-dark"><Filter className="h-4 w-4" /> Apply</button>
            <button type="button" onClick={() => setSearchParams({})} className="inline-flex items-center gap-2 rounded-lg border border-line px-4 py-2 text-sm font-medium text-ink transition-colors hover:bg-surface dark:border-line-dark dark:text-ink-dark dark:hover:bg-white/5">Reset</button>
            <a href={exportUrl} className="ml-auto inline-flex items-center gap-2 rounded-lg border border-line px-4 py-2 text-sm font-medium text-ink transition-colors hover:border-primary/30 hover:bg-primary/5 hover:text-primary dark:border-line-dark dark:text-ink-dark dark:hover:bg-primary/10">
              <Download className="h-4 w-4" /> Export CSV
            </a>
          </div>
        </form>
      </div>

      <div className="rounded-2xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">
        {data.results.length > 0 ? (
          <>
            <div className="overflow-auto">
              <table className="w-full min-w-[920px] text-left text-sm">
                <thead className="sticky top-0 z-10 bg-card dark:bg-card-dark">
                  <tr className="border-b border-line text-xs font-semibold uppercase tracking-wide text-muted dark:border-line-dark dark:text-muted-dark">
                    <th className="px-5 py-3">Question</th>
                    <th className="px-3 py-3">Owner</th>
                    <th className="px-3 py-3">Status</th>
                    <th className="px-3 py-3">Method</th>
                    <th className="px-3 py-3 text-right">Confidence</th>
                    <th className="px-3 py-3 text-right">Response</th>
                    <th className="px-3 py-3 text-right">Sources</th>
                    <th className="px-3 py-3">Asked</th>
                    <th className="px-5 py-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line dark:divide-line-dark">
                  {data.results.map((log) => (
                    <tr key={log.id} className="transition-colors hover:bg-surface dark:hover:bg-white/5">
                      <td className="max-w-[280px] px-5 py-3 font-medium text-ink dark:text-ink-dark">
                        {data.can_view_content ? (
                          <span className="block truncate" title={log.question}>{log.question}</span>
                        ) : (
                          <span className="inline-flex items-center gap-1.5 text-muted dark:text-muted-dark"><Lock className="h-3.5 w-3.5" /> Protected</span>
                        )}
                      </td>
                      <td className="px-3 py-3 text-muted dark:text-muted-dark">{log.owner}</td>
                      <td className="px-3 py-3">
                        <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ${log.status_answered ? 'bg-success/10 text-success dark:text-success-dark' : 'bg-danger/10 text-danger dark:text-danger-dark'}`}>{log.status_label}</span>
                      </td>
                      <td className="px-3 py-3 text-muted dark:text-muted-dark">{log.search_method}</td>
                      <td className="px-3 py-3 text-right text-muted dark:text-muted-dark">{log.confidence}%</td>
                      <td className="px-3 py-3 text-right text-muted dark:text-muted-dark">{log.response_time_ms} ms</td>
                      <td className="px-3 py-3 text-right text-muted dark:text-muted-dark">{log.source_count}</td>
                      <td className="px-3 py-3 text-muted dark:text-muted-dark">{timeAgo(log.created_at)} ago</td>
                      <td className="px-5 py-3">
                        <div className="flex items-center justify-end gap-1.5">
                          <button
                            type="button" onClick={() => toggleFlag.mutate(log.id)} title={log.is_flagged ? 'Unpin' : 'Pin for follow-up'}
                            className={`flex h-8 w-8 items-center justify-center rounded-lg transition-colors ${log.is_flagged ? 'text-warning hover:bg-warning/10' : 'text-muted hover:bg-surface dark:text-muted-dark dark:hover:bg-white/5'}`}
                          >
                            <Flag className="h-4 w-4" />
                          </button>
                          {data.can_view_content && (
                            <button type="button" onClick={() => setDetailId(log.id)} className="inline-flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1.5 text-xs font-medium text-ink transition-colors hover:border-primary/30 hover:bg-primary/5 hover:text-primary dark:border-line-dark dark:text-ink-dark dark:hover:bg-primary/10">
                              <Eye className="h-3.5 w-3.5" /> View
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {data.num_pages > 1 && (
              <div className="flex items-center justify-between border-t border-line px-5 py-3 dark:border-line-dark">
                <p className="text-xs text-muted dark:text-muted-dark">Page {data.page} of {data.num_pages} · {data.count} total</p>
                <div className="flex gap-2">
                  {data.has_previous && <button onClick={() => setPage(data.page - 1)} className="rounded-lg border border-line px-3 py-1.5 text-xs font-medium text-ink hover:bg-surface dark:border-line-dark dark:text-ink-dark dark:hover:bg-white/5">Previous</button>}
                  {data.has_next && <button onClick={() => setPage(data.page + 1)} className="rounded-lg border border-line px-3 py-1.5 text-xs font-medium text-ink hover:bg-surface dark:border-line-dark dark:text-ink-dark dark:hover:bg-white/5">Next</button>}
                </div>
              </div>
            )}
          </>
        ) : (
          <EmptyState icon={Search} title="No queries match these filters" />
        )}
      </div>

      {detailId && <DetailModal logId={detailId} onClose={() => setDetailId(null)} />}
    </>
  );
}
