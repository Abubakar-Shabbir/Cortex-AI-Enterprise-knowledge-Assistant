import { Check, FileText, Sparkles, X } from 'lucide-react';
import { renderCitedText } from '../../lib/renderCitedText';

const SEVERITY_CLASSES = {
  high: 'bg-danger/10 text-danger dark:text-danger-dark',
  medium: 'bg-warning/10 text-warning dark:text-warning-dark',
};

function Cited({ text, className }) {
  // eslint-disable-next-line react/no-danger
  return <div className={className} dangerouslySetInnerHTML={{ __html: renderCitedText(text) }} />;
}

// Port of templates/ai_tasks/_result_row.html - shared across all 8
// task types, branching on which `result.data` keys are present (the
// same small, closed set ai_tasks_engine_service.py controls) rather
// than on task_type.
export default function ResultRow({ result, isCorpus }) {
  const { data } = result;

  return (
    <div className={`rounded-xl border p-5 shadow-soft ${isCorpus ? 'border-primary/30 bg-primary/5 dark:border-primary/40 dark:bg-primary/10' : 'border-line bg-card dark:border-line-dark dark:bg-card-dark'}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-2.5">
          {isCorpus ? (
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary text-white"><Sparkles className="h-4 w-4" /></div>
          ) : (
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary-soft/50 text-primary dark:bg-primary/15 dark:text-primary-soft"><FileText className="h-4 w-4" /></div>
          )}
          <div>
            <h3 className="text-sm font-semibold text-ink dark:text-ink-dark">{result.title}</h3>
            {result.rank && <p className="text-xs text-muted dark:text-muted-dark">Rank #{result.rank}</p>}
          </div>
        </div>
        {result.score !== null && result.score !== undefined && (
          <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ${result.score >= 70 ? 'bg-success/10 text-success dark:text-success-dark' : result.score >= 40 ? 'bg-warning/10 text-warning dark:text-warning-dark' : 'bg-danger/10 text-danger dark:text-danger-dark'}`}>
            {Math.round(result.score)}%
          </span>
        )}
      </div>

      {data.error ? (
        <p className="mt-3 text-sm text-danger dark:text-danger-dark">{result.summary}</p>
      ) : (
        <>
          {result.summary && (
            <Cited text={result.summary} className="mt-3 text-sm text-ink dark:text-ink-dark [&>*+*]:mt-2 [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:pl-5 [&_strong]:font-semibold" />
          )}

          {data.cluster_label && !isCorpus && (
            <p className="mt-2 text-xs text-muted dark:text-muted-dark">Group: <span className="font-medium text-ink dark:text-ink-dark">{data.cluster_label}</span></p>
          )}

          {data.findings?.length > 0 && (
            <div className="mt-3">
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted dark:text-muted-dark">Findings</p>
              <ul className="space-y-1 text-sm text-ink dark:text-ink-dark">
                {data.findings.map((finding, idx) => (
                  <li key={idx} className="flex items-start gap-1.5"><Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-success dark:text-success-dark" /> {finding.point}</li>
                ))}
              </ul>
            </div>
          )}

          {data.missing_requirements?.length > 0 && (
            <div className="mt-3">
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted dark:text-muted-dark">Missing Requirements</p>
              <ul className="space-y-1 text-sm text-ink dark:text-ink-dark">
                {data.missing_requirements.map((item, idx) => (
                  <li key={idx} className="flex items-start gap-1.5"><X className="mt-0.5 h-3.5 w-3.5 shrink-0 text-danger dark:text-danger-dark" /> {item}</li>
                ))}
              </ul>
            </div>
          )}

          {data.common_gaps?.length > 0 && (
            <div className="mt-3">
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted dark:text-muted-dark">Common Gaps</p>
              <ul className="space-y-1 text-sm text-ink dark:text-ink-dark">
                {data.common_gaps.map((item, idx) => <li key={idx}>• {item}</li>)}
              </ul>
            </div>
          )}

          {data.violations?.length > 0 && (
            <div className="mt-3">
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted dark:text-muted-dark">Violations</p>
              <ul className="space-y-1 text-sm text-ink dark:text-ink-dark">
                {data.violations.map((v, idx) => (
                  <li key={idx} className="flex items-start gap-1.5">
                    <span className={`mt-0.5 rounded-full px-1.5 py-0.5 text-[10px] font-semibold uppercase ${SEVERITY_CLASSES[v.severity] || 'bg-line text-muted dark:bg-white/10 dark:text-muted-dark'}`}>{v.severity || '—'}</span>
                    {v.issue}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {data.compliant_points?.length > 0 && (
            <div className="mt-3">
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted dark:text-muted-dark">Compliant Points</p>
              <ul className="space-y-1 text-sm text-ink dark:text-ink-dark">
                {data.compliant_points.map((p, idx) => (
                  <li key={idx} className="flex items-start gap-1.5"><Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-success dark:text-success-dark" /> {p.point}</li>
                ))}
              </ul>
            </div>
          )}

          {data.key_points?.length > 0 && (
            <div className="mt-3">
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted dark:text-muted-dark">Key Points</p>
              <ul className="space-y-1 text-sm text-ink dark:text-ink-dark">
                {data.key_points.map((point, idx) => (
                  <li key={idx} className="flex items-start gap-1.5"><Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-success dark:text-success-dark" /> {point}</li>
                ))}
              </ul>
            </div>
          )}

          {(data.topics?.length > 0 || data.common_topics?.length > 0) && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {(data.topics || []).map((topic, idx) => <span key={`t-${idx}`} className="rounded-full bg-line px-2.5 py-0.5 text-xs text-muted dark:bg-white/10 dark:text-muted-dark">{topic}</span>)}
              {(data.common_topics || []).map((topic, idx) => <span key={`ct-${idx}`} className="rounded-full bg-line px-2.5 py-0.5 text-xs text-muted dark:bg-white/10 dark:text-muted-dark">{topic}</span>)}
            </div>
          )}

          {data.fields && Object.keys(data.fields).length > 0 && (
            <div className="mt-3 overflow-hidden rounded-lg border border-line dark:border-line-dark">
              <table className="w-full text-left text-xs">
                <tbody className="divide-y divide-line dark:divide-line-dark">
                  {Object.entries(data.fields).map(([name, field]) => (
                    <tr key={name}>
                      <td className="px-3 py-2 font-medium text-muted dark:text-muted-dark">{name}</td>
                      <td className="px-3 py-2 text-ink dark:text-ink-dark">{field.value ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {data.table && data.table.headers && data.table.rows && (
            <div className="mt-3 overflow-x-auto rounded-lg border border-line dark:border-line-dark">
              <table className="w-full min-w-[420px] text-left text-xs">
                <thead className="bg-surface dark:bg-white/5">
                  <tr>{data.table.headers.map((h, idx) => <th key={idx} className="px-3 py-2 font-semibold text-muted dark:text-muted-dark">{h}</th>)}</tr>
                </thead>
                <tbody className="divide-y divide-line dark:divide-line-dark">
                  {data.table.rows.map((row, ridx) => (
                    <tr key={ridx}>{row.map((cell, cidx) => <td key={cidx} className="px-3 py-2 text-ink dark:text-ink-dark">{cell}</td>)}</tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {data.table && typeof data.table === 'object' && !data.table.headers && Object.keys(data.table).length > 0 && (
            <div className="mt-3 overflow-x-auto rounded-lg border border-line dark:border-line-dark">
              <table className="w-full min-w-[480px] text-left text-xs">
                <thead className="bg-surface dark:bg-white/5">
                  <tr>
                    <th className="px-3 py-2 font-semibold text-muted dark:text-muted-dark">Document</th>
                    <th className="px-3 py-2 font-semibold text-muted dark:text-muted-dark">Extracted Fields</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line dark:divide-line-dark">
                  {Object.entries(data.table).map(([docTitle, fields]) => (
                    <tr key={docTitle}>
                      <td className="px-3 py-2 font-medium text-ink dark:text-ink-dark">{docTitle}</td>
                      <td className="px-3 py-2 text-muted dark:text-muted-dark">
                        {Object.entries(fields).map(([name, field], idx, arr) => (
                          <span key={name}>{name}: {field.value ?? '—'}{idx < arr.length - 1 ? ', ' : ''}</span>
                        ))}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {data.dimensions?.length > 0 && (
            <div className="mt-3 space-y-2">
              {data.dimensions.map((dim, idx) => (
                <div key={idx} className="rounded-lg border border-line p-2.5 text-sm dark:border-line-dark">
                  <p className="font-medium text-ink dark:text-ink-dark">{dim.dimension}</p>
                  <Cited text={dim.finding} className="mt-0.5 text-xs text-muted dark:text-muted-dark [&_ul]:list-disc [&_ul]:pl-4 [&_strong]:font-semibold" />
                </div>
              ))}
            </div>
          )}

          {data.relevant_points?.length > 0 && (
            <div className="mt-3">
              <ul className="space-y-1 text-sm text-ink dark:text-ink-dark">
                {data.relevant_points.map((point, idx) => <li key={idx}>• {point.point}</li>)}
              </ul>
            </div>
          )}

          {data.sections?.length > 0 && (
            <div className="mt-3 space-y-3">
              {data.sections.map((section, idx) => (
                <div key={idx}>
                  <p className="text-sm font-semibold text-ink dark:text-ink-dark">{section.heading}</p>
                  <Cited text={section.body} className="mt-1 text-sm text-muted dark:text-muted-dark [&>*+*]:mt-2 [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:pl-5 [&_strong]:font-semibold" />
                </div>
              ))}
            </div>
          )}

          {isCorpus && data.member_count && (
            <p className="mt-3 text-xs text-muted dark:text-muted-dark">{data.member_count} document{data.member_count === 1 ? '' : 's'} in this group.</p>
          )}

          {data.average_score !== null && data.average_score !== undefined && (
            <p className="mt-2 text-xs text-muted dark:text-muted-dark">{data.validated_count} document(s) validated · average compliance {data.average_score}%.</p>
          )}

          {result.citations?.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5 border-t border-line pt-3 dark:border-line-dark">
              <span className="text-[11px] font-medium text-muted dark:text-muted-dark">Sources:</span>
              {result.citations.map((citation, idx) => (
                <span key={idx} title={citation.document} className="rounded-full border border-line px-2 py-0.5 text-[11px] text-muted dark:border-line-dark dark:text-muted-dark">
                  [{citation.number}] {citation.document?.length > 24 ? `${citation.document.slice(0, 24)}…` : citation.document}
                </span>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
