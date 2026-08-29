// Shared skeleton placeholder primitive - a pulsing block sized by the
// caller's className (e.g. "h-4 w-24", "h-9 w-9 rounded-full"). Used
// instead of each page hand-rolling its own `animate-pulse bg-...` div,
// so every skeleton in the app pulses in sync and looks the same.
export default function Skeleton({ className = '' }) {
  return <div className={`animate-pulse rounded-md bg-line/70 dark:bg-white/10 ${className}`} />;
}
