// The one loading mark used everywhere in the app - five short dots
// bouncing up and down in a traveling wave, the classic "typing
// indicator" motion (iMessage/Slack/Discord) rather than a spinning
// ring, each dot squashing/stretching a little at the top of its
// hop for a livelier, more rubbery feel. Pure inline SVG + a couple
// of bespoke keyframes in index.css (no extra dependency, no JS
// animation loop), colored via `currentColor` so a caller controls
// color the same way it controls any other icon - pass a text-*
// class, or nothing to inherit context (e.g. white text inside a
// primary button). `prefers-reduced-motion` drops the bounce for a
// slower opacity fade (handled in index.css) - it never stops
// moving outright, a loading mark should still say "busy".
const DOTS = [
  { x: 2, y: 15.5 },
  { x: 7, y: 15.5 },
  { x: 12, y: 15.5 },
  { x: 17, y: 15.5 },
  { x: 22, y: 15.5 },
];
const RADIUS = 1.9;
const DURATION = 0.8;

export default function Spinner({ size = 20, className = '', label = 'Loading' }) {
  return (
    <span
      role="status"
      aria-label={label}
      className={`inline-block shrink-0 ${className}`}
      style={{ width: size, height: size }}
    >
      <svg viewBox="0 0 24 24" fill="none" className="h-full w-full">
        {DOTS.map((d, i) => (
          <circle
            key={i}
            cx={d.x} cy={d.y} r={RADIUS} fill="currentColor"
            className="spinner-wave-dot"
            style={{
              transformOrigin: `${d.x}px ${d.y}px`,
              animationDelay: `${-(i / DOTS.length) * DURATION}s`,
            }}
          />
        ))}
      </svg>
    </span>
  );
}
