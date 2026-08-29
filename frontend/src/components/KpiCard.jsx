import { Minus, TrendingDown, TrendingUp } from 'lucide-react';
import CountUp from './CountUp';
import ChartCanvas from './ChartCanvas';

// Port of templates/dashboard/_kpi_card.html - Admin Overview's KPI
// cards (icon, big number, trend badge, and a real Chart.js sparkline
// from a 7-point daily series), distinct from the chart-free
// MiniStatCard User Overview uses.
export default function KpiCard({ icon: Icon, iconBg, iconColor, label, value, numeric = false, trend, trendLabel, chartColor }) {
  const sparklineConfig = trend?.has_activity
    ? {
        type: 'line',
        data: {
          labels: (trend.sparkline || []).map((_, i) => i),
          datasets: [{
            data: trend.sparkline,
            borderColor: chartColor,
            backgroundColor: (context) => {
              const { ctx, chartArea } = context.chart;
              if (!chartArea) return null;
              const gradient = ctx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
              gradient.addColorStop(0, `${chartColor}33`);
              gradient.addColorStop(1, `${chartColor}00`);
              return gradient;
            },
            tension: 0.4,
            pointRadius: 0,
            pointHoverRadius: 3,
            pointHoverBackgroundColor: chartColor,
            borderWidth: 2,
            fill: true,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: { intersect: false, mode: 'index' },
          plugins: {
            legend: { display: false },
            tooltip: { displayColors: false, bodyFont: { size: 10 }, padding: 6, callbacks: { title: () => '' } },
          },
          scales: { x: { display: false }, y: { display: false } },
          elements: { line: { capBezierPoints: true } },
        },
      }
    : null;

  return (
    <div className="min-w-0 rounded-xl border border-line bg-card p-3 shadow-soft transition-transform hover:-translate-y-0.5 dark:border-line-dark dark:bg-card-dark">
      <div className="flex items-center justify-between">
        <div className={`flex h-7 w-7 items-center justify-center rounded-lg ${iconBg} ${iconColor}`}>
          <Icon className="h-4 w-4" />
        </div>
      </div>

      <div className="mt-2 text-xs font-medium leading-snug text-muted dark:text-muted-dark">{label}</div>

      {numeric ? (
        <div className="mt-0.5 text-xl font-bold leading-tight tracking-tight text-ink dark:text-ink-dark"><CountUp value={value} /></div>
      ) : (
        <div className="mt-0.5 text-xl font-bold leading-tight tracking-tight text-ink dark:text-ink-dark">{value}</div>
      )}

      <div className="mt-2 flex items-end justify-between gap-2">
        <div className="flex items-center gap-1 text-xs font-medium">
          {trend?.direction === 'up' ? (
            <>
              <TrendingUp className="h-3.5 w-3.5 text-success dark:text-success-dark" />
              <span className="text-success dark:text-success-dark">{trend.change_pct}%</span>
            </>
          ) : trend?.direction === 'down' ? (
            <>
              <TrendingDown className="h-3.5 w-3.5 text-danger dark:text-danger-dark" />
              <span className="text-danger dark:text-danger-dark">{trend.change_pct}%</span>
            </>
          ) : (
            <>
              <Minus className="h-3.5 w-3.5 text-muted dark:text-muted-dark" />
              <span className="text-muted dark:text-muted-dark">0%</span>
            </>
          )}
          <span className="text-muted dark:text-muted-dark">{trendLabel}</span>
        </div>

        {sparklineConfig ? (
          <div className="relative h-6 w-14 shrink-0">
            <ChartCanvas config={sparklineConfig} />
          </div>
        ) : (
          <div className="flex h-6 w-14 shrink-0 items-center" title="No activity in this period yet">
            <div className="h-px w-full rounded-full bg-line dark:bg-line-dark" />
          </div>
        )}
      </div>
    </div>
  );
}
