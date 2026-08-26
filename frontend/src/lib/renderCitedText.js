import DOMPurify from 'dompurify';
import { marked } from 'marked';

// Client-side port of RAG.services.citation_service.render_answer_html() -
// Markdown -> sanitized HTML, then every "[n]" citation marker turned
// into a small badge, matching the styling render_answer_html()'s
// _CITATION_MARKER_HTML produces (minus the Ask-AI-specific
// scroll-to-source click handler, which has no equivalent target on
// an AI Task result row).
export function renderCitedText(text) {
  if (!text) return '';
  const safeHtml = DOMPurify.sanitize(marked.parse(text));
  return safeHtml.replace(
    /\[(\d+)\]/g,
    '<span class="mx-0.5 inline-flex h-[18px] min-w-[18px] items-center justify-center rounded bg-primary/15 px-1 align-text-top text-[10px] font-semibold text-primary dark:bg-primary-soft/20 dark:text-primary-soft">$1</span>',
  );
}
