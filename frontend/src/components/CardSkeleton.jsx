import Skeleton from './Skeleton';

// Mimics MiniStatCard/KpiCard/StatCard's shape while its data loads -
// used in a grid alongside the real cards once they're ready, so the
// stat row's height never jumps between loading and loaded.
export function StatCardSkeleton() {
  return (
    <div className="min-w-0 rounded-xl border border-line bg-card p-3 shadow-soft dark:border-line-dark dark:bg-card-dark">
      <div className="flex items-center justify-between">
        <Skeleton className="h-3 w-16" />
        <Skeleton className="h-7 w-7 rounded-lg" />
      </div>
      <Skeleton className="mt-3 h-5 w-14" />
    </div>
  );
}

// Mimics a "header + divided list rows" card (Recent Documents, Recent
// Questions, Activity Feed, ...) while its data loads.
export function ListCardSkeleton({ rows = 4 }) {
  return (
    <div className="flex h-full flex-col rounded-xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">
      <div className="border-b border-line px-3.5 py-2 dark:border-line-dark">
        <Skeleton className="h-3.5 w-32" />
      </div>
      <div className="divide-y divide-line dark:divide-line-dark">
        {Array.from({ length: rows }).map((_, i) => (
          <div key={i} className="flex items-center gap-2.5 px-3.5 py-2">
            <Skeleton className="h-8 w-8 shrink-0 rounded-lg" />
            <div className="min-w-0 flex-1 space-y-1.5">
              <Skeleton className="h-3.5 w-3/4" />
              <Skeleton className="h-3 w-1/2" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// Mimics a chart card (a titled panel with a large plot area) while
// its data loads.
export function ChartCardSkeleton({ height = 'h-40' }) {
  return (
    <div className="min-w-0 rounded-xl border border-line bg-card p-3 shadow-soft dark:border-line-dark dark:bg-card-dark">
      <div className="mb-2 flex items-center justify-between">
        <Skeleton className="h-3.5 w-36" />
        <Skeleton className="h-6 w-16 rounded-lg" />
      </div>
      <Skeleton className={`w-full ${height}`} />
    </div>
  );
}
