import Spinner from './Spinner';

/**
 * The app's shared loading indicator, in four flavors - always the
 * same Spinner mark, never a fake delay, always tied to a real
 * isLoading/isPending/isFetching flag from the caller.
 *
 * variant="fullscreen" - full-viewport, used only before any layout
 *   exists yet (the auth gate in App.jsx). Never used inside a page.
 * variant="page"       - fills the content area under the sidebar/
 *   topbar, which stay mounted and visible - the page's own chrome is
 *   never hidden, only the not-yet-loaded content region.
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
    return <Spinner size={size || 16} label={subtitle} />;
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
        <Spinner size={size || 22} className="text-primary dark:text-primary-soft" label={subtitle} />
        <span className="sr-only">{subtitle}</span>
      </div>
    );
  }

  const shell =
    variant === 'fullscreen'
      ? 'fixed inset-0 z-[100] flex items-center justify-center bg-surface dark:bg-surface-dark'
      : 'flex min-h-[40vh] w-full items-center justify-center py-16';

  return (
    <div className={shell} role="status" aria-live="polite" aria-busy="true" aria-label={subtitle}>
      <Spinner
        size={size || 32}
        className="text-primary drop-shadow-[0_0_10px_rgba(139,30,45,0.25)] dark:text-primary-soft dark:drop-shadow-[0_0_10px_rgba(231,200,204,0.15)]"
        label={subtitle}
      />
      <span className="sr-only">{subtitle}</span>
    </div>
  );
}
