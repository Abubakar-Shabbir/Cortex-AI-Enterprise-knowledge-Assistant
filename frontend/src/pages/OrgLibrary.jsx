import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { FileText, HardDrive, Library, LibraryBig, Search } from 'lucide-react';
import PageHeader from '../components/PageHeader';
import StatCard from '../components/StatCard';
import EmptyState from '../components/EmptyState';
import AppLoader from '../components/AppLoader';
import Spinner from '../components/Spinner';
import SimpleDocumentTable from '../components/SimpleDocumentTable';
import DocumentsTabs from '../layout/DocumentsTabs';
import { useOrgLibrary, useToggleOrgLibrary } from '../api/hooks';

// Port of templates/documents/org_library.html.
export default function OrgLibrary() {
  const [searchParams, setSearchParams] = useSearchParams();
  const page = searchParams.get('page') || '1';
  const addQuery = searchParams.get('add_q') || '';
  const [searchInput, setSearchInput] = useState(addQuery);

  const { data, isLoading } = useOrgLibrary({ page, add_q: addQuery });
  const toggleOrgLibrary = useToggleOrgLibrary();

  const onSearch = (e) => {
    e.preventDefault();
    setSearchParams(searchInput ? { add_q: searchInput } : {});
  };

  const onRemove = (doc) => {
    if (window.confirm('Remove this document from the Organization Library?')) {
      toggleOrgLibrary.mutate(doc.id);
    }
  };

  if (isLoading || !data) return <AppLoader variant="page" />;

  return (
    <>
      <PageHeader title="Organization Library" subtitle="Admin-managed documents visible workspace-wide — policies, SOPs, manuals, templates." />
      <DocumentsTabs />

      <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-2">
        <StatCard icon={Library} label="Total Library Documents" value={data.total_org_documents} numeric />
        <StatCard icon={HardDrive} label="Library Storage" value={data.total_org_storage} />
      </div>

      {data.can_manage && (
        <div className="mb-6 rounded-xl border border-line bg-card p-4 shadow-soft dark:border-line-dark dark:bg-card-dark">
          <form onSubmit={onSearch} className="flex flex-wrap items-end gap-3">
            <div className="min-w-[240px] flex-1">
              <label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">Find a document to publish</label>
              <input
                type="text" value={searchInput} onChange={(e) => setSearchInput(e.target.value)}
                placeholder="Search by title, any user's document…"
                className="w-full rounded-lg border border-line bg-transparent px-3 py-2 text-sm text-ink placeholder:text-muted focus:border-primary focus:outline-none dark:border-line-dark dark:text-ink-dark"
              />
            </div>
            <button type="submit" className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-primary-dark">
              <Search className="h-4 w-4" /> Search
            </button>
          </form>

          {addQuery && (
            <div className="mt-4 space-y-1.5">
              {data.add_candidates.length > 0 ? data.add_candidates.map((doc) => {
                const isPending = toggleOrgLibrary.isPending && toggleOrgLibrary.variables === doc.id;
                return (
                  <div key={doc.id} className="flex items-center justify-between rounded-lg border border-line px-3 py-2 text-sm dark:border-line-dark">
                    <div className="flex items-center gap-2 truncate">
                      <FileText className="h-3.5 w-3.5 shrink-0 text-muted dark:text-muted-dark" />
                      <span className="truncate text-ink dark:text-ink-dark">{doc.title}</span>
                      <span className="shrink-0 text-xs text-muted dark:text-muted-dark">by {doc.owner}</span>
                    </div>
                    <button
                      type="button" onClick={() => toggleOrgLibrary.mutate(doc.id)} disabled={isPending}
                      className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-line px-2.5 py-1 text-xs font-medium text-primary hover:border-primary/30 hover:bg-primary/5 disabled:opacity-50 dark:border-line-dark dark:text-primary-soft"
                    >
                      {isPending && <Spinner size={12} />} Add to Library
                    </button>
                  </div>
                );
              }) : <p className="text-xs text-muted dark:text-muted-dark">No matching documents outside the library.</p>}
            </div>
          )}
        </div>
      )}

      <SimpleDocumentTable
        documents={data.results}
        badgeIcon={Library}
        pagination={data}
        onPageChange={(p) => setSearchParams({ ...(addQuery ? { add_q: addQuery } : {}), page: String(p) })}
        emptyState={<EmptyState icon={Library} title="Nothing in the Organization Library yet" message="An Admin can add a document to the library from My Documents." />}
        renderExtraActions={data.can_manage ? (doc) => {
          const isPending = toggleOrgLibrary.isPending && toggleOrgLibrary.variables === doc.id;
          return (
            <button type="button" onClick={() => onRemove(doc)} disabled={isPending} title="Remove from Library" className="rounded-lg p-2 text-muted transition-colors hover:bg-danger/10 hover:text-danger disabled:opacity-50 dark:text-muted-dark dark:hover:text-danger-dark">
              {isPending ? <Spinner size={16} /> : <LibraryBig className="h-4 w-4" />}
            </button>
          );
        } : undefined}
      />
    </>
  );
}
