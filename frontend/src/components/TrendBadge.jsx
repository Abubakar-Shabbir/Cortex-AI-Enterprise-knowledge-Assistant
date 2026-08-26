import { Minus, TrendingDown, TrendingUp } from 'lucide-react';

// Port of templates/partials/_trend_badge.html.
export default function TrendBadge({ trend, label = 'vs last 7 days' }) {
  if (!trend) return null;

  const colorClass = trend.direction === 'up' ? 'text-success dark:text-success-dark' : trend.direction === 'down' ? 'text-danger dark:text-danger-dark' : 'text-muted dark:text-muted-dark';
  const Icon = trend.direction === 'up' ? TrendingUp : trend.direction === 'down' ? TrendingDown : Minus;

  return (
    <span className={`inline-flex items-center gap-1 text-xs font-semibold ${colorClass}`}>
      <Icon className="h-3.5 w-3.5" />
      {trend.change_pct}%
      <span className="font-normal text-muted dark:text-muted-dark">{label}</span>
    </span>
  );
}
