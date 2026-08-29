import { useSearchParams } from 'react-router-dom';
import { FileText, Star, StarOff } from 'lucide-react';
import PageHeader from '../components/PageHeader';
import EmptyState from '../components/EmptyState';
import PageSkeleton from '../components/PageSkeleton';
import Spinner from '../components/Spinner';
import SimpleDocumentTable from '../components/SimpleDocumentTable';
import DocumentsTabs from '../layout/DocumentsTabs';
import { useFavoriteDocuments, useToggleFavorite } from '../api/hooks';

// Port of templates/documents/favorites.html.
export default function Favorites() {
  const [searchParams, setSearchParams] = useSearchParams();
  const page = searchParams.get('page') || '1';
  const { data, isLoading } = useFavoriteDocuments({ page });
  const toggleFavorite = useToggleFavorite();

  return (
    <>
      <PageHeader title="Favorites" subtitle="Documents you've pinned for quick access, across everything you own or can access." />
      <DocumentsTabs />

      {isLoading || !data ? <PageSkeleton variant="list" /> : (
        <SimpleDocumentTable
          documents={data.results}
          badgeIcon={FileText}
          leadingIcon={Star}
          pagination={data}
          onPageChange={(p) => setSearchParams({ page: String(p) })}
          emptyState={<EmptyState icon={Star} title="No favorites yet" message="Star a document from My Documents to pin it here for quick access." />}
          renderExtraActions={(doc) => {
            const isPending = toggleFavorite.isPending && toggleFavorite.variables === doc.id;
            return (
              <button
                type="button" onClick={() => toggleFavorite.mutate(doc.id)} disabled={isPending} title="Remove from Favorites"
                className="rounded-lg p-2 text-muted transition-colors hover:bg-danger/10 hover:text-danger disabled:opacity-50 dark:text-muted-dark dark:hover:text-danger-dark"
              >
                {isPending ? <Spinner size={16} /> : <StarOff className="h-4 w-4" />}
              </button>
            );
          }}
        />
      )}
    </>
  );
}
