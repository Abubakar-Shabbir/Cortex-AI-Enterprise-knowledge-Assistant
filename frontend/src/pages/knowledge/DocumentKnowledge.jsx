import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, ArrowRight, ExternalLink, Folder, FolderOpen, Library, Sparkles, Tag as TagIcon, User } from 'lucide-react';
import AppLoader from '../../components/AppLoader';
import { getApiBaseUrl } from '../../api/client';
import { timeAgo } from '../../lib/timeAgo';
import { useDocumentKnowledge } from '../../api/hooks';

// Port of templates/knowledge/document_relationships.html (Document Relationship View).
export default function DocumentKnowledge() {
  const { docId } = useParams();
  const { data, isLoading } = useDocumentKnowledge(docId);

  if (isLoading || !data) return <AppLoader variant="page" />;

  const { document, topics, relationships, related_by_topic: relatedByTopic, similar_documents: similarDocuments, citations, shares, is_owner: isOwner } = data;
  const downloadUrl = `${getApiBaseUrl()}/api/documents/${document.id}/download/`;

  return (
    <>
      <div className="mb-4 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <Link to="/documents" className="mb-1 inline-flex items-center gap-1.5 text-xs font-medium text-muted hover:text-ink dark:text-muted-dark dark:hover:text-ink-dark">
            <ArrowLeft className="h-3.5 w-3.5" /> Back to Documents
          </Link>
          <h1 className="truncate text-2xl font-bold tracking-tight text-ink dark:text-ink-dark">{document.title}</h1>
          <p className="mt-1 text-sm text-muted dark:text-muted-dark">Where this document's knowledge came from, what it connects to, and everything traced back to it.</p>
        </div>
        <a href={downloadUrl} target="_blank" rel="noreferrer" className="inline-flex shrink-0 items-center gap-2 rounded-lg border border-line px-3.5 py-2 text-sm font-medium text-ink transition-colors hover:border-primary/30 hover:bg-primary/5 hover:text-primary dark:border-line-dark dark:text-ink-dark dark:hover:bg-primary/10">
          <ExternalLink className="h-4 w-4" /> Open Document
        </a>
      </div>

      <div className="mb-4 rounded-xl border border-line bg-card p-4 shadow-soft dark:border-line-dark dark:bg-card-dark">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="inline-flex items-center gap-1 rounded-full border border-line px-2 py-1 font-medium uppercase text-muted dark:border-line-dark dark:text-muted-dark">{document.file_type}</span>
          <span className="text-muted dark:text-muted-dark">{document.file_size_display}</span>
          <span className="text-muted dark:text-muted-dark">· {document.chunk_count} chunk{document.chunk_count === 1 ? '' : 's'}</span>
          <span className="text-muted dark:text-muted-dark">· Uploaded {new Date(document.uploaded_at).toLocaleDateString('en-US', { month: 'short', day: '2-digit', year: 'numeric' })}</span>
          {document.is_org_library && (
            <span className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-1 font-medium text-primary dark:text-primary-soft"><Library className="h-3 w-3" /> Organization Library</span>
          )}
          {document.category && (
            <span className="inline-flex items-center gap-1 rounded-full border border-line px-2 py-1 text-ink dark:border-line-dark dark:text-ink-dark"><Folder className="h-3 w-3" /> {document.category}</span>
          )}
          {document.tags.map((tag) => (
            <span key={tag} className="inline-flex items-center gap-1 rounded-full border border-line px-2 py-1 text-ink dark:border-line-dark dark:text-ink-dark"><TagIcon className="h-3 w-3" /> {tag}</span>
          ))}
          {(document.collections || []).map((name) => (
            <span key={name} className="inline-flex items-center gap-1 rounded-full border border-line px-2 py-1 text-ink dark:border-line-dark dark:text-ink-dark"><FolderOpen className="h-3 w-3" /> {name}</span>
          ))}
        </div>

        {isOwner && shares && shares.length > 0 && (
          <div className="mt-3 border-t border-line pt-3 dark:border-line-dark">
            <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted dark:text-muted-dark">Shared with</p>
            <div className="flex flex-wrap gap-1.5">
              {shares.map((share) => (
                <span key={share.id} className="inline-flex items-center gap-1 rounded-full border border-line px-2 py-1 text-xs text-ink dark:border-line-dark dark:text-ink-dark">
                  <User className="h-3 w-3" /> {share.shared_with_user || share.shared_with_role || share.invited_email}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <div className="rounded-xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">
            <div className="border-b border-line px-5 py-3 dark:border-line-dark">
              <h2 className="text-sm font-semibold text-ink dark:text-ink-dark">Topics Found In This Document</h2>
              <p className="mt-0.5 text-xs text-muted dark:text-muted-dark" title="Entities represent important people, organizations, concepts, or objects found in your documents.">The people, organizations, and concepts AI extracted from this document.</p>
            </div>
            <div className="px-5 py-4">
              {topics.length > 0 ? (
                <div className="flex flex-wrap gap-1.5">
                  {topics.map((topic) => (
                    <Link key={topic.id} to={`/knowledge/entities/${topic.id}`} className="inline-flex items-center gap-1.5 rounded-full border border-line px-2.5 py-1 text-xs font-medium text-ink transition-colors hover:border-primary/40 dark:border-line-dark dark:text-ink-dark">
                      <span className="h-2 w-2 rounded-full" style={{ backgroundColor: topic.color }}></span>
                      {topic.display_name}
                      <span className="text-muted dark:text-muted-dark">{topic.mention_count}</span>
                    </Link>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-muted dark:text-muted-dark">No topics extracted yet — this document may still be processing, or its content didn't contain any recognizable entities.</p>
              )}
            </div>

            {relationships.length > 0 && (
              <div className="border-t border-line px-5 py-4 dark:border-line-dark">
                <p className="mb-2 text-xs text-muted dark:text-muted-dark" title="Relationships show how pieces of knowledge are connected.">How this document's topics connect to each other.</p>
                <ul className="space-y-1.5">
                  {relationships.map((rel) => (
                    <li key={rel.id} className="flex items-center gap-1.5 text-sm text-ink dark:text-ink-dark">
                      <span>{rel.source.display_name}</span>
                      <span className="rounded-full bg-line/50 px-1.5 py-0.5 text-[11px] font-medium text-muted dark:bg-white/5 dark:text-muted-dark">{rel.relation_type}</span>
                      <ArrowRight className="h-3 w-3 text-muted dark:text-muted-dark" />
                      <span>{rel.target.display_name}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          <div className="rounded-xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">
            <div className="border-b border-line px-5 py-3 dark:border-line-dark">
              <h2 className="text-sm font-semibold text-ink dark:text-ink-dark">Related Documents</h2>
              <p className="mt-0.5 text-xs text-muted dark:text-muted-dark">Connected Documents show other sources tied to this one — by shared topics or by similar content.</p>
            </div>
            <div className="grid grid-cols-1 divide-y divide-line dark:divide-line-dark sm:grid-cols-2 sm:divide-x sm:divide-y-0 dark:sm:divide-line-dark">
              <div className="px-5 py-4">
                <p className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted dark:text-muted-dark"><Sparkles className="h-3 w-3" /> Shares topics with</p>
                {relatedByTopic.length > 0 ? (
                  <ul className="space-y-2">
                    {relatedByTopic.map((row) => (
                      <li key={row.document.id}>
                        <Link to={`/knowledge/documents/${row.document.id}`} className="flex items-center justify-between gap-2 text-sm text-ink hover:text-primary dark:text-ink-dark dark:hover:text-primary-soft">
                          <span className="truncate">{row.document.title}</span>
                          <span className="shrink-0 text-xs text-muted dark:text-muted-dark">{row.shared_topics} shared</span>
                        </Link>
                      </li>
                    ))}
                  </ul>
                ) : <p className="text-sm text-muted dark:text-muted-dark">No documents share topics with this one yet.</p>}
              </div>
              <div className="px-5 py-4">
                <p className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted dark:text-muted-dark"><Sparkles className="h-3 w-3" /> Similar content</p>
                {similarDocuments.length > 0 ? (
                  <ul className="space-y-2">
                    {similarDocuments.map((row) => (
                      <li key={row.document.id}>
                        <Link to={`/knowledge/documents/${row.document.id}`} className="flex items-center justify-between gap-2 text-sm text-ink hover:text-primary dark:text-ink-dark dark:hover:text-primary-soft">
                          <span className="truncate">{row.document.title}</span>
                          <span className="shrink-0 text-xs text-muted dark:text-muted-dark">{row.similarity}% similar</span>
                        </Link>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-muted dark:text-muted-dark">
                    {document.processing_status !== 'completed' ? "This document is still processing — similarity can't be computed yet." : 'No similar documents found.'}
                  </p>
                )}
              </div>
            </div>
          </div>
        </div>

        <div className="space-y-4">
          <div className="rounded-xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">
            <div className="border-b border-line px-5 py-3 dark:border-line-dark">
              <h2 className="text-sm font-semibold text-ink dark:text-ink-dark">Cited In Your Ask AI History</h2>
              <p className="mt-0.5 text-xs text-muted dark:text-muted-dark">Questions you've asked where the answer cited this document.</p>
            </div>
            <div className="px-5 py-4">
              {citations.length > 0 ? (
                <>
                  <ul className="space-y-3">
                    {citations.slice(0, 10).map((citation, idx) => (
                      <li key={idx} className="text-xs">
                        <p className="font-medium text-ink dark:text-ink-dark">{citation.question.length > 70 ? `${citation.question.slice(0, 70)}…` : citation.question}</p>
                        <p className="mt-0.5 text-muted dark:text-muted-dark">Chunk {citation.chunk_number} · {timeAgo(citation.created_at)} ago</p>
                      </li>
                    ))}
                  </ul>
                  <Link to="/knowledge/citations" className="mt-3 inline-block text-xs font-medium text-primary hover:underline dark:text-primary-soft">View all citations</Link>
                </>
              ) : <p className="text-sm text-muted dark:text-muted-dark">You haven't cited this document in Ask AI yet.</p>}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
