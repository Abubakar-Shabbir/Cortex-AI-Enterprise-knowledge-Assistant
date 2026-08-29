import { Compass, Download, FileText, Minus, MessageSquare, Sparkles, TrendingDown, TrendingUp } from 'lucide-react';
import PageHeader from '../components/PageHeader';
import TrendBadge from '../components/TrendBadge';
import PageSkeleton from '../components/PageSkeleton';
import { getApiBaseUrl } from '../api/client';
import { useReports } from '../api/hooks';

function pluralize(count, word) {
  return `${word}${count === 1 ? '' : 's'}`;
}

const DIRECTION_ICON = { up: TrendingUp, down: TrendingDown };
const DIRECTION_CLASS = { up: 'text-success dark:text-success-dark', down: 'text-danger dark:text-danger-dark' };
const DIRECTION_BAR_CLASS = { up: 'bg-success', down: 'bg-danger' };

// Port of templates/reports.html.
export default function Reports() {
  const { data, isLoading } = useReports();

  if (isLoading || !data) return <PageSkeleton variant="detail" />;

  const {
    document_count: documentCount, total_storage: totalStorage, question_count: questionCount,
    ai_task_run_count: aiTaskRunCount, topic_count: topicCount, comparison, kpi_trends: kpiTrends,
    document_types: documentTypes, can_view_ai_tasks: canViewAiTasks, can_view_knowledge_base: canViewKnowledgeBase,
  } = data;

  const base = getApiBaseUrl();

  return (
    <>
      <PageHeader title="Reports" subtitle="Export your data as CSV for offline analysis, or compare this period against the last right here." />

      <div className="flex flex-wrap gap-4">
        <div className="flex min-w-[280px] flex-1 flex-col rounded-xl border border-line bg-card p-5 shadow-soft dark:border-line-dark dark:bg-card-dark">
          <div className="flex items-start justify-between">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary-soft/50 text-primary dark:bg-primary/15 dark:text-primary-soft">
              <FileText className="h-5 w-5" />
            </div>
            <div className="text-right">
              <div className="text-xl font-bold tracking-tight text-ink dark:text-ink-dark">{documentCount}</div>
              <div className="text-[11px] text-muted dark:text-muted-dark">{pluralize(documentCount, 'document')} · {totalStorage}</div>
            </div>
          </div>
          <h2 className="mt-3 text-sm font-semibold text-ink dark:text-ink-dark">Document Report</h2>
          <p className="mt-1 text-xs text-muted dark:text-muted-dark">Every document you've uploaded — title, type, size, chunk count, and upload date.</p>

          {documentTypes.breakdown.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {documentTypes.breakdown.map((item) => (
                <span key={item.type} className="inline-flex items-center gap-1 rounded-full bg-line/50 px-2 py-0.5 text-[11px] font-medium text-ink dark:bg-white/5 dark:text-ink-dark">
                  <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: item.color }}></span>
                  {item.type} {item.percent}%
                </span>
              ))}
            </div>
          )}

          <div className="mt-auto flex items-center justify-between pt-4">
            <TrendBadge trend={kpiTrends.documents} />
            <a href={`${base}/api/reports/documents.csv`} className="ml-auto inline-flex items-center gap-2 rounded-lg border border-line px-3.5 py-2 text-sm font-medium text-ink transition-colors hover:border-primary/30 hover:bg-primary/5 hover:text-primary dark:border-line-dark dark:text-ink-dark dark:hover:bg-primary/10">
              <Download className="h-4 w-4" /> Export CSV
            </a>
          </div>
        </div>

        <div className="flex min-w-[280px] flex-1 flex-col rounded-xl border border-line bg-card p-5 shadow-soft dark:border-line-dark dark:bg-card-dark">
          <div className="flex items-start justify-between">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary-soft/50 text-primary dark:bg-primary/15 dark:text-primary-soft">
              <MessageSquare className="h-5 w-5" />
            </div>
            <div className="text-right">
              <div className="text-xl font-bold tracking-tight text-ink dark:text-ink-dark">{questionCount}</div>
              <div className="text-[11px] text-muted dark:text-muted-dark">{pluralize(questionCount, 'question')} logged</div>
            </div>
          </div>
          <h2 className="mt-3 text-sm font-semibold text-ink dark:text-ink-dark">Usage &amp; AI Report</h2>
          <p className="mt-1 text-xs text-muted dark:text-muted-dark">Every question you've asked — the answer, search method, confidence, and response time.</p>

          <div className="mt-auto flex items-center justify-between pt-4">
            <TrendBadge trend={kpiTrends.queries} label="vs yesterday" />
            <a href={`${base}/api/reports/usage.csv`} className="ml-auto inline-flex items-center gap-2 rounded-lg border border-line px-3.5 py-2 text-sm font-medium text-ink transition-colors hover:border-primary/30 hover:bg-primary/5 hover:text-primary dark:border-line-dark dark:text-ink-dark dark:hover:bg-primary/10">
              <Download className="h-4 w-4" /> Export CSV
            </a>
          </div>
        </div>

        {canViewAiTasks && (
          <div className="flex min-w-[280px] flex-1 flex-col rounded-xl border border-line bg-card p-5 shadow-soft dark:border-line-dark dark:bg-card-dark">
            <div className="flex items-start justify-between">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary-soft/50 text-primary dark:bg-primary/15 dark:text-primary-soft">
                <Sparkles className="h-5 w-5" />
              </div>
              <div className="text-right">
                <div className="text-xl font-bold tracking-tight text-ink dark:text-ink-dark">{aiTaskRunCount}</div>
                <div className="text-[11px] text-muted dark:text-muted-dark">{pluralize(aiTaskRunCount, 'run')} started</div>
              </div>
            </div>
            <h2 className="mt-3 text-sm font-semibold text-ink dark:text-ink-dark">AI Task Runs Report</h2>
            <p className="mt-1 text-xs text-muted dark:text-muted-dark">Every AI Task you've run — type, status, document count, and timing.</p>

            <div className="mt-auto flex items-center justify-between pt-4">
              <TrendBadge trend={kpiTrends.ai_tasks} />
              <a href={`${base}/api/reports/ai-task-runs.csv`} className="ml-auto inline-flex items-center gap-2 rounded-lg border border-line px-3.5 py-2 text-sm font-medium text-ink transition-colors hover:border-primary/30 hover:bg-primary/5 hover:text-primary dark:border-line-dark dark:text-ink-dark dark:hover:bg-primary/10">
                <Download className="h-4 w-4" /> Export CSV
              </a>
            </div>
          </div>
        )}

        {canViewKnowledgeBase && (
          <div className="flex min-w-[280px] flex-1 flex-col rounded-xl border border-line bg-card p-5 shadow-soft dark:border-line-dark dark:bg-card-dark">
            <div className="flex items-start justify-between">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary-soft/50 text-primary dark:bg-primary/15 dark:text-primary-soft">
                <Compass className="h-5 w-5" />
              </div>
              <div className="text-right">
                <div className="text-xl font-bold tracking-tight text-ink dark:text-ink-dark">{topicCount}</div>
                <div className="text-[11px] text-muted dark:text-muted-dark">{pluralize(topicCount, 'topic')} discovered</div>
              </div>
            </div>
            <h2 className="mt-3 text-sm font-semibold text-ink dark:text-ink-dark">Knowledge Center Report</h2>
            <p className="mt-1 text-xs text-muted dark:text-muted-dark">Every topic across everything you can access — category, mentions, and connected documents.</p>

            <div className="mt-auto flex items-center justify-end pt-4">
              <a href={`${base}/api/reports/knowledge-topics.csv`} className="inline-flex items-center gap-2 rounded-lg border border-line px-3.5 py-2 text-sm font-medium text-ink transition-colors hover:border-primary/30 hover:bg-primary/5 hover:text-primary dark:border-line-dark dark:text-ink-dark dark:hover:bg-primary/10">
                <Download className="h-4 w-4" /> Export CSV
              </a>
            </div>
          </div>
        )}
      </div>

      <div className="mt-4 rounded-xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-4 dark:border-line-dark">
          <div>
            <h2 className="text-sm font-semibold text-ink dark:text-ink-dark">Comparative Report</h2>
            <p className="text-xs text-muted dark:text-muted-dark">{comparison.current_range} vs. {comparison.previous_range} (previous {comparison.days} days)</p>
          </div>
          <a href={`${base}/api/reports/comparison.csv`} className="inline-flex items-center gap-2 rounded-lg border border-line px-3.5 py-2 text-sm font-medium text-ink transition-colors hover:border-primary/30 hover:bg-primary/5 hover:text-primary dark:border-line-dark dark:text-ink-dark dark:hover:bg-primary/10">
            <Download className="h-4 w-4" /> Export CSV
          </a>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full min-w-[620px] text-left text-sm">
            <thead>
              <tr className="border-b border-line text-xs font-semibold uppercase tracking-wide text-muted dark:border-line-dark dark:text-muted-dark">
                <th className="px-5 py-3">Metric</th>
                <th className="px-3 py-3 text-right">Current Period</th>
                <th className="px-3 py-3 text-right">Previous Period</th>
                <th className="px-3 py-3">Change</th>
                <th className="px-5 py-3 text-right">%</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line dark:divide-line-dark">
              {comparison.rows.map((row) => {
                const DirIcon = DIRECTION_ICON[row.direction] || Minus;
                return (
                  <tr key={row.label} className="transition-colors hover:bg-surface dark:hover:bg-white/5">
                    <td className="px-5 py-3 font-medium text-ink dark:text-ink-dark">{row.label}</td>
                    <td className="px-3 py-3 text-right text-ink dark:text-ink-dark">{row.current}</td>
                    <td className="px-3 py-3 text-right text-muted dark:text-muted-dark">{row.previous}</td>
                    <td className="px-3 py-3">
                      <div className="h-1.5 w-24 overflow-hidden rounded-full bg-line/50 dark:bg-white/10">
                        <div className={`h-full rounded-full ${DIRECTION_BAR_CLASS[row.direction] || 'bg-muted'}`} style={{ width: `${row.bar_width}%` }}></div>
                      </div>
                    </td>
                    <td className="px-5 py-3 text-right">
                      <span className={`inline-flex items-center gap-1 text-xs font-semibold ${DIRECTION_CLASS[row.direction] || 'text-muted dark:text-muted-dark'}`}>
                        <DirIcon className="h-3.5 w-3.5" /> {row.change_pct}%
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
