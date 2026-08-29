// Port of templates/partials/_toggle_switch.html.
export default function ToggleSwitch({ checked, onChange, title, description, warning }) {
  return (
    <label className="flex items-start justify-between gap-3 text-sm text-ink dark:text-ink-dark">
      <span className="min-w-0">
        <span className="font-medium">{title}</span>
        <span className="mt-0.5 block text-xs text-muted dark:text-muted-dark">
          {description}
          {warning && <span className="font-medium text-warning dark:text-warning-dark"> {warning}</span>}
        </span>
      </span>
      <span className="relative mt-0.5 inline-flex h-5 w-9 shrink-0 cursor-pointer items-center">
        <input
          type="checkbox"
          checked={!!checked}
          onChange={(e) => onChange(e.target.checked)}
          className="peer sr-only"
        />
        <span className="absolute inset-0 rounded-full bg-line transition-colors peer-checked:bg-primary dark:bg-white/10"></span>
        <span className="absolute left-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform peer-checked:translate-x-4"></span>
      </span>
    </label>
  );
}
