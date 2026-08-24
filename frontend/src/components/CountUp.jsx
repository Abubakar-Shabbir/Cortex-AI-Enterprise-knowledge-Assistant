import { useEffect, useState } from 'react';

// Port of the x-init count-up animation _stat_card.html / _mini_stat_card.html
// use (700ms, requestAnimationFrame).
export default function CountUp({ value }) {
  const target = Number(value) || 0;
  const [display, setDisplay] = useState(0);

  useEffect(() => {
    let start = null;
    let frame;
    const step = (ts) => {
      if (start === null) start = ts;
      const progress = Math.min((ts - start) / 700, 1);
      setDisplay(Math.round(progress * target));
      if (progress < 1) frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [target]);

  return <>{display.toLocaleString()}</>;
}
