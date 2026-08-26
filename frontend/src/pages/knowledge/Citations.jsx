import { Link } from 'react-router-dom';
import { Compass, Quote } from 'lucide-react';
import PageHeader from '../../components/PageHeader';
import EmptyState from '../../components/EmptyState';
import AppLoader from '../../components/AppLoader';
import KnowledgeTabs from '../../layout/KnowledgeTabs';
import { timeAgo } from '../../lib/timeAgo';
import { useCitationExplorer } from '../../api/hooks';

// Port of templates/knowledge/citations.html.
export default function Citations() {
  const { data, isLoading } = useCitationExplorer();

  if (isLoading || !data) return <AppLoader variant="page" />;

  const { citations } = data;

  return (
    <>
      <PageHeader title="Citation Viewer" subtitle="Every source your AI Search answers have actually cited, most recent first." />
      <KnowledgeTabs />

      <p className="mb-4 max-w-2xl text-sm text-muted dark:text-muted-dark">Every question you've asked where the AI Search answer traced back to a specific source chunk — the paper trail from an answer to where it actually came from.</p>

      <div className="overflow-hidden rounded-xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-line bg-surface dark:border-line-dark dark:bg-white/5">
              <tr className="text-xs font-semibold uppercase tracking-wide text-muted dark:text-muted-dark">
                <th className="px-5 py-3.5">Question</th>
                <th className="px-5 py-3.5">Cited Source</th>
                <th className="px-5 py-3.5">Citation</th>
                <th className="px-5 py-3.5">Asked</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line dark:divide-line-dark">
              {citations.length > 0 ? citations.map((citation, idx) => (
                <tr key={idx} className="transition-colors hover:bg-surface dark:hover:bg-white/5">
                  <td className="max-w-[320px] px-5 py-3.5">
                    <p className="truncate font-medium text-ink dark:text-ink-dark" title={citation.question}>{citation.question}</p>
                  </td>
                  <td className="px-5 py-3.5 text-muted dark:text-muted-dark">
                    {citation.document} · chunk {citation.chunk_number}
                    {citation.topic_id && (
                      <Link to={`/knowledge/entities/${citation.topic_id}`} className="ml-1.5 inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline dark:text-primary-soft">
                        <Compass className="h-3 w-3" /> View topic
                      </Link>
                    )}
                  </td>
                  <td className="px-5 py-3.5">
                    <span className="inline-flex items-center gap-1 rounded-full bg-primary-soft/40 px-2.5 py-1 text-xs font-medium text-primary dark:bg-primary/15 dark:text-primary-soft">
                      <Quote className="h-3 w-3" /> [{citation.citation_number}]
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-5 py-3.5 text-muted dark:text-muted-dark">{timeAgo(citation.created_at)} ago</td>
                </tr>
              )) : (
                <tr>
                  <td colSpan={4}>
                    <EmptyState icon={Quote} title="No citations yet" message="Once an AI Search answer cites a source, it'll show up here." actionTo="/ask" actionLabel="Ask a question" />
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
