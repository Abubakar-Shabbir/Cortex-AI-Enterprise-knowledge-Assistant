import { useSearchParams } from 'react-router-dom';
import { Share2 } from 'lucide-react';
import PageHeader from '../components/PageHeader';
import EmptyState from '../components/EmptyState';
import PageSkeleton from '../components/PageSkeleton';
import SimpleDocumentTable from '../components/SimpleDocumentTable';
import DocumentsTabs from '../layout/DocumentsTabs';
import { useSharedWithMe } from '../api/hooks';

// Port of templates/documents/shared_with_me.html.
export default function SharedWithMe() {
  const [searchParams, setSearchParams] = useSearchParams();
  const page = searchParams.get('page') || '1';
  const { data, isLoading } = useSharedWithMe({ page });

  return (
    <>
      <PageHeader title="Shared With Me" subtitle="Documents another user or your role has shared with you." />
      <DocumentsTabs />

      {isLoading || !data ? <PageSkeleton variant="list" /> : (
        <SimpleDocumentTable
          documents={data.results}
          badgeIcon={Share2}
          pagination={data}
          onPageChange={(p) => setSearchParams({ page: String(p) })}
          emptyState={<EmptyState icon={Share2} title="Nothing shared with you yet" message="Documents another user shares with you, or with a role you hold, will show up here." />}
        />
      )}
    </>
  );
}
