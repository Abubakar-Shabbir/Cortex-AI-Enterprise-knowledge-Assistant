// Port of templates/partials/_logo.html's colored-badge variant (the
// only variant used anywhere in the pages this migration covers).
export default function Logo({ size = 'h-8 w-8' }) {
  return (
    <svg viewBox="0 0 32 32" className={size} xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Cortex">
      <rect width="32" height="32" rx="8" fill="currentColor"></rect>
      <g stroke="white" strokeWidth="1.5" strokeLinecap="round" opacity="0.95">
        <line x1="16" y1="7" x2="8" y2="22"></line>
        <line x1="16" y1="7" x2="24" y2="22"></line>
        <line x1="8" y1="22" x2="24" y2="22"></line>
      </g>
      <circle cx="16" cy="7" r="3" fill="white"></circle>
      <circle cx="8" cy="22" r="3" fill="white"></circle>
      <circle cx="24" cy="22" r="3" fill="white"></circle>
    </svg>
  );
}
