import { useEffect, useRef } from 'react';
import { Chart, registerables } from 'chart.js';

Chart.register(...registerables);

Chart.defaults.font.family = 'Inter, ui-sans-serif, system-ui, sans-serif';
Chart.defaults.font.size = 11;
Chart.defaults.color = '#8a7d7d';
Chart.defaults.layout.padding = 0;
Chart.defaults.plugins.legend.labels.boxWidth = 9;
Chart.defaults.plugins.legend.labels.boxHeight = 9;
Chart.defaults.plugins.legend.labels.usePointStyle = true;
Chart.defaults.plugins.legend.labels.padding = 10;

// Thin imperative wrapper around Chart.js (npm dependency, replacing
// the CDN <script> the Django templates use) - takes the exact
// {type, data, options} config object a chart definition would pass
// to `new Chart(ctx, config)`, and re-creates the chart whenever it
// changes.
export default function ChartCanvas({ config, className }) {
  const canvasRef = useRef(null);
  const chartRef = useRef(null);

  useEffect(() => {
    if (!canvasRef.current) return undefined;
    chartRef.current = new Chart(canvasRef.current, config);
    return () => chartRef.current?.destroy();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(config)]);

  return <canvas ref={canvasRef} className={className}></canvas>;
}
