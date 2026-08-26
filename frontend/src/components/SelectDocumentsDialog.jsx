import { useEffect, useRef, useState } from 'react';
import { FileCheck2, Square, SquareCheck, X } from 'lucide-react';
import { api } from '../api/client';
import Spinner from './Spinner';

const FILE_TYPES = ['', 'pdf', 'docx', 'txt'];

// Port of templates/partials/_select_documents_dialog.html - the
// reusable "Select Documents" picker (AI Tasks, and anything else that
// needs to choose from the requester's accessible document set).
// `selected` is {id: {id, title}}; `onChange` receives the next map.
export default function SelectDocumentsDialog({ selected, onChange, triggerLabel = 'Select Documents' }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [fileType, setFileType] = useState('');
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [hasNext, setHasNext] = useState(false);
  const debounceRef = useRef(null);

  const search = async (reset, pageOverride) => {
    setLoading(true);
    const nextPage = reset ? 1 : pageOverride || page;
    if (reset) setPage(1);
    try {
      const params = new URLSearchParams({ q: query, file_type: fileType, page: String(nextPage) });
      const data = await api.get(`/documents/select-dialog/search/?${params.toString()}`);
      setResults((prev) => (reset ? data.results : [...prev, ...data.results]));
      setHasNext(data.has_next);
    } catch {
      // leave results as-is on a transient failure
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!open) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => search(true), 300);
    return () => clearTimeout(debounceRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, fileType, open]);

  const toggle = (doc) => {
    const next = { ...selected };
    if (next[doc.id]) delete next[doc.id];
    else next[doc.id] = { id: doc.id, title: doc.title };
    onChange(next);
  };

  const loadMore = () => {
    const next = page + 1;
    setPage(next);
    search(false, next);
  };

  const count = Object.keys(selected).length;

  return (
    <div className="inline-block">
      {Object.keys(selected).map((id) => (
        <input key={id} type="hidden" name="document_ids" value={id} />
      ))}

      <button
        type="button"
        onClick={() => { setOpen(true); search(true); }}
        className="inline-flex items-center gap-2 rounded-lg border border-line bg-surface px-3.5 py-2 text-sm font-medium text-ink transition-colors hover:border-primary/30 hover:bg-primary/5 hover:text-primary dark:border-line-dark dark:bg-white/5 dark:text-ink-dark dark:hover:bg-primary/10"
      >
        <FileCheck2 className="h-4 w-4" />
        <span>{count ? `${count} document${count === 1 ? '' : 's'} selected` : triggerLabel}</span>
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={(e) => { if (e.target === e.currentTarget) setOpen(false); }}>
          <div className="flex max-h-[80vh] w-full max-w-lg flex-col overflow-hidden rounded-2xl border border-line bg-card shadow-2xl dark:border-line-dark dark:bg-card-dark">
            <div className="flex items-center justify-between gap-3 border-b border-line px-5 py-4 dark:border-line-dark">
              <h3 className="text-sm font-semibold text-ink dark:text-ink-dark">Select Documents</h3>
              <button type="button" onClick={() => setOpen(false)} className="flex h-8 w-8 items-center justify-center rounded-lg text-muted hover:bg-surface dark:text-muted-dark dark:hover:bg-white/5">
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="border-b border-line px-5 py-3 dark:border-line-dark">
              <input
                type="text" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search by title…"
                className="w-full rounded-lg border border-line bg-transparent px-3 py-2 text-sm text-ink placeholder:text-muted focus:border-primary focus:outline-none dark:border-line-dark dark:text-ink-dark"
              />
              <div className="mt-2 flex flex-wrap gap-1.5">
                {FILE_TYPES.map((opt) => (
                  <button
                    key={opt || 'all'} type="button" onClick={() => setFileType(opt)}
                    className={`rounded-full border px-2.5 py-1 text-xs font-medium transition-colors ${fileType === opt ? 'border-primary bg-primary/10 text-primary dark:text-primary-soft' : 'border-line text-muted hover:bg-surface dark:border-line-dark dark:text-muted-dark dark:hover:bg-white/5'}`}
                  >
                    {opt ? opt.toUpperCase() : 'All types'}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex-1 overflow-y-auto px-5 py-3">
              {count > 0 && (
                <div className="mb-3 flex flex-wrap gap-1.5">
                  {Object.values(selected).map((item) => (
                    <span key={item.id} className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary dark:text-primary-soft">
                      <span className="max-w-[160px] truncate">{item.title}</span>
                      <button type="button" onClick={() => toggle(item)}><X className="h-3 w-3" /></button>
                    </span>
                  ))}
                </div>
              )}

              <div className="space-y-1">
                {results.map((doc) => (
                  <button
                    key={doc.id} type="button" onClick={() => toggle(doc)}
                    className={`flex w-full items-center justify-between gap-3 rounded-lg px-3 py-2 text-left text-sm transition-colors hover:bg-surface dark:hover:bg-white/5 ${selected[doc.id] ? 'bg-primary/5' : ''}`}
                  >
                    <span className="flex min-w-0 items-center gap-2">
                      {selected[doc.id] ? <SquareCheck className="h-4 w-4 shrink-0 text-primary dark:text-primary-soft" /> : <Square className="h-4 w-4 shrink-0 text-line dark:text-line-dark" />}
                      <span className="truncate text-ink dark:text-ink-dark">{doc.title}</span>
                    </span>
                    <span className="shrink-0 rounded-full bg-line px-2 py-0.5 text-[10px] font-semibold uppercase text-muted dark:bg-white/10 dark:text-muted-dark">{doc.owner_badge}</span>
                  </button>
                ))}
                {!loading && results.length === 0 && <p className="px-3 py-6 text-center text-sm text-muted dark:text-muted-dark">No documents found.</p>}
                {loading && (
                  <p className="flex items-center justify-center gap-2 px-3 py-6 text-center text-sm text-muted dark:text-muted-dark">
                    <Spinner size={16} /> Loading…
                  </p>
                )}
              </div>

              {hasNext && (
                <button type="button" onClick={loadMore} className="mt-2 w-full rounded-lg border border-line py-1.5 text-xs font-medium text-ink hover:bg-surface dark:border-line-dark dark:text-ink-dark dark:hover:bg-white/5">Load more</button>
              )}
            </div>

            <div className="flex justify-end gap-2 border-t border-line px-5 py-3 dark:border-line-dark">
              <button type="button" onClick={() => onChange({})} className="rounded-lg border border-line px-3.5 py-2 text-sm font-medium text-ink hover:bg-surface dark:border-line-dark dark:text-ink-dark dark:hover:bg-white/5">Clear</button>
              <button type="button" onClick={() => setOpen(false)} className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white hover:bg-primary-dark">Done</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
