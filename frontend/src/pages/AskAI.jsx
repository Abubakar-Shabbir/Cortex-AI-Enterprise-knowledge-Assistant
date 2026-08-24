import { useMemo, useRef, useState } from 'react';
import DOMPurify from 'dompurify';
import { marked } from 'marked';
import { Loader2, RotateCcw, Send, Sparkles, WandSparkles } from 'lucide-react';
import { streamAsk, useAskContext, useAskLog } from '../api/hooks';
import AskResult from '../components/AskResult';

// Port of templates/ask_ai.html. Streaming reuses the exact same SSE
// contract as the classic page's streamAnswer() (RAG.views.ask_ai_stream)
// - just against /api/ask/stream/ (RAG/api/ask_views.py), which sends
// the final structured result as JSON instead of a server-rendered
// HTML partial, since a React page renders its own DOM (AskResult.jsx
// mirrors partials/_ask_ai_result.html's markup 1:1).
//
// The Select-Documents modal dialog (partials/_select_documents_dialog.html)
// is simplified here to a plain multi-select for this increment - same
// underlying filter (document_ids), different picker UI. See the
// migration's final report for that trade-off.
export default function AskAI() {
  const { data: context } = useAskContext();
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
          setStreamError(firstToken ? 'Could not reach the AI service. Please try again.' : 'Connection interrupted - the response above may be incomplete.');
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

  const displayedResult = streamedResult || logResult || null;
  const liveHtml = liveText ? DOMPurify.sanitize(marked.parse(liveText)) : '';

  return (
    <div>
      <div className="mb-6 flex items-center gap-3">
        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-primary-light text-white shadow-soft">
          <Sparkles className="h-5 w-5" />
        </div>
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-ink dark:text-ink-dark">AI Search</h1>
          <p className="text-sm text-muted dark:text-muted-dark">Ask anything about your uploaded documents — answers are grounded only in retrieved context.</p>
        </div>
      </div>

      {context?.suggested_questions?.length > 0 && (
        <div className="mb-6 flex flex-wrap items-center gap-2">
          <span className="flex items-center gap-1 text-xs font-medium text-muted dark:text-muted-dark"><WandSparkles className="h-3.5 w-3.5" /> Suggested:</span>
          {context.suggested_questions.map((s) => (
            <button key={s} type="button" onClick={() => useQuestion(s)} className="rounded-full border border-line px-3 py-1.5 text-xs font-medium text-ink transition-all duration-150 hover:-translate-y-0.5 hover:border-primary hover:text-primary hover:shadow-softer dark:border-line-dark dark:text-ink-dark dark:hover:border-primary-soft dark:hover:text-primary-soft">
              {s}
            </button>
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="min-w-0 space-y-6 lg:col-span-2">
          <div className="rounded-xl border border-line bg-card p-5 shadow-soft dark:border-line-dark dark:bg-card-dark">
            <form onSubmit={(e) => { e.preventDefault(); ask(question); }}>
              <textarea
                ref={textareaRef}
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                rows={4}
                maxLength={2000}
                required
                placeholder="e.g. What are the key findings in the Q3 report?"
                className="w-full resize-none rounded-lg border border-line bg-surface p-3.5 text-sm text-ink placeholder:text-muted focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/15 dark:border-line-dark dark:bg-white/5 dark:text-ink-dark dark:placeholder:text-muted-dark"
                onKeyDown={(e) => { if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); ask(question); } }}
              />

              <div className="mt-1 flex items-center justify-between">
                <span className="text-[11px] text-muted dark:text-muted-dark"><kbd className="rounded border border-line px-1 py-0.5 font-mono dark:border-line-dark">Ctrl+Enter</kbd> to ask</span>
                <span className="text-[11px] text-muted dark:text-muted-dark">{question.length} / 2000</span>
              </div>

              <div className="mt-3 flex flex-wrap items-end justify-between gap-3">
                <div className="flex flex-wrap items-end gap-3">
                  <div>
                    <label className="mb-1.5 block text-xs font-medium text-muted dark:text-muted-dark">Search in</label>
                    <select
                      multiple
                      value={documentIds}
                      onChange={(e) => setDocumentIds(Array.from(e.target.selectedOptions, (o) => o.value))}
                      className="h-9 min-w-[180px] rounded-lg border border-line bg-surface px-2 py-1 text-xs text-ink focus:border-primary focus:outline-none dark:border-line-dark dark:bg-white/5 dark:text-ink-dark"
                    >
                      {context?.documents.map((d) => <option key={d.id} value={d.id}>{d.title}</option>)}
                    </select>
                  </div>

                  <button
                    type="button"
                    onClick={() => setShowFilters((v) => !v)}
                    className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-2 text-xs font-medium transition-colors ${showFilters ? 'border-primary/40 text-primary dark:text-primary-soft' : 'border-line text-ink hover:border-primary/30 hover:text-primary dark:border-line-dark dark:text-ink-dark'}`}
                  >
                    Advanced Filters
                    {activeFilterCount > 0 && <span className="flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 text-[10px] font-bold text-white dark:bg-primary-soft dark:text-card-dark">{activeFilterCount}</span>}
                  </button>
                </div>

                {!submitting ? (
                  <button type="submit" className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-primary-dark">
                    <Send className="h-4 w-4" /> <span>Ask AI</span>
                  </button>
                ) : (
                  <button type="button" onClick={stopStreaming} className="inline-flex items-center gap-2 rounded-lg border border-line bg-surface px-4 py-2.5 text-sm font-semibold text-ink transition-colors hover:border-danger/40 hover:text-danger dark:border-line-dark dark:bg-white/5 dark:text-ink-dark">
                    <Loader2 className="h-4 w-4 animate-spin" /> <span>Stop generating</span>
                  </button>
                )}
              </div>

              {showFilters && (
                <div className="mt-4 grid grid-cols-1 gap-4 rounded-lg border border-line bg-surface p-4 dark:border-line-dark dark:bg-white/5 sm:grid-cols-3">
                  <div>
                    <span className="mb-1.5 block text-xs font-medium text-muted dark:text-muted-dark">File type</span>
                    <div className="flex flex-wrap gap-3">
                      {context?.allowed_file_extensions.map((ext) => (
                        <label key={ext} className="flex items-center gap-1.5 text-sm text-ink dark:text-ink-dark">
                          <input
                            type="checkbox" checked={fileTypes.includes(ext)}
                            onChange={(e) => setFileTypes((prev) => e.target.checked ? [...prev, ext] : prev.filter((t) => t !== ext))}
                            className="rounded border-line text-primary focus:ring-primary/30 dark:border-line-dark"
                          />
                          {ext.toUpperCase()}
                        </label>
                      ))}
                    </div>
                  </div>
                  <div>
                    <label className="mb-1.5 block text-xs font-medium text-muted dark:text-muted-dark">Uploaded after</label>
                    <input type="date" value={uploadedAfter} onChange={(e) => setUploadedAfter(e.target.value)} className="w-full rounded-lg border border-line bg-card px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none dark:border-line-dark dark:bg-white/5 dark:text-ink-dark" />
                  </div>
                  <div>
                    <label className="mb-1.5 block text-xs font-medium text-muted dark:text-muted-dark">Uploaded before</label>
                    <input type="date" value={uploadedBefore} onChange={(e) => setUploadedBefore(e.target.value)} className="w-full rounded-lg border border-line bg-card px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none dark:border-line-dark dark:bg-white/5 dark:text-ink-dark" />
                  </div>
                  <div>
                    <label className="mb-1.5 block text-xs font-medium text-muted dark:text-muted-dark">Collection</label>
                    <select value={collectionId} onChange={(e) => setCollectionId(e.target.value)} className="w-full rounded-lg border border-line bg-card px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none dark:border-line-dark dark:bg-white/5 dark:text-ink-dark">
                      <option value="">Any collection</option>
                      {context?.collections.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="mb-1.5 block text-xs font-medium text-muted dark:text-muted-dark">Category</label>
                    <select value={categoryId} onChange={(e) => setCategoryId(e.target.value)} className="w-full rounded-lg border border-line bg-card px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none dark:border-line-dark dark:bg-white/5 dark:text-ink-dark">
                      <option value="">Any category</option>
                      {context?.categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="mb-1.5 block text-xs font-medium text-muted dark:text-muted-dark">Tag</label>
                    <select value={tagId} onChange={(e) => setTagId(e.target.value)} className="w-full rounded-lg border border-line bg-card px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none dark:border-line-dark dark:bg-white/5 dark:text-ink-dark">
                      <option value="">Any tag</option>
                      {context?.tags.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                    </select>
                  </div>
                  <div className="flex items-end sm:col-span-3">
                    <label className="flex items-center gap-2 text-sm text-ink dark:text-ink-dark">
                      <input type="checkbox" checked={orgLibraryOnly} onChange={(e) => setOrgLibraryOnly(e.target.checked)} className="rounded border-line text-primary focus:ring-primary/30 dark:border-line-dark" />
                      Organization Library only
                    </label>
                  </div>
                </div>
              )}
            </form>
          </div>

          {submitting && liveText === '' && !streamError ? (
            <div className="rounded-xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">
              <div className="px-5 py-5">
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted dark:text-muted-dark">Answer</h3>
                <span className="inline-flex items-center gap-1 py-1" aria-live="polite" aria-label="Thinking">
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted dark:bg-muted-dark" style={{ animationDelay: '0ms' }}></span>
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted dark:bg-muted-dark" style={{ animationDelay: '150ms' }}></span>
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted dark:bg-muted-dark" style={{ animationDelay: '300ms' }}></span>
                </span>
              </div>
            </div>
          ) : submitting && liveText ? (
            <div className="rounded-xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">
              <div className="px-5 py-5">
                <div className="mb-2 flex items-center gap-2">
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-muted dark:text-muted-dark">Answer</h3>
                  <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
                </div>
                <div className="streaming-cursor text-sm leading-relaxed text-ink dark:text-ink-dark [&>*+*]:mt-3" dangerouslySetInnerHTML={{ __html: liveHtml }} />
              </div>
            </div>
          ) : (
            <AskResult result={displayedResult} appliedFilterLabels={appliedFilterLabels} onAskAgain={useQuestion} />
          )}

          {streamError && (
            <div className="flex items-start gap-2.5 rounded-lg border border-danger/30 bg-danger/5 px-3.5 py-3 text-xs dark:border-danger/40 dark:bg-danger/10">
              <div className="min-w-0">
                <p className="font-medium text-danger">Connection interrupted</p>
                <p className="mt-0.5 text-danger/80 dark:text-danger/70">{streamError}</p>
              </div>
              <button type="button" onClick={() => ask(question)} className="ml-auto shrink-0 self-center rounded-lg border border-danger/30 px-2.5 py-1.5 text-xs font-semibold text-danger transition-colors hover:bg-danger/10">Retry</button>
            </div>
          )}
        </div>

        <div className="h-fit rounded-xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">
          <div className="border-b border-line px-5 py-4 dark:border-line-dark">
            <h2 className="text-sm font-semibold text-ink dark:text-ink-dark">Recent Questions</h2>
          </div>
          <div className="divide-y divide-line dark:divide-line-dark">
            {context?.recent_questions?.length ? context.recent_questions.map((log) => (
              <div key={log.id} className="group flex items-center gap-1 px-2 py-1.5 transition-colors hover:bg-surface dark:hover:bg-white/5">
                <button
                  type="button"
                  onClick={() => { setStreamedResult(null); setViewedLogId(log.id); }}
                  className="min-w-0 flex-1 rounded-lg px-3 py-2 text-left"
                >
                  <p className="truncate text-sm font-medium text-ink dark:text-ink-dark">{log.question}</p>
                  <p className="mt-0.5 text-xs text-muted dark:text-muted-dark">{log.confidence}% confidence</p>
                </button>
                <button type="button" onClick={() => useQuestion(log.question)} title="Ask again" className="shrink-0 rounded-lg p-2 text-muted opacity-0 transition-opacity hover:text-primary group-hover:opacity-100 dark:text-muted-dark dark:hover:text-primary-soft">
                  <RotateCcw className="h-3.5 w-3.5" />
                </button>
              </div>
            )) : (
              <p className="px-5 py-8 text-center text-sm text-muted dark:text-muted-dark">Your recent questions will appear here.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
