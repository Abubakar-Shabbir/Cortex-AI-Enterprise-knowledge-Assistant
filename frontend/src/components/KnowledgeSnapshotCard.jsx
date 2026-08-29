import { Link } from 'react-router-dom';
import ChartCanvas from './ChartCanvas';

const GRID_COLOR = 'rgba(109, 102, 101, 0.12)';

// Port of templates/dashboard/_knowledge_snapshot.html. `showChart`
// (unset by default) renders the polar-area "Topics by Category"
// breakdown - only Admin Overview passes it, matching the Django
// partial's own `show_chart` flag (User Overview stays chart-free).
export default function KnowledgeSnapshotCard({ data, showChart = false }) {
  const categoryBreakdown = data?.category_breakdown || [];

  const chartConfig = {
    type: 'polarArea',
    data: {
      labels: categoryBreakdown.map((item) => item.entity_type),
      datasets: [{
        data: categoryBreakdown.map((item) => item.count),
        backgroundColor: categoryBreakdown.map((item) => `${item.color}55`),
        borderColor: categoryBreakdown.map((item) => item.color),
        borderWidth: 1.5,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { animateRotate: true, animateScale: true },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label(item) {
              const entry = categoryBreakdown[item.dataIndex];
              return ` ${entry.entity_type}: ${entry.count} (${entry.percent}%)`;
            },
          },
        },
      },
      scales: {
        r: {
          grid: { color: GRID_COLOR },
          ticks: { display: false, backdropColor: 'transparent' },
        },
      },
    },
  };

  return (
    <div className="flex h-full flex-col rounded-xl border border-line bg-card p-3 shadow-soft dark:border-line-dark dark:bg-card-dark">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-ink dark:text-ink-dark">Knowledge Center</h2>
        <Link to="/knowledge" className="text-xs font-medium text-primary hover:underline dark:text-primary-soft">Explore</Link>
      </div>

      <div className="grid grid-cols-3 gap-1.5 text-center">
        <div className="rounded-lg bg-surface px-1.5 py-2 dark:bg-white/5">
          <div className="text-base font-bold leading-tight tracking-tight text-ink dark:text-ink-dark">{data?.total_entities ?? 0}</div>
          <div className="mt-0.5 text-[11px] leading-tight text-muted dark:text-muted-dark">Topics</div>
        </div>
        <div className="rounded-lg bg-surface px-1.5 py-2 dark:bg-white/5">
          <div className="text-base font-bold leading-tight tracking-tight text-ink dark:text-ink-dark">{data?.total_relationships ?? 0}</div>
          <div className="mt-0.5 text-[11px] leading-tight text-muted dark:text-muted-dark">Links</div>
        </div>
        <div className="rounded-lg bg-surface px-1.5 py-2 dark:bg-white/5">
          <div className="text-base font-bold leading-tight tracking-tight text-ink dark:text-ink-dark">{data?.total_sources ?? 0}</div>
          <div className="mt-0.5 text-[11px] leading-tight text-muted dark:text-muted-dark">Docs</div>
        </div>
      </div>

      {showChart && categoryBreakdown.length > 0 && (
        <div className="mt-3 border-t border-line pt-3 dark:border-line-dark">
          <div className="mb-2 text-xs font-semibold text-ink dark:text-ink-dark">Topics by Category</div>
          <div className="flex items-center gap-3">
            <div className="relative h-24 w-24 shrink-0">
              <ChartCanvas config={chartConfig} />
            </div>
            <div className="min-w-0 flex-1 space-y-1.5">
              {categoryBreakdown.map((item) => (
                <div key={item.entity_type} className="flex items-center justify-between gap-2 text-xs">
                  <span className="flex min-w-0 items-center gap-1.5 font-medium text-ink dark:text-ink-dark">
                    <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: item.color }} />
                    <span className="truncate capitalize">{item.entity_type}</span>
                  </span>
                  <span className="shrink-0 text-muted dark:text-muted-dark">{item.count}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      <Link to="/knowledge/graph" className="mt-auto block rounded-lg bg-primary/10 px-3 py-1.5 text-center text-sm font-semibold text-primary transition-colors hover:bg-primary/15 dark:text-primary-soft">
        View Knowledge Graph
      </Link>
    </div>
  );
}
