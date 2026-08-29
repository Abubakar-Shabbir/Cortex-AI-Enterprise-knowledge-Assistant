import { Link } from 'react-router-dom';
import {
  Activity, CheckCircle2, Compass, Database, FileUp, Gauge, GitBranch, HardDrive, MessageSquare, PieChart, Sparkles, Timer,
} from 'lucide-react';
import PageHeader from '../components/PageHeader';
import StatCard from '../components/StatCard';
import EmptyState from '../components/EmptyState';
import ChartCanvas from '../components/ChartCanvas';
import PageSkeleton from '../components/PageSkeleton';
import { useAnalytics } from '../api/hooks';

const GRID_COLOR = 'rgba(109, 102, 101, 0.10)';
const TICK_COLOR = '#8a7d7d';
const PRIMARY = '#8B1E2D';
const WINE = '#6D1B27';
const ROSE = '#A6333F';
const INFO = '#2A78D6';
const SUCCESS = '#1F7A4D';
const WARNING = '#C77700';
const ACCENT = '#4A3AA7';
const PALETTE = [PRIMARY, INFO, SUCCESS, WARNING, ACCENT, ROSE, '#0F9B8E', '#D6336C'];
const STORAGE_COLOR_MAP = { PDF: PRIMARY, DOCX: WARNING, TXT: SUCCESS };
const AI_TASK_STATUS_COLOR_MAP = { Completed: SUCCESS, Failed: PRIMARY, Running: WARNING, Pending: TICK_COLOR, Cancelled: '#A9989A' };

