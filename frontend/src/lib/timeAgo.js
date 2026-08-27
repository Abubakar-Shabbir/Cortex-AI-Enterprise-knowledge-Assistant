const UNITS = [
  ['year', 31536000],
  ['month', 2592000],
  ['week', 604800],
  ['day', 86400],
  ['hour', 3600],
  ['minute', 60],
];

function coarseDuration(totalSeconds) {
  const seconds = Math.max(0, Math.floor(totalSeconds));

  for (const [name, secondsInUnit] of UNITS) {
    const count = Math.floor(seconds / secondsInUnit);
    if (count >= 1) return `${count} ${name}${count === 1 ? '' : 's'}`;
  }
  return 'less than a minute';
}

// Lightweight approximation of Django's {{ x|timesince }} filter -
// coarse, human-readable relative time, biggest unit only (matches
// what every ported template used it for: "3 hours ago", not a
// precise duration). Only meaningful for a *past* isoString - a
// future one (e.g. a session's expire_date) always reads as elapsed
// zero, which is why timeUntil() below exists as its mirror image
// rather than callers passing a future date in here.
export function timeAgo(isoString) {
  const then = new Date(isoString).getTime();
  return coarseDuration((Date.now() - then) / 1000);
}

// Mirror of timeAgo() for a *future* isoString - "expires in 45
// minutes" rather than "45 minutes ago". Reusing timeAgo() for a
// future date silently floors to "0 minutes" regardless of how far
// out it actually is, since Date.now() - then is negative and gets
// clamped; this computes the duration the other direction instead.
export function timeUntil(isoString) {
  const then = new Date(isoString).getTime();
  return coarseDuration((then - Date.now()) / 1000);
}
