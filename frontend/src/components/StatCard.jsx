import CountUp from './CountUp';

// Port of templates/partials/_stat_card.html.
export default function StatCard({ icon: Icon, label, value, numeric = false }) {
  return (
    <div className="group rounded-xl border border-line bg-card p-5 shadow-soft transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/30 hover:shadow-soft dark:border-line-dark dark:bg-card-dark dark:hover:border-primary-soft/30">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-muted dark:text-muted-dark">{label}</span>
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary-soft/50 text-primary transition-transform duration-200 group-hover:scale-105 dark:bg-primary/15 dark:text-primary-soft">
          <Icon className="h-4 w-4" />
        </div>
      </div>
      {numeric ? (
        <div className="mt-3 text-2xl font-bold tracking-tight text-ink dark:text-ink-dark"><CountUp value={value} /></div>
      ) : (
        <div className="mt-3 truncate text-2xl font-bold tracking-tight text-ink dark:text-ink-dark" title={value}>{value}</div>
      )}
    </div>
  );
}
