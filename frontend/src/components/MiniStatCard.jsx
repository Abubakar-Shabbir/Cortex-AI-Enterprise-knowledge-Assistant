import CountUp from './CountUp';

// Port of templates/dashboard/_mini_stat_card.html.
export default function MiniStatCard({ icon: Icon, iconBg = 'bg-primary/10', iconColor = 'text-primary', label, value, numeric = false }) {
  return (
    <div className="min-w-0 rounded-xl border border-line bg-card p-3 shadow-soft transition-transform hover:-translate-y-0.5 dark:border-line-dark dark:bg-card-dark">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium leading-snug text-muted dark:text-muted-dark">{label}</span>
        <div className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg ${iconBg} ${iconColor}`}>
          <Icon className="h-4 w-4" />
        </div>
      </div>
      {numeric ? (
        <div className="mt-2 text-xl font-bold leading-tight tracking-tight text-ink dark:text-ink-dark"><CountUp value={value} /></div>
      ) : (
        <div className="mt-2 text-xl font-bold leading-tight tracking-tight text-ink dark:text-ink-dark">{value}</div>
      )}
    </div>
  );
}
