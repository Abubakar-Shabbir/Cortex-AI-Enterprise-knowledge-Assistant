// Port of templates/partials/_page_header.html.
export default function PageHeader({ title, subtitle }) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-ink dark:text-ink-dark">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-muted dark:text-muted-dark">{subtitle}</p>}
      </div>
    </div>
  );
}
