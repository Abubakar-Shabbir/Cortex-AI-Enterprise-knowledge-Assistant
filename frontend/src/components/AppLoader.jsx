import Spinner from './Spinner';

/**
 * The app's shared *spinner*-based loading indicator, for the cases
 * that are genuinely spinner cases (not initial content loading, which
 * uses PageSkeleton instead - see components/PageSkeleton.jsx). Always
 * the same Spinner mark, never a fake delay, always tied to a real
 * isLoading/isPending/isFetching flag from the caller.
 *
 * variant="fullscreen" - full-viewport, used only before any layout
 *   exists yet (the auth gate in App.jsx). Never used inside a page.
 * variant="overlay"    - absolutely positioned over a `relative`
 *   parent (a card/table/panel already showing its previous data) -
 *   for a background refetch that shouldn't blank what's already on
 *   screen. Parent must add `relative` (and usually keep rendering its
 *   stale content dimmed underneath).
 * variant="inline"     - just the bare mark, sized to sit inside a
 *   button, table cell, or next to a label.
 */
export default function AppLoader({ variant = 'fullscreen', subtitle = 'Loading…', size }) {
  if (variant === 'inline') {
    return <Spinner size={size || 20} label={subtitle} />;
  }

  if (variant === 'overlay') {
    return (
      <div
        className="absolute inset-0 z-10 flex items-center justify-center rounded-[inherit] bg-card/70 backdrop-blur-[1px] dark:bg-card-dark/70"
        role="status"
        aria-live="polite"
        aria-busy="true"
        aria-label={subtitle}
      >
        <Spinner size={size || 38} className="text-primary dark:text-primary-soft" label={subtitle} />
        <span className="sr-only">{subtitle}</span>
      </div>
    );
  }

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-surface dark:bg-surface-dark"
      role="status"
      aria-live="polite"
      aria-busy="true"
      aria-label={subtitle}
    >
      <div className="flex flex-col items-center gap-4">
        <Spinner size={size || 80} className="text-primary dark:text-primary-soft" label={subtitle} />
        <p className="text-sm font-medium text-muted dark:text-muted-dark">{subtitle}</p>
      </div>
    </div>
  );
}
