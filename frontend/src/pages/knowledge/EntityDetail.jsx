import { Link, useParams } from 'react-router-dom';
import {
  ArrowDownLeft, ArrowLeft, ArrowUpRight, ExternalLink, FilePlus, FileText, GitCompareArrows, History,
  Link as LinkIcon, Quote, ShieldQuestion, Sparkles, Users,
} from 'lucide-react';
import { getApiBaseUrl } from '../../api/client';
import AppLoader from '../../components/AppLoader';
import EmptyState from '../../components/EmptyState';
import { timeAgo } from '../../lib/timeAgo';
import { useEntityDetail } from '../../api/hooks';

// Port of templates/knowledge/entity_detail.html (Topic Detail).
export default function EntityDetail() {
  const { entityId } = useParams();
  const { data, isLoading } = useEntityDetail(entityId);

  if (isLoading || !data) return <AppLoader variant="page" />;

  const {
    entity, member_count: memberCount, mention_count: mentionCount, document_count: documentCount,
    document_buckets: documentBuckets, related_teams: relatedTeams, outgoing, incoming,
    cross_reference_documents: crossReferenceDocuments, timeline, citations,
  } = data;

  return (
    <>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg" style={{ backgroundColor: `${entity.color}22`, color: entity.color }}>
            <Sparkles className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-ink dark:text-ink-dark">{entity.display_name}</h1>
            <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted dark:text-muted-dark">
              <span className="rounded-full border border-line px-2 py-0.5 text-xs font-medium capitalize dark:border-line-dark">{entity.entity_type.toLowerCase()}</span>
              <span>{documentCount} connected document{documentCount === 1 ? '' : 's'}</span>
              <span aria-hidden="true">·</span>
              <span>{mentionCount} mention{mentionCount === 1 ? '' : 's'}</span>
              {memberCount > 1 && (
                <>
                  <span aria-hidden="true">·</span>
                  <span>seen across {memberCount} contributor{memberCount === 1 ? '' : 's'}</span>
                </>
              )}
            </p>
          </div>
        </div>
        <Link to="/knowledge" className="inline-flex items-center gap-2 rounded-lg border border-line px-3.5 py-2 text-sm font-medium text-ink hover:bg-surface dark:border-line-dark dark:text-ink-dark dark:hover:bg-white/5">
          <ArrowLeft className="h-4 w-4" /> Back to Explore Topics
        </Link>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <div className="rounded-xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">
            <div className="border-b border-line px-5 py-4 dark:border-line-dark">
              <h2 className="flex items-center gap-2 text-sm font-semibold text-ink dark:text-ink-dark">
                <FileText className="h-4 w-4 text-primary dark:text-primary-soft" /> Connected Documents
              </h2>
            </div>
            <div className="divide-y divide-line dark:divide-line-dark">
              {documentBuckets.length > 0 ? documentBuckets.map(({ label, documents }) => (
                <div key={label} className="px-5 py-4">
                  <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted dark:text-muted-dark">{label} ({documents.length})</p>
                  <div className="space-y-1.5">
                    {documents.map((document) => (
                      <div key={document.id} className="flex items-center justify-between gap-3 rounded-lg px-2.5 py-2 hover:bg-surface dark:hover:bg-white/5">
                        <span className="min-w-0 truncate text-sm text-ink dark:text-ink-dark">{document.title}</span>
                        <span className="flex shrink-0 items-center gap-3">
                          <Link to={`/knowledge/documents/${document.id}`} className="inline-flex items-center gap-1 text-xs font-medium text-ink hover:text-primary dark:text-ink-dark dark:hover:text-primary-soft">
                            <LinkIcon className="h-3 w-3" /> Knowledge
                          </Link>
                          <a href={`${getApiBaseUrl()}/api/documents/${document.id}/download/?download=1`} className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline dark:text-primary-soft">
                            <ExternalLink className="h-3 w-3" /> View Source
                          </a>
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )) : (
                <EmptyState icon={FileText} title="No connected documents" message="No source documents are visible to you for this topic." />
              )}
            </div>
          </div>

          {crossReferenceDocuments.length > 0 && (
            <div className="rounded-xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">
              <div className="border-b border-line px-5 py-4 dark:border-line-dark">
                <h2 className="flex items-center gap-2 text-sm font-semibold text-ink dark:text-ink-dark">
                  <GitCompareArrows className="h-4 w-4 text-primary dark:text-primary-soft" /> Cross-References
                </h2>
                <p className="mt-0.5 text-xs text-muted dark:text-muted-dark">Documents connected through a related concept, not a direct mention.</p>
              </div>
              <div className="divide-y divide-line dark:divide-line-dark">
                {crossReferenceDocuments.map((document) => (
                  <div key={document.id} className="flex items-center justify-between gap-3 px-5 py-3">
                    <span className="min-w-0 truncate text-sm text-ink dark:text-ink-dark">{document.title}</span>
                    <a href={`${getApiBaseUrl()}/api/documents/${document.id}/download/?download=1`} className="inline-flex shrink-0 items-center gap-1 text-xs font-medium text-primary hover:underline dark:text-primary-soft">
                      <ExternalLink className="h-3 w-3" /> View Source
                    </a>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="rounded-xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">
            <div className="border-b border-line px-5 py-4 dark:border-line-dark">
              <h2 className="flex items-center gap-2 text-sm font-semibold text-ink dark:text-ink-dark">
                <History className="h-4 w-4 text-primary dark:text-primary-soft" /> Timeline
              </h2>
            </div>
            <div className="divide-y divide-line dark:divide-line-dark">
              {timeline.length > 0 ? timeline.map((event, idx) => (
                <div key={idx} className="flex items-start gap-3 px-5 py-3">
                  {event.kind === 'mention' ? <FilePlus className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted dark:text-muted-dark" /> : <LinkIcon className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted dark:text-muted-dark" />}
                  <div className="min-w-0 flex-1">
                    <p className="text-sm text-ink dark:text-ink-dark">{event.description}</p>
                    <p className="text-xs text-muted dark:text-muted-dark">{timeAgo(event.at)} ago</p>
                  </div>
                </div>
              )) : <p className="px-5 py-6 text-center text-sm text-muted dark:text-muted-dark">No timeline activity yet.</p>}
            </div>
          </div>

          {citations.length > 0 && (
            <div className="rounded-xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">
              <div className="border-b border-line px-5 py-4 dark:border-line-dark">
                <h2 className="flex items-center gap-2 text-sm font-semibold text-ink dark:text-ink-dark">
                  <Quote className="h-4 w-4 text-primary dark:text-primary-soft" /> Cited in AI Search
                </h2>
                <p className="mt-0.5 text-xs text-muted dark:text-muted-dark">Questions whose answer actually cited a source about this topic.</p>
              </div>
              <div className="divide-y divide-line dark:divide-line-dark">
                {citations.map((citation, idx) => (
                  <div key={idx} className="px-5 py-3">
                    <p className="truncate text-sm font-medium text-ink dark:text-ink-dark">{citation.question}</p>
                    <p className="mt-0.5 text-xs text-muted dark:text-muted-dark">{citation.document} · chunk {citation.chunk_number} · {timeAgo(citation.created_at)} ago</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="space-y-6">
          {relatedTeams.length > 0 && (
            <div className="rounded-xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">
              <div className="border-b border-line px-5 py-4 dark:border-line-dark">
                <h2 className="flex items-center gap-2 text-sm font-semibold text-ink dark:text-ink-dark">
                  <Users className="h-4 w-4 text-primary dark:text-primary-soft" /> Related Teams
                </h2>
              </div>
              <div className="divide-y divide-line dark:divide-line-dark">
                {relatedTeams.map((team) => (
                  <Link key={team.id} to={`/knowledge/entities/${team.id}`} className="flex items-center justify-between gap-2 px-5 py-3 text-sm hover:bg-surface dark:hover:bg-white/5">
                    <span className="font-medium text-ink dark:text-ink-dark">{team.display_name}</span>
                    <span className="shrink-0 rounded-full border border-line px-2 py-0.5 text-[11px] text-muted dark:border-line-dark dark:text-muted-dark">{team.mention_count} mention{team.mention_count === 1 ? '' : 's'}</span>
                  </Link>
                ))}
              </div>
            </div>
          )}

          <div className="rounded-xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">
            <div className="border-b border-line px-5 py-4 dark:border-line-dark">
              <h2 className="flex items-center gap-2 text-sm font-semibold text-ink dark:text-ink-dark">
                <ArrowUpRight className="h-4 w-4 text-primary dark:text-primary-soft" /> Connected Concepts
              </h2>
              <p className="mt-0.5 text-xs text-muted dark:text-muted-dark">What this topic points to.</p>
            </div>
            <div className="divide-y divide-line dark:divide-line-dark">
              {outgoing.length > 0 ? outgoing.map((rel) => (
                <Link key={rel.id} to={`/knowledge/entities/${rel.target.id}`} className="flex items-center justify-between gap-2 px-5 py-3 text-sm hover:bg-surface dark:hover:bg-white/5">
                  <span className="text-ink dark:text-ink-dark">
                    <span className="text-muted dark:text-muted-dark">{rel.relation_type.toLowerCase()}</span> → <span className="font-medium">{rel.target.display_name}</span>
                  </span>
                  <span className="shrink-0 rounded-full border border-line px-2 py-0.5 text-[11px] text-muted dark:border-line-dark dark:text-muted-dark">×{rel.weight}</span>
                </Link>
              )) : <p className="px-5 py-6 text-center text-sm text-muted dark:text-muted-dark">None found.</p>}
            </div>
          </div>

          <div className="rounded-xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">
            <div className="border-b border-line px-5 py-4 dark:border-line-dark">
              <h2 className="flex items-center gap-2 text-sm font-semibold text-ink dark:text-ink-dark">
                <ArrowDownLeft className="h-4 w-4 text-primary dark:text-primary-soft" /> Referenced By
              </h2>
              <p className="mt-0.5 text-xs text-muted dark:text-muted-dark">What points to this topic.</p>
            </div>
            <div className="divide-y divide-line dark:divide-line-dark">
              {incoming.length > 0 ? incoming.map((rel) => (
                <Link key={rel.id} to={`/knowledge/entities/${rel.source.id}`} className="flex items-center justify-between gap-2 px-5 py-3 text-sm hover:bg-surface dark:hover:bg-white/5">
                  <span className="text-ink dark:text-ink-dark">
                    <span className="font-medium">{rel.source.display_name}</span> → <span className="text-muted dark:text-muted-dark">{rel.relation_type.toLowerCase()}</span>
                  </span>
                  <span className="shrink-0 rounded-full border border-line px-2 py-0.5 text-[11px] text-muted dark:border-line-dark dark:text-muted-dark">×{rel.weight}</span>
                </Link>
              )) : <p className="px-5 py-6 text-center text-sm text-muted dark:text-muted-dark">None found.</p>}
            </div>
          </div>

          <div className="rounded-xl border border-dashed border-line bg-card/50 p-5 dark:border-line-dark dark:bg-card-dark/50">
            <h2 className="flex items-center gap-2 text-sm font-semibold text-ink dark:text-ink-dark">
              <ShieldQuestion className="h-4 w-4 text-primary dark:text-primary-soft" /> Check for conflicts
            </h2>
            <p className="mt-1.5 text-xs text-muted dark:text-muted-dark">Spotting contradictions between documents is an analysis task, not a discovery one. Run <strong>Compare Documents</strong> or <strong>Validate Against Reference Documents</strong> in AI Tasks over this topic's connected documents to check.</p>
            <a href="/ai-tasks/" className="mt-3 inline-flex items-center gap-2 rounded-lg border border-line px-3.5 py-2 text-sm font-medium text-ink transition-colors hover:border-primary/30 hover:bg-primary/5 hover:text-primary dark:border-line-dark dark:text-ink-dark dark:hover:bg-primary/10">
              <Sparkles className="h-4 w-4" /> Open AI Tasks
            </a>
          </div>
        </div>
      </div>
    </>
  );
}
