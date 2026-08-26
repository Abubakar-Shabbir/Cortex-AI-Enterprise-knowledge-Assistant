// The one circular loading mark used everywhere in the app - a thin
// static ring plus a rotating, rounded-cap arc (the "comet tail" look
// modern products like Linear/Vercel use), not a plain CSS
// border-spinner. Pure inline SVG + Tailwind's built-in `animate-spin`
// (no extra dependency, no JS animation loop), colored via
// `currentColor` so a caller controls color the same way it controls
// any other icon - pass a text-* class, or nothing to inherit context
// (e.g. white text inside a primary button).
export default function Spinner({ size = 20, className = '', label = 'Loading' }) {
  return (
    <span
      role="status"
      aria-label={label}
      className={`inline-block shrink-0 animate-spin motion-reduce:animate-[spin_1.5s_linear_infinite] ${className}`}
      style={{ width: size, height: size }}
    >
      <svg viewBox="0 0 24 24" fill="none" className="h-full w-full">
        <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2.5" className="opacity-[0.15]" />
        <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeDasharray="15.7 62.8" />
      </svg>
    </span>
  );
}
