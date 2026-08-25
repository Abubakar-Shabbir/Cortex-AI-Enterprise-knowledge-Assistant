import { useState } from 'react';
import {
  Check,
  Copy,
  FileText,
  Gauge,
  GitMerge,
  History,
  Layers,
  Quote,
  SearchX,
  ServerCrash,
  Sparkles,
  Timer,
} from 'lucide-react';

export default function AskResult({ result, appliedFilterLabels = [], onAskAgain }) {
  const [copied, setCopied] = useState(false);
  const [expanded, setExpanded] = useState({});

  if (!result) {
    return (
      <div className="relative overflow-hidden rounded-2xl border border-dashed border-line bg-card px-6 py-14 text-center dark:border-line-dark dark:bg-card-dark">
        <div className="pointer-events-none absolute inset-0 ask-hero-mesh opacity-60" aria-hidden="true" />
        <div className="relative mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-primary to-primary-light text-white shadow-soft">
          <Sparkles className="h-6 w-6" />
        </div>
        <p className="relative mt-4 text-base font-semibold text-ink dark:text-ink-dark">
          Ask your first question
        </p>
        <p className="relative mx-auto mt-1.5 max-w-md text-sm leading-relaxed text-muted dark:text-muted-dark">
          Every answer cites the exact document and chunk it came from — nothing is answered from outside your uploaded content.
        </p>
      </div>
    );
  }

  const copyAnswer = () => {
    navigator.clipboard.writeText(result.answer).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    });
  };

  const metric = (Icon, label, value, valueClass = 'text-ink dark:text-ink-dark') => (
    <div className="flex min-w-0 items-center gap-2.5 rounded-xl border border-line/80 bg-surface/60 px-3 py-2 dark:border-line-dark dark:bg-white/[0.03]">
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary dark:bg-primary/20 dark:text-primary-soft">
        <Icon className="h-3.5 w-3.5" />
      </span>
      <div className="min-w-0">
        <p className="text-[10px] font-semibold uppercase tracking-wide text-muted dark:text-muted-dark">{label}</p>
        <p className={`truncate text-xs font-semibold ${valueClass}`}>{value}</p>
      </div>
    </div>
  );

  return (
    <div className="overflow-hidden rounded-2xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">
      {result.from_history && (
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line bg-surface px-5 py-2.5 dark:border-line-dark dark:bg-white/5">
          <span className="flex items-center gap-1.5 text-xs font-medium text-muted dark:text-muted-dark">
            <History className="h-3.5 w-3.5" /> Viewing a past answer — no new search was run.
          </span>
          <button
            type="button"
            onClick={() => onAskAgain(result.question)}
            className="text-xs font-semibold text-primary hover:underline dark:text-primary-soft"
          >
            Ask again
          </button>
        </div>
      )}

      <div className="grid grid-cols-2 gap-2 border-b border-line p-4 dark:border-line-dark sm:grid-cols-3 lg:grid-cols-5">
        {metric(
          Gauge,
          'Confidence',
          `${result.confidence}%`,
          result.confidence >= 70
            ? 'text-success dark:text-success-dark'
            : result.confidence >= 40
              ? 'text-warning dark:text-warning-dark'
              : 'text-danger dark:text-danger-dark',
        )}
        {metric(Timer, 'Response', `${result.response_time_ms} ms`)}
        {metric(Layers, 'Chunks', String(result.sources?.length || 0))}
        {metric(Quote, 'Citations', String(result.citations?.length || 0))}
        {metric(GitMerge, 'Method', result.search_method || '—')}
      </div>

      {result.llm_provider && (
        <div className="flex flex-wrap items-center gap-2 border-b border-line px-5 py-2.5 text-xs text-muted dark:border-line-dark dark:text-muted-dark">
          Answered by{' '}
          <span className="font-semibold capitalize text-ink dark:text-ink-dark">{result.llm_provider}</span>
          <span className="font-mono text-[11px]">{result.llm_model}</span>
          {result.llm_fallback_used && (
            <span className="rounded-full bg-warning/10 px-2 py-0.5 text-[11px] font-semibold text-warning dark:text-warning-dark">
              Fallback
            </span>
          )}
        </div>
      )}

      {appliedFilterLabels.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 border-b border-line bg-primary/5 px-5 py-2.5 dark:border-line-dark dark:bg-primary/10">
          <span className="text-xs font-semibold text-primary dark:text-primary-soft">Filtered by:</span>
          {appliedFilterLabels.map((label) => (
            <span
              key={label}
              className="rounded-full bg-card px-2.5 py-0.5 text-[11px] font-medium text-ink dark:bg-card-dark dark:text-ink-dark"
            >
              {label}
            </span>
          ))}
        </div>
      )}

      <div className="px-5 py-5">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-muted dark:text-muted-dark">
            Answer
          </h3>
          {!result.is_not_found && !result.is_service_unavailable && (
            <button
              type="button"
              onClick={copyAnswer}
              className="flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs font-medium text-muted transition hover:bg-surface hover:text-primary dark:text-muted-dark dark:hover:bg-white/5 dark:hover:text-primary-soft"
            >
              {copied ? (
                <Check className="h-3.5 w-3.5 text-success dark:text-success-dark" />
              ) : (
                <Copy className="h-3.5 w-3.5" />
              )}
              <span>{copied ? 'Copied' : 'Copy'}</span>
            </button>
          )}
        </div>

        {result.is_service_unavailable ? (
          <div className="flex items-start gap-3 rounded-xl border border-dashed border-danger/30 bg-danger/5 p-4 dark:border-danger-dark/30 dark:bg-danger/10">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-danger/10 text-danger dark:text-danger-dark">
              <ServerCrash className="h-4 w-4" />
            </div>
            <div>
              <p className="text-sm font-medium text-ink dark:text-ink-dark">AI service temporarily unavailable</p>
              <p className="mt-0.5 text-xs text-muted dark:text-muted-dark">
                Every configured AI provider failed to respond. This is usually temporary — please try again in a moment.
              </p>
            </div>
          </div>
        ) : result.is_not_found ? (
          <div className="flex items-start gap-3 rounded-xl border border-dashed border-line bg-surface p-4 dark:border-line-dark dark:bg-white/5">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-warning/10 text-warning">
              <SearchX className="h-4 w-4" />
            </div>
            <div>
              <p className="text-sm font-medium text-ink dark:text-ink-dark">No answer found in your documents</p>
              <p className="mt-0.5 text-xs text-muted dark:text-muted-dark">
                Try rephrasing, widening the search scope, or uploading a document that covers this topic.
              </p>
            </div>
          </div>
        ) : (
          <div
            className="text-sm leading-relaxed text-ink dark:text-ink-dark [&>*+*]:mt-3 [&_strong]:font-semibold [&_em]:italic [&_h1]:text-base [&_h1]:font-bold [&_h2]:text-sm [&_h2]:font-bold [&_h3]:text-sm [&_h3]:font-semibold [&_ul]:list-disc [&_ul]:space-y-1 [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:space-y-1 [&_ol]:pl-5 [&_code]:rounded [&_code]:bg-surface [&_code]:px-1 [&_code]:py-0.5 [&_code]:font-mono [&_code]:text-xs dark:[&_code]:bg-white/10 [&_pre]:overflow-x-auto [&_pre]:rounded-lg [&_pre]:bg-surface [&_pre]:p-3 [&_pre]:text-xs dark:[&_pre]:bg-white/5 [&_pre_code]:bg-transparent [&_pre_code]:p-0 [&_a]:text-primary [&_a]:underline dark:[&_a]:text-primary-soft"
            dangerouslySetInnerHTML={{ __html: result.answer_html }}
          />
        )}
      </div>

      {result.related_topics?.length > 0 && (
        <div className="border-t border-line px-5 py-4 dark:border-line-dark">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted dark:text-muted-dark">
            Related topics
          </h3>
          <div className="flex flex-wrap gap-1.5">
            {result.related_topics.map((topic) => (
              <span
                key={topic.id}
                className="rounded-full border border-line bg-surface px-2.5 py-1 text-xs text-muted dark:border-line-dark dark:bg-white/5 dark:text-muted-dark"
              >
                {topic.name}
              </span>
            ))}
          </div>
        </div>
      )}

      {result.sources?.length > 0 && (
        <div className="border-t border-line px-5 py-5 dark:border-line-dark">
          <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted dark:text-muted-dark">
            Sources
          </h3>
          <div className="space-y-3">
            {result.sources.map((source, i) => {
              const n = i + 1;
              return (
                <div
                  key={n}
                  className="rounded-xl border border-line bg-surface/80 p-3.5 transition hover:border-primary/25 dark:border-line-dark dark:bg-white/[0.04] dark:hover:border-primary-soft/30"
                >
                  <div className="mb-1.5 flex items-center justify-between gap-2">
                    <span className="flex min-w-0 items-center gap-1.5 truncate text-sm font-medium text-ink dark:text-ink-dark">
                      <FileText className="h-3.5 w-3.5 shrink-0 text-primary dark:text-primary-soft" />
                      <span className="truncate">{source.document}</span>
                      <span className="shrink-0 text-muted dark:text-muted-dark">· chunk {source.chunk_number}</span>
                    </span>
                    <span className="flex shrink-0 items-center gap-1.5">
                      {source.citation_number && (
                        <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-semibold text-primary dark:bg-primary-soft/10 dark:text-primary-soft">
                          Cited [{source.citation_number}]
                        </span>
                      )}
                      <span className="rounded-full border border-line px-2 py-0.5 text-[11px] font-medium capitalize text-muted dark:border-line-dark dark:text-muted-dark">
                        {source.search_type}
                      </span>
                    </span>
                  </div>
                  <p className={`text-xs leading-relaxed text-muted dark:text-muted-dark ${!expanded[n] ? 'line-clamp-2' : ''}`}>
                    {source.content}
                  </p>
                  <button
                    type="button"
                    onClick={() => setExpanded((s) => ({ ...s, [n]: !s[n] }))}
                    className="mt-1.5 text-[11px] font-semibold text-primary hover:underline dark:text-primary-soft"
                  >
                    {expanded[n] ? 'Show less' : 'Show more'}
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
