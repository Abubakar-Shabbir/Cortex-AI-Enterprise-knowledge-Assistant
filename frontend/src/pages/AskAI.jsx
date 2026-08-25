import { useMemo, useRef, useState } from 'react';
import DOMPurify from 'dompurify';
import { marked } from 'marked';
import {
  BookOpen,
  Filter,
  History,
  Loader2,
  RotateCcw,
  Send,
  Sparkles,
  Square,
  StopCircle,
  WandSparkles,
  X,
} from 'lucide-react';
import { streamAsk, useAskContext, useAskLog } from '../api/hooks';
import AskResult from '../components/AskResult';

export default function AskAI() {
  const { data: context, isLoading: contextLoading } = useAskContext();
  const [question, setQuestion] = useState('');
  const [documentIds, setDocumentIds] = useState([]);
  const [showFilters, setShowFilters] = useState(false);
  const [fileTypes, setFileTypes] = useState([]);
  const [uploadedAfter, setUploadedAfter] = useState('');
  const [uploadedBefore, setUploadedBefore] = useState('');
  const [collectionId, setCollectionId] = useState('');
  const [categoryId, setCategoryId] = useState('');
  const [tagId, setTagId] = useState('');
  const [orgLibraryOnly, setOrgLibraryOnly] = useState(false);

  const [submitting, setSubmitting] = useState(false);
  const [liveText, setLiveText] = useState('');
  const [streamedResult, setStreamedResult] = useState(null);
  const [viewedLogId, setViewedLogId] = useState(null);
  const [streamError, setStreamError] = useState('');
  const abortRef = useRef(null);
  const textareaRef = useRef(null);

  const { data: logResult } = useAskLog(viewedLogId);

  const activeFilterCount = [
    fileTypes.length > 0, uploadedAfter, uploadedBefore, collectionId, categoryId, tagId, orgLibraryOnly,
  ].filter(Boolean).length;

  const appliedFilterLabels = useMemo(() => {
    if (!streamedResult && !logResult) return [];
    const labels = [];
    if (documentIds.length) labels.push(`Documents: ${documentIds.length} selected`);
    if (collectionId) labels.push(`Collection: ${context?.collections.find((c) => String(c.id) === collectionId)?.name}`);
    if (categoryId) labels.push(`Category: ${context?.categories.find((c) => String(c.id) === categoryId)?.name}`);
    if (tagId) labels.push(`Tag: ${context?.tags.find((t) => String(t.id) === tagId)?.name}`);
    if (orgLibraryOnly) labels.push('Organization Library only');
    if (fileTypes.length) labels.push(`Type: ${fileTypes.map((t) => t.toUpperCase()).join(', ')}`);
    if (uploadedAfter) labels.push(`After ${uploadedAfter}`);
    if (uploadedBefore) labels.push(`Before ${uploadedBefore}`);
    return labels;
  }, [streamedResult, logResult, documentIds, collectionId, categoryId, tagId, orgLibraryOnly, fileTypes, uploadedAfter, uploadedBefore, context]);

  const buildPayload = (q) => ({
    question: q,
    document_ids: documentIds,
    file_types: fileTypes,
    uploaded_after: uploadedAfter || null,
    uploaded_before: uploadedBefore || null,
    collection_id: collectionId || null,
    category_id: categoryId || null,
    tag_id: tagId || null,
    org_library_only: orgLibraryOnly,
  });

  const ask = async (q) => {
    if (!q.trim() || submitting) return;
    setSubmitting(true);
    setStreamError('');
    setLiveText('');
    setStreamedResult(null);
    setViewedLogId(null);

    abortRef.current = new AbortController();
    let firstToken = true;

    try {
      await streamAsk(buildPayload(q), {
        signal: abortRef.current.signal,
        onToken: (text) => {
          firstToken = false;
          setLiveText((prev) => prev + text);
        },
        onDone: (result) => {
          setStreamedResult(result);
          setLiveText('');
        },
        onError: () => {
          setStreamError(firstToken
            ? 'Could not reach the AI service. Please try again.'
            : 'Connection interrupted - the response above may be incomplete.');
        },
      });
    } catch (err) {
      if (err.name !== 'AbortError') setStreamError('Could not reach the AI service. Please try again.');
    }

    setSubmitting(false);
    abortRef.current = null;
  };

  const stopStreaming = () => abortRef.current?.abort();

  const useQuestion = (text) => {
    setQuestion(text);
    textareaRef.current?.focus();
    textareaRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  };

  const toggleDocument = (id) => {
    const key = String(id);
    setDocumentIds((prev) =>
      prev.includes(key) ? prev.filter((x) => x !== key) : [...prev, key],
    );
  };

  const clearScope = () => setDocumentIds([]);

  const displayedResult = streamedResult || logResult || null;
  const liveHtml = liveText ? DOMPurify.sanitize(marked.parse(liveText)) : '';
  const docs = context?.documents || [];

  return (
    <div className="fade-in-up relative -mx-4 sm:-mx-6 lg:-mx-8">
      {/* Hero band */}
      <div className="ask-hero-mesh relative border-b border-line px-4 pb-8 pt-2 dark:border-line-dark sm:px-6 lg:px-8">
        <div className="mx-auto max-w-[1600px]">
          <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
            <div className="flex items-start gap-4">
              <div className="relative flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-primary to-primary-light text-white shadow-soft">
                <Sparkles className="h-6 w-6" />
                <span className="absolute -right-1 -top-1 flex h-3 w-3">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary-soft opacity-60" />
                  <span className="relative inline-flex h-3 w-3 rounded-full bg-primary-soft" />
                </span>
              </div>
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-primary dark:text-primary-soft">
                  Knowledge Assistant
                </p>
                <h1 className="mt-0.5 text-3xl font-bold tracking-tight text-ink dark:text-ink-dark">
                  Ask AI
                </h1>
                <p className="mt-1.5 max-w-xl text-sm leading-relaxed text-muted dark:text-muted-dark">
                  Grounded answers from your documents — every claim cites the exact chunk it came from.
                </p>
              </div>
            </div>

            <div className="flex flex-wrap gap-2">
              <div className="rounded-xl border border-line/80 bg-card/80 px-3.5 py-2 backdrop-blur-sm dark:border-line-dark dark:bg-card-dark/80">
                <p className="text-[10px] font-semibold uppercase tracking-wide text-muted dark:text-muted-dark">Documents</p>
                <p className="text-sm font-bold text-ink dark:text-ink-dark">{docs.length}</p>
              </div>
              <div className="rounded-xl border border-line/80 bg-card/80 px-3.5 py-2 backdrop-blur-sm dark:border-line-dark dark:bg-card-dark/80">
                <p className="text-[10px] font-semibold uppercase tracking-wide text-muted dark:text-muted-dark">Scope</p>
                <p className="text-sm font-bold text-ink dark:text-ink-dark">
                  {documentIds.length ? `${documentIds.length} selected` : 'All'}
                </p>
              </div>
            </div>
          </div>

          {/* Composer */}
          <form
            onSubmit={(e) => { e.preventDefault(); ask(question); }}
            className="relative overflow-hidden rounded-2xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark"
          >
            <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-primary/40 to-transparent" />

            <div className="p-4 sm:p-5">
              <label className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted dark:text-muted-dark">
                <BookOpen className="h-3.5 w-3.5 text-primary dark:text-primary-soft" />
                Your question
              </label>
              <textarea
                ref={textareaRef}
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                rows={4}
                maxLength={2000}
                required
                placeholder="e.g. What are the key findings in the Q3 report?"
                className="w-full resize-none rounded-xl border border-transparent bg-surface/80 p-4 text-[15px] leading-relaxed text-ink placeholder:text-muted/80 focus:border-primary/30 focus:bg-surface focus:outline-none focus:ring-2 focus:ring-primary/15 dark:bg-white/[0.04] dark:text-ink-dark dark:placeholder:text-muted-dark dark:focus:bg-white/[0.06]"
                onKeyDown={(e) => {
                  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
                    e.preventDefault();
                    ask(question);
                  }
                }}
              />

              <div className="mt-2 flex items-center justify-between gap-3">
                <span className="text-[11px] text-muted dark:text-muted-dark">
                  <kbd className="rounded-md border border-line bg-card px-1.5 py-0.5 font-mono text-[10px] dark:border-line-dark dark:bg-card-dark">
                    Ctrl
                  </kbd>
                  {' + '}
                  <kbd className="rounded-md border border-line bg-card px-1.5 py-0.5 font-mono text-[10px] dark:border-line-dark dark:bg-card-dark">
                    Enter
                  </kbd>
                  {' '}to ask
                </span>
                <span className={`text-[11px] tabular-nums ${question.length > 1800 ? 'text-warning' : 'text-muted dark:text-muted-dark'}`}>
                  {question.length} / 2000
                </span>
              </div>
            </div>

            {/* Document scope chips */}
            {docs.length > 0 && (
              <div className="border-t border-line px-4 py-3 dark:border-line-dark sm:px-5">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <p className="text-xs font-semibold text-muted dark:text-muted-dark">
                    Search in documents
                    <span className="ml-1.5 font-normal text-muted/80">(optional — leave empty for all)</span>
                  </p>
                  {documentIds.length > 0 && (
                    <button
                      type="button"
                      onClick={clearScope}
                      className="inline-flex items-center gap-1 text-[11px] font-semibold text-primary hover:underline dark:text-primary-soft"
                    >
                      <X className="h-3 w-3" /> Clear
                    </button>
                  )}
                </div>
                <div className="flex max-h-28 flex-wrap gap-1.5 overflow-y-auto">
                  {docs.map((d) => {
                    const selected = documentIds.includes(String(d.id));
                    return (
                      <button
                        key={d.id}
                        type="button"
                        onClick={() => toggleDocument(d.id)}
                        className={`max-w-[220px] truncate rounded-full border px-3 py-1.5 text-xs font-medium transition-all ${
                          selected
                            ? 'border-primary bg-primary/10 text-primary shadow-softer dark:border-primary-soft dark:bg-primary/20 dark:text-primary-soft'
                            : 'border-line text-ink hover:border-primary/40 hover:text-primary dark:border-line-dark dark:text-ink-dark dark:hover:border-primary-soft/50 dark:hover:text-primary-soft'
                        }`}
                        title={d.title}
                      >
                        {d.title}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Actions */}
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line bg-surface/50 px-4 py-3 dark:border-line-dark dark:bg-white/[0.02] sm:px-5">
              <button
                type="button"
                onClick={() => setShowFilters((v) => !v)}
                className={`inline-flex items-center gap-2 rounded-xl border px-3.5 py-2 text-xs font-semibold transition-colors ${
                  showFilters || activeFilterCount > 0
                    ? 'border-primary/35 bg-primary/5 text-primary dark:border-primary-soft/40 dark:text-primary-soft'
                    : 'border-line text-ink hover:border-primary/30 hover:text-primary dark:border-line-dark dark:text-ink-dark'
                }`}
              >
                <Filter className="h-3.5 w-3.5" />
                Advanced filters
                {activeFilterCount > 0 && (
                  <span className="flex h-5 min-w-5 items-center justify-center rounded-full bg-primary px-1.5 text-[10px] font-bold text-white dark:bg-primary-soft dark:text-card-dark">
                    {activeFilterCount}
                  </span>
                )}
              </button>

              {!submitting ? (
                <button
                  type="submit"
                  disabled={!question.trim()}
                  className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-primary to-primary-light px-5 py-2.5 text-sm font-semibold text-white shadow-soft transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-45"
                >
                  <Send className="h-4 w-4" />
                  Ask AI
                </button>
              ) : (
                <button
                  type="button"
                  onClick={stopStreaming}
                  className="inline-flex items-center gap-2 rounded-xl border border-danger/30 bg-danger/5 px-5 py-2.5 text-sm font-semibold text-danger transition hover:bg-danger/10 dark:border-danger-dark/40 dark:text-danger-dark"
                >
                  <StopCircle className="h-4 w-4" />
                  Stop generating
                </button>
              )}
            </div>

            {showFilters && (
              <div className="grid grid-cols-1 gap-4 border-t border-line bg-surface/70 p-4 dark:border-line-dark dark:bg-white/[0.03] sm:grid-cols-3 sm:p-5">
                <div>
                  <span className="mb-2 block text-xs font-semibold text-muted dark:text-muted-dark">File type</span>
                  <div className="flex flex-wrap gap-2">
                    {(context?.allowed_file_extensions || []).map((ext) => {
                      const on = fileTypes.includes(ext);
                      return (
                        <button
                          key={ext}
                          type="button"
                          onClick={() =>
                            setFileTypes((prev) =>
                              on ? prev.filter((t) => t !== ext) : [...prev, ext],
                            )
                          }
                          className={`rounded-lg border px-2.5 py-1.5 text-xs font-semibold transition ${
                            on
                              ? 'border-primary bg-primary text-white dark:border-primary-soft dark:bg-primary-soft dark:text-card-dark'
                              : 'border-line text-ink hover:border-primary/40 dark:border-line-dark dark:text-ink-dark'
                          }`}
                        >
                          {ext.toUpperCase()}
                        </button>
                      );
                    })}
                  </div>
                </div>
                <div>
                  <label className="mb-1.5 block text-xs font-semibold text-muted dark:text-muted-dark">Uploaded after</label>
                  <input type="date" value={uploadedAfter} onChange={(e) => setUploadedAfter(e.target.value)} className="w-full rounded-xl border border-line bg-card px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/15 dark:border-line-dark dark:bg-white/5 dark:text-ink-dark" />
                </div>
                <div>
                  <label className="mb-1.5 block text-xs font-semibold text-muted dark:text-muted-dark">Uploaded before</label>
                  <input type="date" value={uploadedBefore} onChange={(e) => setUploadedBefore(e.target.value)} className="w-full rounded-xl border border-line bg-card px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/15 dark:border-line-dark dark:bg-white/5 dark:text-ink-dark" />
                </div>
                <div>
                  <label className="mb-1.5 block text-xs font-semibold text-muted dark:text-muted-dark">Collection</label>
                  <select value={collectionId} onChange={(e) => setCollectionId(e.target.value)} className="w-full rounded-xl border border-line bg-card px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none dark:border-line-dark dark:bg-white/5 dark:text-ink-dark">
                    <option value="">Any collection</option>
                    {context?.collections?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                  </select>
                </div>
                <div>
                  <label className="mb-1.5 block text-xs font-semibold text-muted dark:text-muted-dark">Category</label>
                  <select value={categoryId} onChange={(e) => setCategoryId(e.target.value)} className="w-full rounded-xl border border-line bg-card px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none dark:border-line-dark dark:bg-white/5 dark:text-ink-dark">
                    <option value="">Any category</option>
                    {context?.categories?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                  </select>
                </div>
                <div>
                  <label className="mb-1.5 block text-xs font-semibold text-muted dark:text-muted-dark">Tag</label>
                  <select value={tagId} onChange={(e) => setTagId(e.target.value)} className="w-full rounded-xl border border-line bg-card px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none dark:border-line-dark dark:bg-white/5 dark:text-ink-dark">
                    <option value="">Any tag</option>
                    {context?.tags?.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                  </select>
                </div>
                <div className="flex items-end sm:col-span-3">
                  <label className="flex cursor-pointer items-center gap-2.5 rounded-xl border border-line bg-card px-3.5 py-2.5 text-sm text-ink dark:border-line-dark dark:bg-white/5 dark:text-ink-dark">
                    <input
                      type="checkbox"
                      checked={orgLibraryOnly}
                      onChange={(e) => setOrgLibraryOnly(e.target.checked)}
                      className="rounded border-line text-primary focus:ring-primary/30 dark:border-line-dark"
                    />
                    Organization Library only
                  </label>
                </div>
              </div>
            )}
          </form>

          {/* Suggested */}
          {context?.suggested_questions?.length > 0 && (
            <div className="mt-5">
              <div className="mb-2.5 flex items-center gap-1.5 text-xs font-semibold text-muted dark:text-muted-dark">
                <WandSparkles className="h-3.5 w-3.5 text-primary dark:text-primary-soft" />
                Suggested from your knowledge graph
              </div>
              <div className="flex flex-wrap gap-2">
                {context.suggested_questions.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => useQuestion(s)}
                    className="group rounded-full border border-line bg-card/90 px-3.5 py-2 text-left text-xs font-medium text-ink shadow-softer transition hover:-translate-y-0.5 hover:border-primary/40 hover:text-primary hover:shadow-soft dark:border-line-dark dark:bg-card-dark dark:text-ink-dark dark:hover:border-primary-soft/50 dark:hover:text-primary-soft"
                  >
                    <span className="mr-1.5 inline-block text-primary/50 transition group-hover:text-primary dark:text-primary-soft/50">✦</span>
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Results + history */}
      <div className="mx-auto grid max-w-[1600px] grid-cols-1 gap-6 px-4 py-6 sm:px-6 lg:grid-cols-3 lg:px-8 lg:py-8">
        <div className="min-w-0 space-y-5 lg:col-span-2">
          {contextLoading && !context ? (
            <div className="animate-pulse space-y-3 rounded-2xl border border-line bg-card p-6 dark:border-line-dark dark:bg-card-dark">
              <div className="h-3 w-24 rounded bg-surface dark:bg-white/10" />
              <div className="h-4 w-full rounded bg-surface dark:bg-white/10" />
              <div className="h-4 w-5/6 rounded bg-surface dark:bg-white/10" />
              <div className="h-4 w-2/3 rounded bg-surface dark:bg-white/10" />
            </div>
          ) : null}

          {submitting && liveText === '' && !streamError ? (
            <div className="overflow-hidden rounded-2xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">
              <div className="flex items-center gap-2 border-b border-line bg-primary/5 px-5 py-3 dark:border-line-dark dark:bg-primary/10">
                <Loader2 className="h-4 w-4 animate-spin text-primary dark:text-primary-soft" />
                <span className="text-xs font-semibold uppercase tracking-wide text-primary dark:text-primary-soft">
                  Retrieving &amp; thinking
                </span>
              </div>
              <div className="space-y-3 px-5 py-6" aria-live="polite" aria-label="Thinking">
                <div className="h-3 w-full animate-pulse rounded bg-surface dark:bg-white/10" />
                <div className="h-3 w-[92%] animate-pulse rounded bg-surface dark:bg-white/10" style={{ animationDelay: '80ms' }} />
                <div className="h-3 w-[78%] animate-pulse rounded bg-surface dark:bg-white/10" style={{ animationDelay: '160ms' }} />
                <div className="mt-4 flex items-center gap-2">
                  <span className="h-4 w-4 animate-spin rounded-full border-2 border-line border-t-primary dark:border-line-dark dark:border-t-primary-soft" />
                  <span className="text-xs text-muted dark:text-muted-dark">Searching your knowledge base…</span>
                </div>
              </div>
            </div>
          ) : submitting && liveText ? (
            <div className="overflow-hidden rounded-2xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">
              <div className="flex items-center justify-between gap-2 border-b border-line px-5 py-3 dark:border-line-dark">
                <div className="flex items-center gap-2">
                  <span className="relative flex h-2 w-2">
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-success opacity-60" />
                    <span className="relative inline-flex h-2 w-2 rounded-full bg-success" />
                  </span>
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-muted dark:text-muted-dark">
                    Streaming answer
                  </h3>
                </div>
                <button
                  type="button"
                  onClick={stopStreaming}
                  className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-[11px] font-semibold text-muted hover:bg-surface hover:text-danger dark:hover:bg-white/5"
                >
                  <Square className="h-3 w-3" /> Stop
                </button>
              </div>
              <div className="px-5 py-5">
                <div
                  className="streaming-cursor text-sm leading-relaxed text-ink dark:text-ink-dark [&>*+*]:mt-3"
                  dangerouslySetInnerHTML={{ __html: liveHtml }}
                />
              </div>
            </div>
          ) : (
            <AskResult result={displayedResult} appliedFilterLabels={appliedFilterLabels} onAskAgain={useQuestion} />
          )}

          {streamError && (
            <div className="flex items-start gap-3 rounded-2xl border border-danger/25 bg-danger/5 px-4 py-3.5 text-xs dark:border-danger/35 dark:bg-danger/10">
              <div className="min-w-0 flex-1">
                <p className="font-semibold text-danger dark:text-danger-dark">Connection interrupted</p>
                <p className="mt-0.5 text-danger/80 dark:text-danger/70">{streamError}</p>
              </div>
              <button
                type="button"
                onClick={() => ask(question)}
                className="shrink-0 self-center rounded-xl border border-danger/30 px-3 py-1.5 text-xs font-semibold text-danger transition hover:bg-danger/10"
              >
                Retry
              </button>
            </div>
          )}
        </div>

        {/* Recent questions panel */}
        <aside className="h-fit overflow-hidden rounded-2xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark lg:sticky lg:top-20">
          <div className="flex items-center gap-2 border-b border-line bg-gradient-to-r from-primary/5 to-transparent px-5 py-4 dark:border-line-dark dark:from-primary/15">
            <History className="h-4 w-4 text-primary dark:text-primary-soft" />
            <h2 className="text-sm font-semibold text-ink dark:text-ink-dark">Recent questions</h2>
          </div>
          <div className="max-h-[28rem] divide-y divide-line overflow-y-auto dark:divide-line-dark">
            {context?.recent_questions?.length ? (
              context.recent_questions.map((log) => {
                const active = viewedLogId === log.id;
                return (
                  <div
                    key={log.id}
                    className={`group flex items-stretch gap-0.5 transition-colors ${
                      active ? 'bg-primary/5 dark:bg-primary/15' : 'hover:bg-surface dark:hover:bg-white/[0.04]'
                    }`}
                  >
                    <button
                      type="button"
                      onClick={() => { setStreamedResult(null); setViewedLogId(log.id); }}
                      className="min-w-0 flex-1 px-4 py-3.5 text-left"
                    >
                      <p className="line-clamp-2 text-sm font-medium leading-snug text-ink dark:text-ink-dark">
                        {log.question}
                      </p>
                      <div className="mt-1.5 flex items-center gap-2">
                        <span
                          className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                            log.confidence >= 70
                              ? 'bg-success/10 text-success dark:text-success-dark'
                              : log.confidence >= 40
                                ? 'bg-warning/10 text-warning dark:text-warning-dark'
                                : 'bg-danger/10 text-danger dark:text-danger-dark'
                          }`}
                        >
                          {log.confidence}%
                        </span>
                        <span className="text-[11px] text-muted dark:text-muted-dark">confidence</span>
                      </div>
                    </button>
                    <button
                      type="button"
                      onClick={() => useQuestion(log.question)}
                      title="Ask again"
                      className="mr-2 self-center rounded-lg p-2 text-muted opacity-0 transition group-hover:opacity-100 hover:bg-line/60 hover:text-primary dark:text-muted-dark dark:hover:bg-white/10 dark:hover:text-primary-soft"
                    >
                      <RotateCcw className="h-3.5 w-3.5" />
                    </button>
                  </div>
                );
              })
            ) : (
              <div className="px-5 py-12 text-center">
                <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 text-primary dark:bg-primary/20 dark:text-primary-soft">
                  <History className="h-4 w-4" />
                </div>
                <p className="text-sm font-medium text-ink dark:text-ink-dark">No questions yet</p>
                <p className="mt-1 text-xs text-muted dark:text-muted-dark">
                  Your recent asks will show up here for quick revisit.
                </p>
              </div>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}
