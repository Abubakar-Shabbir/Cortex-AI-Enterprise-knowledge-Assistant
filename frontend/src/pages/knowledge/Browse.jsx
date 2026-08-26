import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Compass, DatabaseZap, FileText, GitBranch, Search, Sparkles, Tag } from 'lucide-react';
import PageHeader from '../../components/PageHeader';
import StatCard from '../../components/StatCard';
import EmptyState from '../../components/EmptyState';
import AppLoader from '../../components/AppLoader';
import KnowledgeTabs from '../../layout/KnowledgeTabs';
import { timeAgo } from '../../lib/timeAgo';
import { useKnowledgeBrowse } from '../../api/hooks';

// Port of templates/knowledge/browse.html (Explore Topics).
export default function KnowledgeBrowse() {
  const [searchParams, setSearchParams] = useSearchParams();
  const query = searchParams.get('q') || '';
  const selectedType = searchParams.get('type') || '';
  const page = searchParams.get('page') || '1';

  const [searchInput, setSearchInput] = useState(query);
  const { data, isLoading } = useKnowledgeBrowse({ q: query, type: selectedType, page });

  const submitSearch = (e) => {
    e.preventDefault();
    setSearchParams({ ...(searchInput ? { q: searchInput } : {}), ...(selectedType ? { type: selectedType } : {}) });
  };

  const selectType = (type) => setSearchParams({ ...(query ? { q: query } : {}), ...(type ? { type } : {}) });

  if (isLoading || !data) return <AppLoader variant="page" />;

  const { overview, recently_updated: recentlyUpdated, topics, pagination } = data;

  return (
    <>
      <PageHeader title="Knowledge Center" subtitle="Your organization's connected knowledge space — explore topics, entities, and relationships discovered across everything you can access." />
      <KnowledgeTabs />

      <p className="mb-4 max-w-3xl text-sm text-muted dark:text-muted-dark">
        As documents are uploaded, AI extracts the people, organizations, and concepts they mention (
        <span title="A Topic groups the same real-world entity mentioned across multiple documents, even by different uploaders.">Topics</span>) and how those topics relate to each other (
        <span title="A Relationship is a directed connection between two topics, e.g. 'Company A' — acquired — 'Company B'.">Relationships</span>). Search below, or open the{' '}
        <Link to="/knowledge/graph" className="font-medium text-primary hover:underline dark:text-primary-soft">Graph</Link> to see it all connected visually.
      </p>

      <div className="mb-4 flex flex-wrap gap-3">
        <div className="min-w-[190px] flex-1"><StatCard icon={Compass} label="Topics" value={overview.total_entities} title="Distinct people, organizations, and concepts found across your accessible documents." iconBg="bg-primary/10" iconColor="text-primary dark:text-primary-soft" /></div>
        <div className="min-w-[190px] flex-1"><StatCard icon={GitBranch} label="Relationships" value={overview.total_relationships} title="Directed connections discovered between topics." iconBg="bg-info/10" iconColor="text-info" /></div>
        <div className="min-w-[190px] flex-1"><StatCard icon={FileText} label="Connected Documents" value={overview.total_sources} title="Documents that contributed at least one topic to your knowledge base." iconBg="bg-success/10" iconColor="text-success" /></div>
        <div className="min-w-[190px] flex-1"><StatCard icon={DatabaseZap} label="Indexed Documents" value={overview.indexed_documents} sublabel={overview.indexed_documents_label} title="Documents fully processed and searched for topics, out of every document you can access." iconBg="bg-accent/10" iconColor="text-accent" /></div>
      </div>

      {recentlyUpdated.length > 0 && (
        <div className="mb-4 rounded-xl border border-line bg-card p-4 shadow-soft dark:border-line-dark dark:bg-card-dark">
          <div className="mb-2.5 flex items-center justify-between">
            <h2 className="flex items-center gap-1.5 text-sm font-semibold text-ink dark:text-ink-dark">
              <Sparkles className="h-4 w-4 text-primary dark:text-primary-soft" /> Recently Added Knowledge
            </h2>
            <Link to="/knowledge/insights" className="text-xs font-medium text-primary hover:underline dark:text-primary-soft">View all insights</Link>
          </div>
          <div className="flex flex-wrap gap-2">
            {recentlyUpdated.map((event, idx) => (
              <span key={idx} className="inline-flex items-center gap-1.5 rounded-full border border-line px-2.5 py-1 text-xs text-ink dark:border-line-dark dark:text-ink-dark">
                {event.kind === 'mention' ? <Tag className="h-3 w-3 text-muted dark:text-muted-dark" /> : <GitBranch className="h-3 w-3 text-muted dark:text-muted-dark" />}
                {event.kind === 'mention' ? event.entity.display_name : `${event.relationship.source.display_name} → ${event.relationship.target.display_name}`}
                <span className="text-muted dark:text-muted-dark">· {timeAgo(event.at)} ago</span>
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="mb-4 rounded-xl border border-line bg-card p-4 shadow-soft dark:border-line-dark dark:bg-card-dark">
        <form onSubmit={submitSearch} className="flex flex-wrap items-center gap-3">
          <div className="relative min-w-[220px] flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted dark:text-muted-dark" />
            <input
              type="text" value={searchInput} onChange={(e) => setSearchInput(e.target.value)}
              placeholder='Search topics — e.g. "ISO 27001", "Employee Onboarding"…'
              className="w-full rounded-lg border border-line bg-surface py-2 pl-9 pr-3 text-sm text-ink placeholder:text-muted focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/15 dark:border-line-dark dark:bg-white/5 dark:text-ink-dark dark:placeholder:text-muted-dark"
            />
          </div>
          <button type="submit" className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-primary-dark">
            <Search className="h-4 w-4" /> Search
          </button>
          {(query || selectedType) && (
            <button type="button" onClick={() => { setSearchInput(''); setSearchParams({}); }} className="text-sm font-medium text-muted hover:text-ink dark:text-muted-dark dark:hover:text-ink-dark">Clear</button>
          )}
        </form>

        {overview.categories.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5 border-t border-line pt-3 dark:border-line-dark">
            <button
              onClick={() => selectType('')}
              className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-colors ${!selectedType ? 'border-primary bg-primary text-white' : 'border-line text-muted hover:border-primary/40 hover:text-ink dark:border-line-dark dark:text-muted-dark dark:hover:text-ink-dark'}`}
            >
              All <span className={!selectedType ? 'text-white/70' : 'text-muted dark:text-muted-dark'}>{overview.total_entities}</span>
            </button>
            {overview.categories.map((category) => {
              const active = selectedType === category.entity_type;
              return (
                <button
                  key={category.entity_type}
                  onClick={() => selectType(category.entity_type)}
                  style={active ? { backgroundColor: category.color, borderColor: category.color } : undefined}
                  className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium capitalize transition-colors ${active ? 'text-white' : 'border-line text-muted hover:border-primary/40 hover:text-ink dark:border-line-dark dark:text-muted-dark dark:hover:text-ink-dark'}`}
                >
                  <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: active ? '#fff' : category.color }}></span>
                  {category.entity_type.toLowerCase()} <span className={active ? 'text-white/70' : 'text-muted dark:text-muted-dark'}>{category.count}</span>
                </button>
              );
            })}
          </div>
        )}
      </div>

      {topics.length > 0 ? (
        <>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {topics.map((topic) => (
              <Link
                key={topic.id}
                to={`/knowledge/entities/${topic.id}`}
                className="group relative overflow-hidden rounded-xl border border-line bg-card p-4 shadow-soft transition-all duration-200 hover:-translate-y-0.5 hover:border-transparent hover:shadow-soft dark:border-line-dark dark:bg-card-dark"
              >
                <span className="absolute inset-y-0 left-0 w-1 opacity-80 transition-opacity duration-200 group-hover:opacity-100" style={{ backgroundColor: topic.color }}></span>
                <div className="flex items-start justify-between gap-2 pl-1.5">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl transition-transform duration-200 group-hover:scale-105" style={{ backgroundColor: `${topic.color}22`, color: topic.color }}>
                    <Compass className="h-5 w-5" />
                  </div>
                  <span className="rounded-full px-2 py-0.5 text-[11px] font-medium capitalize" style={{ backgroundColor: `${topic.color}22`, color: topic.color }}>{topic.entity_type.toLowerCase()}</span>
                </div>
                <p className="mt-3 truncate pl-1.5 text-sm font-semibold text-ink group-hover:text-primary dark:text-ink-dark dark:group-hover:text-primary-soft">{topic.display_name}</p>
                <p className="mt-1 flex items-center gap-2 pl-1.5 text-xs text-muted dark:text-muted-dark">
                  <span className="inline-flex items-center gap-1"><FileText className="h-3 w-3" /> {topic.document_count} document{topic.document_count === 1 ? '' : 's'}</span>
                  <span aria-hidden="true">·</span>
                  <span className="inline-flex items-center gap-1"><Tag className="h-3 w-3" /> {topic.mention_count} mention{topic.mention_count === 1 ? '' : 's'}</span>
                </p>
              </Link>
            ))}
          </div>

          {pagination.num_pages > 1 && (
            <div className="mt-6 flex items-center justify-between">
              <p className="text-xs text-muted dark:text-muted-dark">Page {pagination.page} of {pagination.num_pages}</p>
              <div className="flex gap-1.5">
                {pagination.has_previous && (
                  <button onClick={() => setSearchParams({ ...(query ? { q: query } : {}), ...(selectedType ? { type: selectedType } : {}), page: String(pagination.page - 1) })} className="inline-flex items-center gap-1 rounded-lg border border-line px-3 py-1.5 text-xs font-medium text-ink hover:bg-surface dark:border-line-dark dark:text-ink-dark dark:hover:bg-white/5">Previous</button>
                )}
                {pagination.has_next && (
                  <button onClick={() => setSearchParams({ ...(query ? { q: query } : {}), ...(selectedType ? { type: selectedType } : {}), page: String(pagination.page + 1) })} className="inline-flex items-center gap-1 rounded-lg border border-line px-3 py-1.5 text-xs font-medium text-ink hover:bg-surface dark:border-line-dark dark:text-ink-dark dark:hover:bg-white/5">Next</button>
                )}
              </div>
            </div>
          )}
        </>
      ) : (
        <div className="rounded-xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">
          <EmptyState icon={Compass} title="No topics yet" message="Topics are discovered automatically while your documents are processed. Upload a document to get started." actionTo="/documents" actionLabel="Go to Documents" />
        </div>
      )}
    </>
  );
}
