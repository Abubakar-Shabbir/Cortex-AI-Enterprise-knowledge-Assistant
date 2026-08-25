/**
 * Minimal page/boot loader — small circle spinner only.
 * variant="fullscreen" | "page"
 */
export default function AppLoader({
  variant = 'fullscreen',
  subtitle = 'Loading…',
}) {
  const shell =
    variant === 'fullscreen'
      ? 'fixed inset-0 z-[100] flex items-center justify-center bg-surface dark:bg-surface-dark'
      : 'flex min-h-[40vh] w-full items-center justify-center py-16';

  return (
    <div
      className={shell}
      role="status"
      aria-live="polite"
      aria-busy="true"
      aria-label={subtitle}
    >
      <span
        className="h-7 w-7 animate-spin rounded-full border-2 border-line border-t-primary dark:border-line-dark dark:border-t-primary-soft"
        aria-hidden="true"
      />
      <span className="sr-only">{subtitle}</span>
    </div>
  );
}
