import { Link, useSearchParams } from 'react-router-dom';
import { ArrowRight, GitBranch } from 'lucide-react';
import PageHeader from '../../components/PageHeader';
import EmptyState from '../../components/EmptyState';
import AppLoader from '../../components/AppLoader';
import KnowledgeTabs from '../../layout/KnowledgeTabs';
import { timeAgo } from '../../lib/timeAgo';
import { useRelationships } from '../../api/hooks';

// Port of templates/knowledge/relationships.html.
export default function Relationships() {
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedType = searchParams.get('type') || '';
  const page = searchParams.get('page') || '1';

  const { data, isLoading } = useRelationships({ type: selectedType, page });

  if (isLoading || !data) return <AppLoader variant="page" />;

  const { relationships, pagination, relation_types: relationTypes } = data;

  return (
    <>
      <PageHeader title="Relationship Explorer" subtitle="Directed connections between topics across everything you can access, weighted by how often they're re-confirmed." />
      <KnowledgeTabs />

      <p className="mb-4 max-w-2xl text-sm text-muted dark:text-muted-dark">Relationships show how pieces of knowledge are connected — a source topic, a directed connection, and a target topic, reinforced each time it's found again across your documents.</p>

      <div className="mb-4 rounded-xl border border-line bg-card p-4 shadow-soft dark:border-line-dark dark:bg-card-dark">
        <div className="flex flex-wrap items-center gap-3">
          <select
            value={selectedType}
            onChange={(e) => setSearchParams(e.target.value ? { type: e.target.value } : {})}
            className="rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none dark:border-line-dark dark:bg-white/5 dark:text-ink-dark"
          >
            <option value="">All relationship types</option>
            {relationTypes.map((rtype) => <option key={rtype} value={rtype}>{rtype.toLowerCase()}</option>)}
          </select>
          {selectedType && (
            <button onClick={() => setSearchParams({})} className="text-sm font-medium text-muted hover:text-ink dark:text-muted-dark dark:hover:text-ink-dark">Clear</button>
          )}
        </div>
      </div>

      <div className="overflow-hidden rounded-xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-line bg-surface dark:border-line-dark dark:bg-white/5">
              <tr className="text-xs font-semibold uppercase tracking-wide text-muted dark:text-muted-dark">
                <th className="px-5 py-3.5">Source</th>
                <th className="px-5 py-3.5">Relationship</th>
                <th className="px-5 py-3.5">Target</th>
                <th className="px-5 py-3.5">Confirmations</th>
                <th className="px-5 py-3.5">Last Updated</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line dark:divide-line-dark">
              {relationships.length > 0 ? relationships.map((rel) => (
                <tr key={rel.id} className="transition-colors hover:bg-surface dark:hover:bg-white/5">
                  <td className="px-5 py-3.5">
                    <Link to={`/knowledge/entities/${rel.source.id}`} className="inline-flex items-center gap-1.5 font-medium text-ink hover:text-primary dark:text-ink-dark dark:hover:text-primary-soft">
                      <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: rel.source.color }}></span> {rel.source.display_name}
                    </Link>
                  </td>
                  <td className="px-5 py-3.5">
                    <span className="inline-flex items-center gap-1.5 rounded-full bg-primary-soft/40 px-2.5 py-1 text-xs font-medium text-primary dark:bg-primary/15 dark:text-primary-soft">
                      <ArrowRight className="h-3 w-3" /> {rel.relation_type.toLowerCase()}
                    </span>
                  </td>
                  <td className="px-5 py-3.5">
                    <Link to={`/knowledge/entities/${rel.target.id}`} className="inline-flex items-center gap-1.5 font-medium text-ink hover:text-primary dark:text-ink-dark dark:hover:text-primary-soft">
                      <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: rel.target.color }}></span> {rel.target.display_name}
                    </Link>
                  </td>
                  <td className="px-5 py-3.5 text-muted dark:text-muted-dark">×{rel.weight}</td>
                  <td className="px-5 py-3.5 text-muted dark:text-muted-dark">{timeAgo(rel.updated_at)} ago</td>
                </tr>
              )) : (
                <tr>
                  <td colSpan={5}>
                    <EmptyState icon={GitBranch} title="No relationships yet" message="Relationships appear here once documents mentioning connected entities are processed." />
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {pagination.num_pages > 1 && (
          <div className="flex items-center justify-between border-t border-line px-5 py-3.5 dark:border-line-dark">
            <p className="text-xs text-muted dark:text-muted-dark">Page {pagination.page} of {pagination.num_pages}</p>
            <div className="flex gap-1.5">
              {pagination.has_previous && (
                <button onClick={() => setSearchParams({ ...(selectedType ? { type: selectedType } : {}), page: String(pagination.page - 1) })} className="rounded-lg border border-line px-3 py-1.5 text-xs font-medium text-ink hover:bg-surface dark:border-line-dark dark:text-ink-dark dark:hover:bg-white/5">Previous</button>
              )}
              {pagination.has_next && (
                <button onClick={() => setSearchParams({ ...(selectedType ? { type: selectedType } : {}), page: String(pagination.page + 1) })} className="rounded-lg border border-line px-3 py-1.5 text-xs font-medium text-ink hover:bg-surface dark:border-line-dark dark:text-ink-dark dark:hover:bg-white/5">Next</button>
              )}
            </div>
          </div>
        )}
      </div>
    </>
  );
}
