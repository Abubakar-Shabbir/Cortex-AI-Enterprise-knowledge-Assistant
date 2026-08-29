import { useEffect, useRef, useState } from 'react';
import DOMPurify from 'dompurify';
import { marked } from 'marked';
import {
  AlertTriangle,
  ChevronDown,
  RotateCcw,
  Send,
  SlidersHorizontal,
  Sparkles,
  Square,
  WandSparkles,
  X,
} from 'lucide-react';
import { api } from '../api/client';
import { streamAsk, useAskContext, useAskLog } from '../api/hooks';
import AskResult from '../components/AskResult';
import SelectDocumentsDialog from '../components/SelectDocumentsDialog';
import Skeleton from '../components/Skeleton';
import Spinner from '../components/Spinner';
import { timeAgo } from '../lib/timeAgo';

// Mirrors templates/ask_ai.html + partials/_ask_ai_result.html: one
// question form, one result panel that gets replaced wholesale by each
// new question (#ask-ai-result-container in the classic template) - not
// a scrolling multi-turn chat thread.
export default function AskAI() {
  const { data: context, isLoading: contextLoading } = useAskContext();
  const [question, setQuestion] = useState('');
  // {id: {id, title}} - same shape SelectDocumentsDialog (AI Tasks' own
  // document picker) already uses, so "which documents" has exactly one
  // picker UI in this app, not a second bespoke one just for Ask AI.
  const [selectedDocs, setSelectedDocs] = useState({});
  const [showFilters, setShowFilters] = useState(false);
  const [fileTypes, setFileTypes] = useState([]);
  const [uploadedAfter, setUploadedAfter] = useState('');
  const [uploadedBefore, setUploadedBefore] = useState('');
  const [collectionId, setCollectionId] = useState('');
  const [categoryId, setCategoryId] = useState('');
  const [tagId, setTagId] = useState('');
  const [orgLibraryOnly, setOrgLibraryOnly] = useState(false);

  // The single current question/answer - {question, appliedFilterLabels,
  // status, liveText, result, error}. null before the first question.
  const [current, setCurrent] = useState(null);
  const [viewedLogId, setViewedLogId] = useState(null);
  const abortRef = useRef(null);
  const textareaRef = useRef(null);
  const resultRef = useRef(null);

  const { data: logResult } = useAskLog(viewedLogId);

  // Clicking a past question in "Recent Questions" replays it - no new
  // retrieval/LLM call runs, matches ask_ai()'s ?log_id= GET branch.
  useEffect(() => {
    if (viewedLogId && logResult) {
      setCurrent({
        question: logResult.question,
        appliedFilterLabels: [],
        status: 'done',
        liveText: '',
        result: logResult,
        error: '',
      });
    }
  }, [viewedLogId, logResult]);

  const isBusy = current?.status === 'streaming';

  const documentIds = Object.keys(selectedDocs);

  const activeFilterCount = [
    fileTypes.length > 0, uploadedAfter, uploadedBefore, collectionId, categoryId, tagId, orgLibraryOnly,
  ].filter(Boolean).length;

  const collectionLabel = context?.collections?.find((c) => String(c.id) === collectionId)?.name;
  const categoryLabel = context?.categories?.find((c) => String(c.id) === categoryId)?.name;
  const tagLabel = context?.tags?.find((t) => String(t.id) === tagId)?.name;

  const buildAppliedFilterLabels = () => {
    const labels = [];
    if (documentIds.length) labels.push(`Documents: ${documentIds.length} selected`);
    if (collectionId) labels.push(`Collection: ${collectionLabel}`);
    if (categoryId) labels.push(`Category: ${categoryLabel}`);
    if (tagId) labels.push(`Tag: ${tagLabel}`);
    if (orgLibraryOnly) labels.push('Organization Library only');
    if (fileTypes.length) labels.push(`Type: ${fileTypes.map((t) => t.toUpperCase()).join(', ')}`);
    if (uploadedAfter) labels.push(`After ${uploadedAfter}`);
    if (uploadedBefore) labels.push(`Before ${uploadedBefore}`);
    return labels;
  };

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

  const patchCurrent = (patch) => {
    setCurrent((prev) => (prev ? { ...prev, ...(typeof patch === 'function' ? patch(prev) : patch) } : prev));
  };

  const ask = async (q) => {
    const text = q.trim();
    if (!text || isBusy) return;

    setViewedLogId(null);
    setCurrent({
      question: text, appliedFilterLabels: buildAppliedFilterLabels(),
      status: 'streaming', liveText: '', result: null, error: '',
    });
    setQuestion('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
    resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

    abortRef.current = new AbortController();
    let firstToken = true;

    // Mirrors ask_ai.html's streamAnswer(): a stream failure with zero
    // tokens rendered yet has nothing to lose, so it falls back to the
    // classic non-streaming /ask/ endpoint (still gets a real answer)
    // instead of a dead-end error. Once any token has landed, there's a
    // partial answer worth keeping - that case stays an inline error +
    // manual Retry rather than silently resubmitting over it.
    const fallbackToClassic = async () => {
      try {
        const result = await api.post('/ask/', buildPayload(text));
        patchCurrent({ status: 'done', result, liveText: '' });
      } catch {
        patchCurrent({ status: 'error', error: 'Could not reach the AI service. Please try again.' });
      }
    };

    try {
      await streamAsk(buildPayload(text), {
        signal: abortRef.current.signal,
        onToken: (chunk) => {
          firstToken = false;
          patchCurrent((c) => ({ liveText: (c.liveText || '') + chunk }));
        },
        onDone: (result) => {
          patchCurrent({ status: 'done', result, liveText: '' });
        },
        onError: () => {
          if (firstToken) fallbackToClassic();
          else patchCurrent({ status: 'error', error: 'Connection interrupted - the response above may be incomplete.' });
        },
      });
    } catch (err) {
      if (err.name !== 'AbortError') {
        if (firstToken) await fallbackToClassic();
        else patchCurrent({ status: 'error', error: 'Could not reach the AI service. Please try again.' });
      }
    }

    abortRef.current = null;
  };

  const stopStreaming = () => {
    abortRef.current?.abort();
    patchCurrent((c) => (c.status === 'streaming' ? { status: 'stopped' } : {}));
  };

  const applyQuestion = (text) => {
    setQuestion(text);
    textareaRef.current?.focus();
    textareaRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  };

  const onQuestionInput = (e) => {
    setQuestion(e.target.value);
    e.target.style.height = 'auto';
    e.target.style.height = `${Math.min(e.target.scrollHeight, 160)}px`;
  };

  const clearFilter = (key) => {
    if (key === 'fileTypes') setFileTypes([]);
    else if (key === 'collectionId') setCollectionId('');
    else if (key === 'categoryId') setCategoryId('');
    else if (key === 'tagId') setTagId('');
    else if (key === 'orgLibraryOnly') setOrgLibraryOnly(false);
    else if (key === 'uploadedAfter') setUploadedAfter('');
    else if (key === 'uploadedBefore') setUploadedBefore('');
  };

  const clearAllFilters = () => {
    setFileTypes([]);
    setUploadedAfter('');
    setUploadedBefore('');
    setCollectionId('');
    setCategoryId('');
    setTagId('');
    setOrgLibraryOnly(false);
  };

  return (
    <div className="fade-in-up">
      <div className="mb-6 flex items-center gap-3">
        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-primary-light text-white shadow-soft">
          <Sparkles className="h-5 w-5" />
        </div>
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-ink dark:text-ink-dark">AI Search</h1>
          <p className="text-sm text-muted dark:text-muted-dark">
            Ask anything about your uploaded documents — answers are grounded only in retrieved context.
          </p>
        </div>
      </div>

      {context?.suggested_questions?.length > 0 && (
        <div className="mb-6 flex flex-wrap items-center gap-2">
          <span className="flex items-center gap-1 text-xs font-medium text-muted dark:text-muted-dark">
            <WandSparkles className="h-3.5 w-3.5" /> Suggested:
          </span>
          {context.suggested_questions.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => applyQuestion(s)}
              className="rounded-full border border-line px-3 py-1.5 text-xs font-medium text-ink transition-all duration-150 hover:-translate-y-0.5 hover:border-primary hover:text-primary hover:shadow-softer dark:border-line-dark dark:text-ink-dark dark:hover:border-primary-soft dark:hover:text-primary-soft"
            >
              {s}
            </button>
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="min-w-0 space-y-6 lg:col-span-2">
          <div className="relative overflow-hidden rounded-xl border border-line bg-card p-5 shadow-soft dark:border-line-dark dark:bg-card-dark">
            <form onSubmit={(e) => { e.preventDefault(); ask(question); }}>
              <textarea
                ref={textareaRef}
                value={question}
                onChange={onQuestionInput}
                rows={4}
                maxLength={2000}
                required
                disabled={isBusy}
                placeholder="e.g. What are the key findings in the Q3 report?"
                className="w-full resize-none rounded-lg border border-line bg-surface p-3.5 text-sm text-ink placeholder:text-muted focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/15 disabled:cursor-not-allowed disabled:opacity-60 dark:border-line-dark dark:bg-white/5 dark:text-ink-dark dark:placeholder:text-muted-dark"
                onKeyDown={(e) => {
                  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
                    e.preventDefault();
                    ask(question);
                  }
                }}
              />

              <div className="mt-1 flex items-center justify-between">
                <span className="text-[11px] text-muted dark:text-muted-dark">
                  <kbd className="rounded border border-line px-1 py-0.5 font-mono dark:border-line-dark">Ctrl+Enter</kbd> to ask
                </span>
                <span className="text-[11px] text-muted dark:text-muted-dark">{question.length} / 2000</span>
              </div>

              <div className="mt-3 flex flex-wrap items-end justify-between gap-3">
                <div className="flex flex-wrap items-end gap-3">
                  <div>
                    <label className="mb-1.5 block text-xs font-medium text-muted dark:text-muted-dark">Search in</label>
                    <SelectDocumentsDialog selected={selectedDocs} onChange={setSelectedDocs} triggerLabel="All documents" />
                  </div>

                  <button
                    type="button"
                    onClick={() => setShowFilters((v) => !v)}
                    className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-2 text-xs font-medium transition-colors ${
                      showFilters
                        ? 'border-primary/40 text-primary dark:text-primary-soft'
                        : 'border-line text-ink hover:border-primary/30 hover:text-primary dark:border-line-dark dark:text-ink-dark'
                    }`}
                  >
                    <SlidersHorizontal className="h-3.5 w-3.5" /> Advanced Filters
                    {activeFilterCount > 0 && (
                      <span className="flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 text-[10px] font-bold text-white dark:bg-primary-soft dark:text-card-dark">
                        {activeFilterCount}
                      </span>
                    )}
                    <ChevronDown className={`h-3.5 w-3.5 transition-transform duration-150 ${showFilters ? 'rotate-180' : ''}`} />
                  </button>
                </div>

                {isBusy ? (
                  <button
                    type="button"
                    onClick={stopStreaming}
                    className="inline-flex items-center gap-2 rounded-lg border border-line bg-surface px-4 py-2.5 text-sm font-semibold text-ink transition-colors hover:border-danger/40 hover:text-danger dark:border-line-dark dark:bg-white/5 dark:text-ink-dark"
                  >
                    <Spinner size={16} className="text-ink dark:text-ink-dark" /> Stop generating
                  </button>
                ) : (
                  <button
                    type="submit"
                    disabled={!question.trim()}
                    className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-primary-dark disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <Send className="h-4 w-4" /> Ask AI
                  </button>
                )}
              </div>

              {/* Always visible, whether or not the Advanced Filters panel is
                  expanded - so a filter set earlier is never invisible. Each
                  chip clears just that one filter; "Clear all" resets
                  everything. */}
              {activeFilterCount > 0 && (
                <div className="mt-2 flex flex-wrap items-center gap-1.5">
                  <span className="text-[11px] font-medium text-muted dark:text-muted-dark">Active filters:</span>
                  {fileTypes.length > 0 && (
                    <FilterChip label={`Type: ${fileTypes.map((t) => t.toUpperCase()).join(', ')}`} onClear={() => clearFilter('fileTypes')} />
                  )}
                  {uploadedAfter && <FilterChip label={`After ${uploadedAfter}`} onClear={() => clearFilter('uploadedAfter')} />}
                  {uploadedBefore && <FilterChip label={`Before ${uploadedBefore}`} onClear={() => clearFilter('uploadedBefore')} />}
                  {collectionId && <FilterChip label={`Collection: ${collectionLabel}`} onClear={() => clearFilter('collectionId')} />}
                  {categoryId && <FilterChip label={`Category: ${categoryLabel}`} onClear={() => clearFilter('categoryId')} />}
                  {tagId && <FilterChip label={`Tag: ${tagLabel}`} onClear={() => clearFilter('tagId')} />}
                  {orgLibraryOnly && <FilterChip label="Organization Library only" onClear={() => clearFilter('orgLibraryOnly')} />}
                  <button
                    type="button"
                    onClick={clearAllFilters}
                    className="text-[11px] font-medium text-muted underline hover:text-ink dark:text-muted-dark dark:hover:text-ink-dark"
                  >
                    Clear all
                  </button>
                </div>
              )}

              {showFilters && (
                <div className="mt-4 grid grid-cols-1 gap-4 rounded-lg border border-line bg-surface p-4 dark:border-line-dark dark:bg-white/5 sm:grid-cols-3">
                  <div>
                    <span className="mb-1.5 block text-xs font-medium text-muted dark:text-muted-dark">File type</span>
                    <div className="flex flex-wrap gap-3">
                      {(context?.allowed_file_extensions || []).map((ext) => (
                        <label key={ext} className="flex items-center gap-1.5 text-sm text-ink dark:text-ink-dark">
                          <input
                            type="checkbox"
                            checked={fileTypes.includes(ext)}
                            onChange={(e) => setFileTypes((prev) => (e.target.checked ? [...prev, ext] : prev.filter((t) => t !== ext)))}
                            className="rounded border-line text-primary focus:ring-primary/30 dark:border-line-dark"
                          />
                          {ext.toUpperCase()}
                        </label>
                      ))}
                    </div>
                  </div>
                  <div>
                    <label className="mb-1.5 block text-xs font-medium text-muted dark:text-muted-dark">Uploaded after</label>
                    <input
                      type="date"
                      value={uploadedAfter}
                      onChange={(e) => setUploadedAfter(e.target.value)}
                      className="w-full rounded-lg border border-line bg-card px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/15 dark:border-line-dark dark:bg-white/5 dark:text-ink-dark"
                    />
                  </div>
                  <div>
                    <label className="mb-1.5 block text-xs font-medium text-muted dark:text-muted-dark">Uploaded before</label>
                    <input
                      type="date"
                      value={uploadedBefore}
                      onChange={(e) => setUploadedBefore(e.target.value)}
                      className="w-full rounded-lg border border-line bg-card px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/15 dark:border-line-dark dark:bg-white/5 dark:text-ink-dark"
                    />
                  </div>
                  <div>
                    <label className="mb-1.5 block text-xs font-medium text-muted dark:text-muted-dark">Collection</label>
                    <select
                      value={collectionId}
                      onChange={(e) => setCollectionId(e.target.value)}
                      disabled={!context?.collections?.length}
                      className="w-full rounded-lg border border-line bg-card px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/15 disabled:opacity-50 dark:border-line-dark dark:bg-white/5 dark:text-ink-dark"
                    >
                      <option value="">Any collection</option>
                      {context?.collections?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="mb-1.5 block text-xs font-medium text-muted dark:text-muted-dark">Category</label>
                    <select
                      value={categoryId}
                      onChange={(e) => setCategoryId(e.target.value)}
                      disabled={!context?.categories?.length}
                      className="w-full rounded-lg border border-line bg-card px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/15 disabled:opacity-50 dark:border-line-dark dark:bg-white/5 dark:text-ink-dark"
                    >
                      <option value="">Any category</option>
                      {context?.categories?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="mb-1.5 block text-xs font-medium text-muted dark:text-muted-dark">Tag</label>
                    <select
                      value={tagId}
                      onChange={(e) => setTagId(e.target.value)}
                      disabled={!context?.tags?.length}
                      className="w-full rounded-lg border border-line bg-card px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/15 disabled:opacity-50 dark:border-line-dark dark:bg-white/5 dark:text-ink-dark"
                    >
                      <option value="">Any tag</option>
                      {context?.tags?.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                    </select>
                  </div>
                  <div className="flex items-end sm:col-span-3">
                    <label className="flex items-center gap-2 text-sm text-ink dark:text-ink-dark">
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
          </div>

          <div ref={resultRef}>
            {contextLoading && !context ? (
              <LoadingSkeleton />
            ) : !current ? (
              <AskResult result={null} />
            ) : current.status === 'streaming' && !current.liveText ? (
              <ThinkingCard />
            ) : current.status === 'streaming' || current.status === 'stopped' || (current.status === 'error' && current.liveText) ? (
              <StreamingCard turn={current} onStop={stopStreaming} onRetry={() => ask(current.question)} />
            ) : current.status === 'error' ? (
              <ErrorCard error={current.error} onRetry={() => ask(current.question)} />
            ) : (
              <AskResult result={current.result} appliedFilterLabels={current.appliedFilterLabels} onAskAgain={applyQuestion} />
            )}
          </div>
        </div>

        <div className="h-fit overflow-hidden rounded-xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">
          <div className="border-b border-line px-5 py-4 dark:border-line-dark">
            <h2 className="text-sm font-semibold text-ink dark:text-ink-dark">Recent Questions</h2>
          </div>
          <div className="divide-y divide-line dark:divide-line-dark">
            {context?.recent_questions?.length ? (
              context.recent_questions.map((log) => (
                <div key={log.id} className="group flex items-center gap-1 px-2 py-1.5 transition-colors hover:bg-surface dark:hover:bg-white/5">
                  <button
                    type="button"
                    onClick={() => setViewedLogId(log.id)}
                    className={`min-w-0 flex-1 rounded-lg px-3 py-2 text-left ${viewedLogId === log.id ? 'bg-primary/5' : ''}`}
                  >
                    <p className="truncate text-sm font-medium text-ink dark:text-ink-dark">{log.question}</p>
                    <p className="mt-0.5 text-xs text-muted dark:text-muted-dark">
                      {log.confidence}% confidence · {timeAgo(log.created_at)} ago
                    </p>
                  </button>
                  <button
                    type="button"
                    onClick={() => applyQuestion(log.question)}
                    title="Ask again"
                    className="shrink-0 rounded-lg p-2 text-muted opacity-0 transition-opacity hover:text-primary group-hover:opacity-100 dark:text-muted-dark dark:hover:text-primary-soft"
                  >
                    <RotateCcw className="h-3.5 w-3.5" />
                  </button>
                </div>
              ))
            ) : (
              <p className="px-5 py-8 text-center text-sm text-muted dark:text-muted-dark">Your recent questions will appear here.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function FilterChip({ label, onClear }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary dark:text-primary-soft">
      {label}
      <button type="button" onClick={onClear}>
        <X className="h-3 w-3" />
      </button>
    </span>
  );
}

function LoadingSkeleton() {
  return (
    <div className="space-y-3 rounded-xl border border-line bg-card p-6 shadow-soft dark:border-line-dark dark:bg-card-dark">
      <Skeleton className="h-3 w-24" />
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-4 w-5/6" />
      <Skeleton className="h-4 w-2/3" />
    </div>
  );
}

// Slow first-token latency isn't an error - just reassures the user the
// request is still alive, matching ask_ai.html's #ask-ai-slow-hint timer.
function ThinkingCard() {
  const [showSlowHint, setShowSlowHint] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setShowSlowHint(true), 6000);
    return () => clearTimeout(timer);
  }, []);

  return (
    <div className="overflow-hidden rounded-xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">
      <div className="px-5 py-5">
        <div className="mb-2 flex items-center gap-2" aria-live="polite" aria-label="Thinking">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-muted dark:text-muted-dark">Answer</h3>
          <Spinner size={14} className="text-primary dark:text-primary-soft" label="Thinking" />
        </div>
        {showSlowHint && (
          <p className="mt-2 text-xs text-muted dark:text-muted-dark">Still working — complex questions can take a little longer…</p>
        )}
      </div>
    </div>
  );
}

function StreamingCard({ turn, onStop, onRetry }) {
  const liveHtml = turn.liveText ? DOMPurify.sanitize(marked.parse(turn.liveText)) : '';
  const isErrorAfterPartial = turn.status === 'error' && turn.liveText;

  return (
    <div className="overflow-hidden rounded-xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">
      <div className="px-5 py-5" id="ask-ai-live-card-body">
        <div className="mb-2 flex items-center gap-2">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-muted dark:text-muted-dark">Answer</h3>
          {turn.status === 'streaming' ? (
            <Spinner size={14} className="text-primary dark:text-primary-soft" />
          ) : isErrorAfterPartial ? (
            <AlertTriangle className="h-3.5 w-3.5 text-danger dark:text-danger-dark" />
          ) : null}
        </div>
        <div
          className={`text-sm leading-relaxed text-ink dark:text-ink-dark [&>*+*]:mt-3 [&_strong]:font-semibold [&_ul]:list-disc [&_ul]:space-y-1 [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:space-y-1 [&_ol]:pl-5 [&_code]:rounded [&_code]:bg-surface [&_code]:px-1 [&_code]:py-0.5 [&_code]:font-mono [&_code]:text-xs dark:[&_code]:bg-white/10 [&_pre]:overflow-x-auto [&_pre]:rounded-lg [&_pre]:bg-surface [&_pre]:p-3 [&_pre]:text-xs dark:[&_pre]:bg-white/5 [&_pre_code]:bg-transparent [&_pre_code]:p-0 ${turn.status === 'streaming' ? 'streaming-cursor' : ''}`}
          dangerouslySetInnerHTML={{ __html: liveHtml }}
        />
        {turn.status === 'streaming' && (
          <button
            type="button"
            onClick={onStop}
            className="mt-3 inline-flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1.5 text-xs font-semibold text-muted transition-colors hover:border-danger/40 hover:text-danger dark:border-line-dark dark:text-muted-dark"
          >
            <Square className="h-3 w-3" /> Stop generating
          </button>
        )}
        {isErrorAfterPartial && (
          <div className="mt-4 flex items-start gap-2.5 rounded-lg border border-danger/30 bg-danger/5 px-3.5 py-3 text-xs dark:border-danger/40 dark:bg-danger/10">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-danger" />
            <div className="min-w-0 flex-1">
              <p className="font-medium text-danger">Connection interrupted</p>
              <p className="mt-0.5 text-danger/80 dark:text-danger/70">
                The response above may be incomplete. This can happen if your connection drops or the AI provider is momentarily unavailable.
              </p>
            </div>
            <button
              type="button"
              onClick={onRetry}
              className="ml-auto shrink-0 self-center rounded-lg border border-danger/30 px-2.5 py-1.5 text-xs font-semibold text-danger transition-colors hover:bg-danger/10"
            >
              Retry
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function ErrorCard({ error, onRetry }) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-danger/25 bg-danger/5 px-4 py-3.5 text-xs dark:border-danger/35 dark:bg-danger/10">
      <div className="min-w-0 flex-1">
        <p className="font-semibold text-danger dark:text-danger-dark">Connection interrupted</p>
        <p className="mt-0.5 text-danger/80 dark:text-danger/70">{error}</p>
      </div>
      <button
        type="button"
        onClick={onRetry}
        className="shrink-0 self-center rounded-xl border border-danger/30 px-3 py-1.5 text-xs font-semibold text-danger transition hover:bg-danger/10"
      >
        Retry
      </button>
    </div>
  );
}
