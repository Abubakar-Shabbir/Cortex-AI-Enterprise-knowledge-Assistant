import { useParams, useSearchParams } from 'react-router-dom';
import { FolderMinus, FolderOpen } from 'lucide-react';
import PageHeader from '../components/PageHeader';
import EmptyState from '../components/EmptyState';
import PageSkeleton from '../components/PageSkeleton';
import Spinner from '../components/Spinner';
import SimpleDocumentTable from '../components/SimpleDocumentTable';
import { useCollectionDetail, useCollectionDetailAction } from '../api/hooks';

// Port of templates/documents/collection_detail.html.
export default function CollectionDetail() {
  const { collectionId } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const page = searchParams.get('page') || '1';
  const { data, isLoading } = useCollectionDetail(collectionId, { page });
  const action = useCollectionDetailAction(collectionId);

  if (isLoading || !data) return <PageSkeleton variant="detail" />;

  const onRemove = (doc) => action.mutate({ action: 'remove_document', doc_id: doc.id });

  return (
    <>
      <PageHeader title={data.collection.name} subtitle={data.collection.description || 'Documents filed in this collection.'} />

      <SimpleDocumentTable
        documents={data.results}
        badgeIcon={FolderOpen}
        pagination={data}
        onPageChange={(p) => setSearchParams({ page: String(p) })}
        emptyState={<EmptyState icon={FolderOpen} title="This collection is empty" message="Add documents to it from My Documents." actionTo="/documents" actionLabel="Go to My Documents" />}
        renderExtraActions={(doc) => {
          const isPending = action.isPending && action.variables?.doc_id === doc.id;
          return (
            <button type="button" onClick={() => onRemove(doc)} disabled={isPending} title="Remove from collection" className="rounded-lg p-2 text-muted transition-colors hover:bg-danger/10 hover:text-danger disabled:opacity-50 dark:text-muted-dark dark:hover:text-danger-dark">
              {isPending ? <Spinner size={16} /> : <FolderMinus className="h-4 w-4" />}
            </button>
          );
        }}
      />
    </>
  );
}