// Port of templates/analytics.html - every Chart.js definition ported
// 1:1 (same types, colors, scales), now driven by React state /
// ChartCanvas instead of CDN Chart.js + json_script-read globals.
export default function Analytics() {
  const { data: payload, isLoading } = useAnalytics();

  if (isLoading || !payload) return <PageSkeleton variant="grid" />;

  const { data, ai_performance: aiPerformance, document_types: documentTypes, can_view_ai_tasks: canViewAiTasks, can_view_knowledge_base: canViewKnowledgeBase } = payload;

  const chunkLabels = data.chunk_labels.length ? data.chunk_labels : ['No documents yet'];
  const chunkValues = data.chunk_values.length ? data.chunk_values : [0];

  return (
    <>
      <PageHeader title="Analytics" subtitle="Usage trends across your document library and question activity, last 14 days." />

      <div className="mb-4 flex flex-wrap gap-3">
        <div className="min-w-[190px] flex-1"><StatCard icon={MessageSquare} label="Questions (14d)" value={data.total_questions} numeric /></div>
        <div className="min-w-[190px] flex-1"><StatCard icon={FileUp} label="Uploads (14d)" value={data.total_uploads} numeric /></div>
        <div className="min-w-[190px] flex-1"><StatCard icon={Timer} label="Average Response Time" value={data.avg_response_time} /></div>
        <div className="min-w-[190px] flex-1"><StatCard icon={HardDrive} label="Storage Used" value={data.total_storage} /></div>
        {canViewAiTasks && <div className="min-w-[190px] flex-1"><StatCard icon={Sparkles} label="AI Task Runs (14d)" value={data.total_ai_task_runs} numeric /></div>}
        {canViewKnowledgeBase && (
          <>
            <div className="min-w-[190px] flex-1"><StatCard icon={Compass} label="Topics" value={data.total_topics} numeric /></div>
            <div className="min-w-[190px] flex-1"><StatCard icon={GitBranch} label="Relationships" value={data.total_relationships} numeric /></div>
          </>
        )}
      </div>

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
        <div className="rounded-xl border border-line bg-card p-4 shadow-soft dark:border-line-dark dark:bg-card-dark xl:col-span-2">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-ink dark:text-ink-dark">Activity Overview</h2>
            <span className="text-[11px] text-muted dark:text-muted-dark">Documents uploaded (bars) vs. questions asked (line)</span>
          </div>
          <div className="h-64">
            <ChartCanvas config={{
              data: {
                labels: data.labels,
                datasets: [
                  { type: 'bar', label: 'Documents Uploaded', data: data.uploads_series, backgroundColor: `${INFO}CC`, borderRadius: 4, maxBarThickness: 22, yAxisID: 'y1', order: 2 },
                  { type: 'line', label: 'Questions Asked', data: data.questions_series, borderColor: PRIMARY, backgroundColor: PRIMARY, tension: 0.35, pointRadius: 2, pointBackgroundColor: PRIMARY, borderWidth: 2.5, yAxisID: 'y', order: 1 },
                ],
              },
              options: {
                responsive: true, maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: { legend: { position: 'top', align: 'end' } },
                scales: {
                  x: { grid: { display: false }, ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 7 } },
                  y: { position: 'left', grid: { color: GRID_COLOR }, beginAtZero: true, ticks: { precision: 0 }, title: { display: true, text: 'Questions', font: { size: 10 } } },
                  y1: { position: 'right', grid: { display: false }, beginAtZero: true, ticks: { precision: 0 }, title: { display: true, text: 'Uploads', font: { size: 10 } } },
                },
              },
            }} />
          </div>
        </div>

        <div className="rounded-xl border border-line bg-card p-4 shadow-soft dark:border-line-dark dark:bg-card-dark xl:col-span-2">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-ink dark:text-ink-dark">Confidence &amp; Response Time Correlation</h2>
            <span className="text-[11px] text-muted dark:text-muted-dark">Daily average, dual-axis</span>
          </div>
          <div className="h-64">
            <ChartCanvas config={{
              type: 'line',
              data: {
                labels: data.labels,
                datasets: [
                  { label: 'Confidence %', data: data.confidence_series, borderColor: SUCCESS, backgroundColor: SUCCESS, tension: 0.35, pointRadius: 2, borderWidth: 2.5, spanGaps: true, yAxisID: 'y' },
                  { label: 'Response Time (ms)', data: data.response_time_series, borderColor: ACCENT, backgroundColor: ACCENT, tension: 0.35, pointRadius: 2, borderWidth: 2.5, spanGaps: true, yAxisID: 'y1', borderDash: [4, 3] },
                ],
              },
              options: {
                responsive: true, maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: { legend: { position: 'top', align: 'end' } },
                scales: {
                  x: { grid: { display: false }, ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 7 } },
                  y: { position: 'left', grid: { color: GRID_COLOR }, beginAtZero: true, max: 100, ticks: { callback: (v) => `${v}%` } },
                  y1: { position: 'right', grid: { display: false }, beginAtZero: true, ticks: { callback: (v) => `${v}ms` } },
                },
              },
            }} />
          </div>
        </div>

        <div className="rounded-xl border border-line bg-card p-4 shadow-soft dark:border-line-dark dark:bg-card-dark">
          <h2 className="mb-2 text-sm font-semibold text-ink dark:text-ink-dark">Search Type Usage</h2>
          <div className="h-56">
            <ChartCanvas config={{
              type: 'polarArea',
              data: { labels: data.search_type_labels, datasets: [{ data: data.search_type_values, backgroundColor: PALETTE.map((c) => `${c}B3`), borderColor: PALETTE, borderWidth: 1.5 }] },
              options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom' } }, scales: { r: { grid: { color: GRID_COLOR }, ticks: { display: false } } } },
            }} />
          </div>
        </div>

        <div className="rounded-xl border border-line bg-card p-4 shadow-soft dark:border-line-dark dark:bg-card-dark">
          <h2 className="mb-2 text-sm font-semibold text-ink dark:text-ink-dark">Confidence Distribution</h2>
          <div className="h-56">
            <ChartCanvas config={{
              type: 'bar',
              data: { labels: data.confidence_distribution_labels, datasets: [{ data: data.confidence_distribution_values, backgroundColor: data.confidence_distribution_colors, borderRadius: 6, maxBarThickness: 40 }] },
              options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { grid: { display: false }, ticks: { font: { size: 9 } } }, y: { grid: { color: GRID_COLOR }, beginAtZero: true, ticks: { precision: 0 } } } },
            }} />
          </div>
        </div>

        <div className="rounded-xl border border-line bg-card p-4 shadow-soft dark:border-line-dark dark:bg-card-dark">
          <h2 className="mb-2 text-sm font-semibold text-ink dark:text-ink-dark">Chunk Distribution by Document</h2>
          <div className="h-56">
            <ChartCanvas config={{
              type: 'bar',
              data: { labels: chunkLabels, datasets: [{ data: chunkValues, backgroundColor: chunkValues.map((_, i) => PALETTE[i % PALETTE.length]), borderRadius: 6, maxBarThickness: 22 }] },
              options: { indexAxis: 'y', responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { grid: { color: GRID_COLOR }, beginAtZero: true, ticks: { precision: 0 } }, y: { grid: { display: false }, ticks: { font: { size: 10 } } } } },
            }} />
          </div>
        </div>

        <div className="rounded-xl border border-line bg-card p-4 shadow-soft dark:border-line-dark dark:bg-card-dark">
          <h2 className="mb-2 text-sm font-semibold text-ink dark:text-ink-dark">Storage Usage by File Type</h2>
          <div className="h-56">
            <ChartCanvas config={{
              type: 'bar',
              data: { labels: data.storage_type_labels, datasets: [{ label: 'Bytes', data: data.storage_type_values, backgroundColor: data.storage_type_labels.map((l) => STORAGE_COLOR_MAP[l] || WINE), borderRadius: 6, maxBarThickness: 36 }] },
              options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { grid: { display: false } }, y: { grid: { color: GRID_COLOR }, beginAtZero: true } } },
            }} />
          </div>
        </div>

        <div className="rounded-xl border border-line bg-card p-4 shadow-soft dark:border-line-dark dark:bg-card-dark">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-ink dark:text-ink-dark">Weekday Activity</h2>
            <span className="text-[11px] text-muted dark:text-muted-dark">Questions asked per weekday, last 90 days</span>
          </div>
          <div className="mx-auto h-56 max-w-xs">
            <ChartCanvas config={{
              type: 'radar',
              data: { labels: data.weekday_labels, datasets: [{ label: 'Questions', data: data.weekday_values, borderColor: PRIMARY, backgroundColor: `${PRIMARY}33`, pointBackgroundColor: PRIMARY, borderWidth: 2 }] },
              options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { r: { grid: { color: GRID_COLOR }, angleLines: { color: GRID_COLOR }, beginAtZero: true, ticks: { precision: 0, backdropColor: 'transparent' } } } },
            }} />
          </div>
        </div>

        <div className="rounded-xl border border-line bg-card p-3 shadow-soft dark:border-line-dark dark:bg-card-dark">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-ink dark:text-ink-dark">Document Types</h2>
            <Link to="/documents" className="text-xs font-medium text-primary hover:underline dark:text-primary-soft">View all</Link>
          </div>

          {documentTypes.breakdown.length > 0 ? (
            <>
              <div className="relative mx-auto h-24 w-24">
                <ChartCanvas config={{
                  type: 'doughnut',
                  data: { labels: documentTypes.breakdown.map((i) => i.type), datasets: [{ data: documentTypes.breakdown.map((i) => i.count), backgroundColor: documentTypes.breakdown.map((i) => i.color), borderWidth: 0 }] },
                  options: { responsive: true, maintainAspectRatio: false, cutout: '72%', plugins: { legend: { display: false } } },
                }} />
                <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
                  <span className="text-lg font-bold leading-tight text-ink dark:text-ink-dark">{documentTypes.total}</span>
                  <span className="text-xs text-muted dark:text-muted-dark">Total</span>
                </div>
              </div>

              <div className="mt-2.5 space-y-1.5">
                {documentTypes.breakdown.map((item) => (
                  <div key={item.type} className="flex items-center justify-between text-xs">
                    <span className="flex items-center gap-2 font-medium text-ink dark:text-ink-dark">
                      <span className="h-2 w-2 rounded-full" style={{ backgroundColor: item.color }}></span>
                      {item.type}
                    </span>
                    <span className="text-muted dark:text-muted-dark">{item.percent}% ({item.count})</span>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <EmptyState icon={PieChart} title="No documents yet" message="Upload a document to see its type breakdown here." actionTo="/documents" actionLabel="Go to Documents" />
          )}
        </div>

        {canViewAiTasks && (
          <>
            <div className="rounded-xl border border-line bg-card p-4 shadow-soft dark:border-line-dark dark:bg-card-dark">
              <div className="mb-2 flex items-center justify-between">
                <h2 className="text-sm font-semibold text-ink dark:text-ink-dark">AI Tasks Activity</h2>
                <span className="text-[11px] text-muted dark:text-muted-dark">Runs/day (14d)</span>
              </div>
              <div className="h-56">
                <ChartCanvas config={{
                  type: 'bar',
                  data: { labels: data.labels, datasets: [{ data: data.ai_task_runs_series, backgroundColor: `${ACCENT}CC`, borderRadius: 4, maxBarThickness: 22 }] },
                  options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { grid: { display: false }, ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 7 } }, y: { grid: { color: GRID_COLOR }, beginAtZero: true, ticks: { precision: 0 } } } },
                }} />
              </div>
            </div>

            <div className="rounded-xl border border-line bg-card p-4 shadow-soft dark:border-line-dark dark:bg-card-dark">
              <h2 className="mb-2 text-sm font-semibold text-ink dark:text-ink-dark">AI Task Status</h2>
              <div className="h-56">
                <ChartCanvas config={{
                  type: 'doughnut',
                  data: { labels: data.ai_task_status_labels, datasets: [{ data: data.ai_task_status_values, backgroundColor: data.ai_task_status_labels.map((l) => AI_TASK_STATUS_COLOR_MAP[l] || ACCENT), borderWidth: 0 }] },
                  options: { responsive: true, maintainAspectRatio: false, cutout: '65%', plugins: { legend: { position: 'bottom' } } },
                }} />
              </div>
            </div>
          </>
        )}
      </div>

      <div className="mt-3 rounded-xl border border-line bg-card p-4 shadow-soft dark:border-line-dark dark:bg-card-dark">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-ink dark:text-ink-dark">AI Performance</h2>
          <span className="text-[11px] text-muted dark:text-muted-dark">Ask AI + AI Tasks, from every request/run's execution trace</span>
        </div>

        {aiPerformance.has_data ? (
          <>
            <div className="mb-4 flex flex-wrap gap-3">
              <div className="min-w-[150px] flex-1"><StatCard icon={Activity} label="Total Requests" value={aiPerformance.total_requests} numeric /></div>
              <div className="min-w-[150px] flex-1"><StatCard icon={CheckCircle2} label="Success Rate" value={aiPerformance.success_rate} sublabel="percent" /></div>
              <div className="min-w-[150px] flex-1"><StatCard icon={Timer} label="Avg Latency" value={aiPerformance.avg_latency_ms} sublabel="ms" /></div>
              <div className="min-w-[150px] flex-1"><StatCard icon={Gauge} label="P95 Latency" value={aiPerformance.p95_latency_ms} sublabel="ms" /></div>
              <div className="min-w-[150px] flex-1"><StatCard icon={GitBranch} label="Fallback Rate" value={aiPerformance.fallback_rate} sublabel="percent" /></div>
              {aiPerformance.cache_hit_rate !== null && aiPerformance.cache_hit_rate !== undefined && (
                <div className="min-w-[150px] flex-1"><StatCard icon={Database} label="Cache Hit Rate" value={aiPerformance.cache_hit_rate} sublabel="percent" /></div>
              )}
            </div>

            <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
              <div>
                <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted dark:text-muted-dark">Latency Percentiles</p>
                <div className="overflow-hidden rounded-lg border border-line dark:border-line-dark">
                  <table className="w-full text-left text-xs">
                    <tbody className="divide-y divide-line dark:divide-line-dark">
                      <tr><td className="px-3 py-2 text-muted dark:text-muted-dark">P50 (median)</td><td className="px-3 py-2 text-right font-medium text-ink dark:text-ink-dark">{aiPerformance.p50_latency_ms} ms</td></tr>
                      <tr><td className="px-3 py-2 text-muted dark:text-muted-dark">P95</td><td className="px-3 py-2 text-right font-medium text-ink dark:text-ink-dark">{aiPerformance.p95_latency_ms} ms</td></tr>
                      <tr><td className="px-3 py-2 text-muted dark:text-muted-dark">P99</td><td className="px-3 py-2 text-right font-medium text-ink dark:text-ink-dark">{aiPerformance.p99_latency_ms} ms</td></tr>
                    </tbody>
                  </table>
                </div>
              </div>

              <div>
                <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted dark:text-muted-dark">Provider Success Rate</p>
                <div className="overflow-hidden rounded-lg border border-line dark:border-line-dark">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-surface dark:bg-white/5">
                      <tr><th className="px-3 py-2 font-semibold text-muted dark:text-muted-dark">Provider</th><th className="px-3 py-2 text-right font-semibold text-muted dark:text-muted-dark">Requests</th><th className="px-3 py-2 text-right font-semibold text-muted dark:text-muted-dark">Success</th></tr>
                    </thead>
                    <tbody className="divide-y divide-line dark:divide-line-dark">
                      {aiPerformance.provider_stats.length > 0 ? aiPerformance.provider_stats.map((row) => (
                        <tr key={row.provider}>
                          <td className="px-3 py-2 text-ink dark:text-ink-dark">{row.provider}</td>
                          <td className="px-3 py-2 text-right text-muted dark:text-muted-dark">{row.total}</td>
                          <td className={`px-3 py-2 text-right font-medium ${row.success_rate >= 90 ? 'text-success dark:text-success-dark' : row.success_rate >= 50 ? 'text-warning' : 'text-danger dark:text-danger-dark'}`}>{row.success_rate}%</td>
                        </tr>
                      )) : <tr><td colSpan={3} className="px-3 py-2 text-muted dark:text-muted-dark">No provider data yet.</td></tr>}
                    </tbody>
                  </table>
                </div>
              </div>

              <div>
                <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted dark:text-muted-dark">Slowest Pipeline Stage</p>
                <div className="overflow-hidden rounded-lg border border-line dark:border-line-dark">
                  <table className="w-full text-left text-xs">
                    <tbody className="divide-y divide-line dark:divide-line-dark">
                      {aiPerformance.bottleneck_breakdown.length > 0 ? aiPerformance.bottleneck_breakdown.map((row) => (
                        <tr key={row.bottleneck_label}><td className="px-3 py-2 text-ink dark:text-ink-dark">{row.bottleneck_label}</td><td className="px-3 py-2 text-right text-muted dark:text-muted-dark">{row.count} request(s)</td></tr>
                      )) : <tr><td className="px-3 py-2 text-muted dark:text-muted-dark">No data yet.</td></tr>}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            {aiPerformance.error_breakdown.length > 0 && (
              <div className="mt-4">
                <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted dark:text-muted-dark">Most Common Errors</p>
                <div className="flex flex-wrap gap-2">
                  {aiPerformance.error_breakdown.map((row) => (
                    <span key={row.error_type} className="rounded-full border border-danger/30 bg-danger/5 px-2.5 py-1 text-xs text-danger dark:border-danger-dark/30 dark:bg-danger/10 dark:text-danger-dark">{row.error_type} · {row.count}</span>
                  ))}
                </div>
              </div>
            )}
          </>
        ) : (
          <EmptyState icon={Activity} title="Not enough data yet" message="AI Performance fills in once Ask AI questions or AI Task runs have gone through the pipeline." />
        )}
      </div>
    </>
  );
}
