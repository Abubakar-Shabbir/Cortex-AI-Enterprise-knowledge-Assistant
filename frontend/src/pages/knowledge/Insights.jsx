import { Link } from 'react-router-dom';
import {
  BadgeAlert, Check, Clock, Compass, Copy, FileText, GitBranch, Network, PieChart, SearchX, Star, Tag,
} from 'lucide-react';
import PageHeader from '../../components/PageHeader';
import StatCard from '../../components/StatCard';
import PageSkeleton from '../../components/PageSkeleton';
import KnowledgeTabs from '../../layout/KnowledgeTabs';
import { timeAgo } from '../../lib/timeAgo';
import { useKnowledgeInsights } from '../../api/hooks';

function Panel({ icon: Icon, iconBg, iconColor, title, subtitle, children }) {
  return (
    <div className="overflow-hidden rounded-xl border border-line bg-card shadow-soft transition-shadow hover:shadow-soft dark:border-line-dark dark:bg-card-dark">
      <div className="border-b border-line px-5 py-4 dark:border-line-dark">
        <h2 className="flex items-center gap-2.5 text-sm font-semibold text-ink dark:text-ink-dark">
          <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${iconBg} ${iconColor}`}><Icon className="h-4 w-4" /></span>
          {title}
        </h2>
        {subtitle && <p className="mt-1.5 text-xs text-muted dark:text-muted-dark">{subtitle}</p>}
      </div>
      {children}
    </div>
  );
}

// Port of templates/knowledge/insights.html.
export default function Insights() {
  const { data: insights, isLoading } = useKnowledgeInsights();

  if (isLoading || !insights) return <PageSkeleton variant="grid" />;

  const hasCoverageGaps = insights.not_processed.length > 0 || insights.processed_without_extraction.length > 0;

  return (
    <>
      <PageHeader title="Knowledge Insights" subtitle="What's well-covered, what's thin, and what might be worth a closer look — across everything you can access." />
      <KnowledgeTabs />

      <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2">
        <StatCard icon={Compass} label="Topics" value={insights.total_topics} numeric iconBg="bg-primary/10" iconColor="text-primary dark:text-primary-soft" />
        <StatCard icon={FileText} label="Accessible Documents" value={insights.total_accessible_documents} numeric iconBg="bg-success/10" iconColor="text-success" />
      </div>

      <div className="fade-in-up grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Panel icon={Star} iconBg="bg-primary/10" iconColor="text-primary dark:text-primary-soft" title="Most Referenced Documents" subtitle="Documents with the most extracted entity mentions — the most load-bearing sources in the graph.">
          <div className="divide-y divide-line dark:divide-line-dark">
            {insights.most_referenced_documents.length > 0 ? insights.most_referenced_documents.map((document) => (
              <Link key={document.id} to={`/knowledge/documents/${document.id}`} className="flex items-center justify-between gap-3 px-5 py-3 transition-colors hover:bg-surface dark:hover:bg-white/5">
                <span className="flex min-w-0 items-center gap-2 truncate text-sm text-ink dark:text-ink-dark">
                  <FileText className="h-3.5 w-3.5 shrink-0 text-muted dark:text-muted-dark" /> {document.title}
                </span>
                <span className="shrink-0 rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary dark:text-primary-soft">{document.mention_total} mention{document.mention_total === 1 ? '' : 's'}</span>
              </Link>
            )) : <p className="px-5 py-6 text-center text-sm text-muted dark:text-muted-dark">Nothing to show yet.</p>}
          </div>
        </Panel>

        <Panel icon={Network} iconBg="bg-info/10" iconColor="text-info" title="Frequently Connected Topics" subtitle="Topics with the most direct connections to other topics.">
          <div className="divide-y divide-line dark:divide-line-dark">
            {insights.frequently_connected_topics.length > 0 ? insights.frequently_connected_topics.map((topic) => (
              <Link key={topic.id} to={`/knowledge/entities/${topic.id}`} className="flex items-center justify-between gap-3 px-5 py-3 transition-colors hover:bg-surface dark:hover:bg-white/5">
                <span className="flex min-w-0 items-center gap-2 truncate text-sm font-medium text-ink dark:text-ink-dark">
                  <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: topic.color }}></span> {topic.display_name}
                </span>
                <span className="shrink-0 rounded-full bg-info/10 px-2 py-0.5 text-[11px] font-medium text-info">{topic.degree} connection{topic.degree === 1 ? '' : 's'}</span>
              </Link>
            )) : <p className="px-5 py-6 text-center text-sm text-muted dark:text-muted-dark">Nothing to show yet.</p>}
          </div>
        </Panel>

        <Panel icon={Clock} iconBg="bg-accent/10" iconColor="text-accent" title="Recently Updated Knowledge">
          <div className="divide-y divide-line dark:divide-line-dark">
            {insights.recently_updated.length > 0 ? insights.recently_updated.map((event, idx) => (
              <div key={idx} className="flex items-start gap-3 px-5 py-3">
                <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-accent/10 text-accent">
                  {event.kind === 'mention' ? <Tag className="h-3 w-3" /> : <GitBranch className="h-3 w-3" />}
                </span>
                <div className="min-w-0">
                  {event.kind === 'mention' ? (
                    <p className="text-sm text-ink dark:text-ink-dark"><span className="font-medium">{event.entity.display_name}</span> newly linked to "{event.document?.title}"</p>
                  ) : (
                    <p className="text-sm text-ink dark:text-ink-dark"><span className="font-medium">{event.relationship.source.display_name}</span> {event.relationship.relation_type.toLowerCase()} <span className="font-medium">{event.relationship.target.display_name}</span></p>
                  )}
                  <p className="mt-0.5 text-xs text-muted dark:text-muted-dark">{timeAgo(event.at)} ago</p>
                </div>
              </div>
            )) : <p className="px-5 py-6 text-center text-sm text-muted dark:text-muted-dark">Nothing to show yet.</p>}
          </div>
        </Panel>

        <Panel icon={PieChart} iconBg="bg-warning/10" iconColor="text-warning" title="Knowledge Coverage" subtitle="Documents that aren't fully contributing to the knowledge graph yet.">
          <div className="px-5 py-4">
            {hasCoverageGaps ? (
              <>
                {insights.not_processed.length > 0 && (
                  <>
                    <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted dark:text-muted-dark">Not yet processed ({insights.not_processed.length})</p>
                    <div className="mb-4 flex flex-wrap gap-1.5">
                      {insights.not_processed.map((document) => (
                        <span key={document.id} title={document.title} className="inline-flex max-w-[220px] items-center gap-1.5 truncate rounded-full border border-warning/30 bg-warning/5 px-2.5 py-1 text-xs text-ink dark:border-warning-dark/30 dark:text-ink-dark">
                          <Clock className="h-3 w-3 shrink-0 text-warning dark:text-warning-dark" /> <span className="truncate">{document.title}</span>
                        </span>
                      ))}
                    </div>
                  </>
                )}
                {insights.processed_without_extraction.length > 0 && (
                  <>
                    <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted dark:text-muted-dark">Processed, nothing extracted ({insights.processed_without_extraction.length})</p>
                    <div className="flex flex-wrap gap-1.5">
                      {insights.processed_without_extraction.map((document) => (
                        <span key={document.id} title={document.title} className="inline-flex max-w-[220px] items-center gap-1.5 truncate rounded-full border border-line bg-surface px-2.5 py-1 text-xs text-ink dark:border-line-dark dark:bg-white/5 dark:text-ink-dark">
                          <SearchX className="h-3 w-3 shrink-0 text-muted dark:text-muted-dark" /> <span className="truncate">{document.title}</span>
                        </span>
                      ))}
                    </div>
                  </>
                )}
              </>
            ) : (
              <div className="flex flex-col items-center gap-2 py-4 text-center">
                <span className="flex h-9 w-9 items-center justify-center rounded-full bg-success/10 text-success"><Check className="h-4 w-4" /></span>
                <p className="text-sm text-muted dark:text-muted-dark">Full coverage — every accessible, processed document has contributed to the graph.</p>
              </div>
            )}
          </div>
        </Panel>

        <Panel icon={BadgeAlert} iconBg="bg-danger/10" iconColor="text-danger dark:text-danger-dark" title="Weak / Unconfirmed Topics" subtitle="Mentioned only once, with no confirmed connections — worth a second look before relying on them.">
          <div className="divide-y divide-line dark:divide-line-dark">
            {insights.weak_topics.length > 0 ? insights.weak_topics.map((topic) => (
              <Link key={topic.id} to={`/knowledge/entities/${topic.id}`} className="flex items-center justify-between gap-3 px-5 py-3 transition-colors hover:bg-surface dark:hover:bg-white/5">
                <span className="flex min-w-0 items-center gap-2 truncate text-sm text-ink dark:text-ink-dark">
                  <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: topic.color }}></span> {topic.display_name}
                </span>
                <span className="shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium capitalize" style={{ backgroundColor: `${topic.color}22`, color: topic.color }}>{topic.entity_type.toLowerCase()}</span>
              </Link>
            )) : <p className="px-5 py-6 text-center text-sm text-muted dark:text-muted-dark">No weak signals found.</p>}
          </div>
        </Panel>

        <Panel icon={Copy} iconBg="bg-success/10" iconColor="text-success" title="Possible Duplicate Content" subtitle="Documents whose embeddings are nearly identical — likely the same content uploaded more than once.">
          <div className="divide-y divide-line dark:divide-line-dark">
            {insights.duplicate_clusters.length > 0 ? insights.duplicate_clusters.map((cluster, idx) => (
              <div key={idx} className="px-5 py-3">
                {cluster.documents.map((document) => (
                  <p key={document.id} className="flex items-center gap-2 truncate text-sm text-ink dark:text-ink-dark"><FileText className="h-3.5 w-3.5 shrink-0 text-muted dark:text-muted-dark" /> {document.title}</p>
                ))}
              </div>
            )) : <p className="px-5 py-6 text-center text-sm text-muted dark:text-muted-dark">No likely duplicates found.</p>}
          </div>
        </Panel>
      </div>
    </>
  );
}
