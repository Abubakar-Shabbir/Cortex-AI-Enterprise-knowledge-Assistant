import Skeleton from './Skeleton';
import { StatCardSkeleton, ListCardSkeleton, ChartCardSkeleton } from './CardSkeleton';

// Icon + two-line row, repeated - the list/table-shaped skeleton used by
// both full list pages and list-shaped modal bodies (ShareModal,
// VersionsModal, SelectDocumentsDialog, NotificationBell, ...).
export function SkeletonRows({ rows = 6 }) {
  return (
    <div className="divide-y divide-line dark:divide-line-dark">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex items-center gap-3 px-1 py-3">
          <Skeleton className="h-9 w-9 shrink-0 rounded-lg" />
          <div className="min-w-0 flex-1 space-y-2">
            <Skeleton className="h-3.5 w-1/3" />
            <Skeleton className="h-3 w-1/2" />
          </div>
        </div>
      ))}
    </div>
  );
}

// Label/value pair block, repeated - the detail/form-shaped skeleton used
// by both full detail pages and key-value modal bodies (AdminQueries
// detail, AdminSystemLogs detail, Documents preview metadata, ...).
export function SkeletonFields({ fields = 4 }) {
  return (
    <div className="space-y-3 rounded-xl border border-line p-4 dark:border-line-dark">
      {Array.from({ length: fields }).map((_, i) => (
        <div key={i} className="space-y-1.5">
          <Skeleton className="h-3 w-1/4" />
          <Skeleton className="h-9 w-full" />
        </div>
      ))}
    </div>
  );
}

// The direct replacement for the old AppLoader variant="page" spinner -
// fills the same content-area footprint (sidebar/topbar stay mounted),
// but shaped to the page's content instead of a generic spinner:
// variant="list"   - table/list pages
// variant="detail" - profile/settings/form pages (header + fields)
// variant="grid"   - dashboard-shaped stat/list/chart pages
export default function PageSkeleton({ variant = 'list', rows = 6 }) {
  if (variant === 'grid') {
    return (
      <div className="w-full space-y-4 py-2">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <StatCardSkeleton key={i} />
          ))}
        </div>
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          <ChartCardSkeleton />
          <ListCardSkeleton />
        </div>
      </div>
    );
  }

  if (variant === 'detail') {
    return (
      <div className="w-full space-y-4 py-2">
        <div className="flex items-center gap-3">
          <Skeleton className="h-12 w-12 rounded-full" />
          <div className="space-y-2">
            <Skeleton className="h-4 w-40" />
            <Skeleton className="h-3 w-28" />
          </div>
        </div>
        <SkeletonFields fields={4} />
      </div>
    );
  }

  return (
    <div className="w-full py-2">
      <SkeletonRows rows={rows} />
    </div>
  );
}
