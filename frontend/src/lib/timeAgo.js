// Lightweight approximation of Django's {{ x|timesince }} filter -
// coarse, human-readable relative time, biggest unit only (matches
// what every ported template used it for: "3 hours ago", not a
// precise duration).
export function timeAgo(isoString) {
  const then = new Date(isoString).getTime();
  const seconds = Math.max(0, Math.floor((Date.now() - then) / 1000));

  const units = [
    ['year', 31536000],
    ['month', 2592000],
    ['week', 604800],
    ['day', 86400],
    ['hour', 3600],
    ['minute', 60],
  ];

  for (const [name, secondsInUnit] of units) {
    const count = Math.floor(seconds / secondsInUnit);
    if (count >= 1) return `${count} ${name}${count === 1 ? '' : 's'}`;
  }
  return '0 minutes';
}
