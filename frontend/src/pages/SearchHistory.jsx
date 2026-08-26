import { Link, useSearchParams } from 'react-router-dom';
import AppLoader from '../components/AppLoader';
import { useSearchHistory } from '../api/hooks';

// Port of templates/search_history.html.
export default function SearchHistory() {
  const [searchParams, setSearchParams] = useSearchParams();
  const page = searchParams.get('page') || '1';
  const { data, isLoading } = useSearchHistory({ page });

  if (isLoading || !data) return <AppLoader variant="page" />;

  return (
    <>
      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight text-ink dark:text-ink-dark">Search History</h1>
        <p className="text-sm text-muted dark:text-muted-dark">Every question you've asked the assistant, with the documents used to answer it.</p>
      </div>

      <div className="overflow-hidden rounded-xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="sticky top-0 border-b border-line bg-surface dark:border-line-dark dark:bg-white/5">
              <tr className="text-xs font-semibold uppercase tracking-wide text-muted dark:text-muted-dark">
                <th className="px-5 py-3.5">Question</th>
                <th className="px-5 py-3.5">Date</th>
                <th className="px-5 py-3.5">Documents Used</th>
                <th className="px-5 py-3.5">Response Time</th>
                <th className="px-5 py-3.5">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line dark:divide-line-dark">
              {data.results.length > 0 ? data.results.map((row, idx) => (
                <tr key={idx} className="transition-colors hover:bg-surface dark:hover:bg-white/5">
                  <td className="max-w-[320px] px-5 py-3.5">
                    <p className="truncate font-medium text-ink dark:text-ink-dark" title={row.question}>{row.question}</p>
                  </td>
                  <td className="whitespace-nowrap px-5 py-3.5 text-muted dark:text-muted-dark">
                    {new Date(row.created_at).toLocaleString('en-US', { month: 'short', day: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false })}
                  </td>
                  <td className="px-5 py-3.5">
                    {row.documents_used.length > 0 ? (
                      <div className="flex flex-wrap gap-1.5">
                        {row.documents_used.slice(0, 2).map((title, i) => (
                          <span key={i} className="rounded-full border border-line px-2 py-0.5 text-xs text-muted dark:border-line-dark dark:text-muted-dark">{title.length > 18 ? `${title.slice(0, 18)}…` : title}</span>
                        ))}
                        {row.documents_used.length > 2 && (
                          <span className="rounded-full border border-line px-2 py-0.5 text-xs text-muted dark:border-line-dark dark:text-muted-dark">+{row.documents_used.length - 2}</span>
                        )}
                      </div>
                    ) : <span className="text-muted dark:text-muted-dark">—</span>}
                  </td>
                  <td className="whitespace-nowrap px-5 py-3.5 text-muted dark:text-muted-dark">{row.response_time_ms} ms</td>
                  <td className="px-5 py-3.5">
                    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${row.answered ? 'bg-success/10 text-success dark:text-success-dark' : 'bg-warning/10 text-warning dark:text-warning-dark'}`}>
                      <span className={`h-1.5 w-1.5 rounded-full ${row.answered ? 'bg-success' : 'bg-warning'}`}></span>
                      {row.answered ? 'Answered' : 'No Match'}
                    </span>
                  </td>
                </tr>
              )) : (
                <tr>
                  <td colSpan={5} className="px-5 py-14 text-center text-sm text-muted dark:text-muted-dark">
                    No questions asked yet. <Link to="/ask" className="font-medium text-primary hover:underline dark:text-primary-soft">Ask your first question</Link>.
                  </td>
                </tr>
              )}
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
      </div>
    </>
  );
}
