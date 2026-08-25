import { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  Archive, CheckCircle2, ChevronDown, Download, ExternalLink, FileText, Filter, HardDrive, Star,
  Trash2, UploadCloud, X, Zap,
} from 'lucide-react';
import {
  useDeleteDocument, useDocuments, useDocumentsMeta, useEmbedDocument, useToggleArchive, useToggleFavorite,
  useUploadDocument, fetchDocumentPreview, fetchDocumentStatus,
} from '../api/hooks';
import { getApiBaseUrl } from '../api/client';
import PageHeader from '../components/PageHeader';
import StatCard from '../components/StatCard';

const STATUS_OPTIONS = [
  ['', 'Any'], ['pending', 'Pending'], ['processing', 'Processing'], ['completed', 'Ready'], ['failed', 'Failed'],
];
const TYPE_OPTIONS = [['', 'Any'], ['pdf', 'PDF'], ['docx', 'DOCX'], ['txt', 'TXT']];
const SORT_OPTIONS = [
  ['newest', 'Newest first'], ['oldest', 'Oldest first'], ['title', 'Title A–Z'],
  ['size_desc', 'Largest first'], ['size_asc', 'Smallest first'],
];

export default function Documents() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploadError, setUploadError] = useState('');
  const [preview, setPreview] = useState(null);

  const filters = {
    q: searchParams.get('q') || '',
    status: searchParams.get('status') || '',
    file_type: searchParams.get('file_type') || '',
    category: searchParams.get('category') || '',
    tag: searchParams.get('tag') || '',
    sort: searchParams.get('sort') || 'newest',
    archived: searchParams.get('archived') || '',
    page: searchParams.get('page') || '1',
  };

  const { data, isLoading } = useDocuments(filters);
  const { data: meta } = useDocumentsMeta();
  const uploadMutation = useUploadDocument();
  const deleteMutation = useDeleteDocument();
  const embedMutation = useEmbedDocument();
  const favoriteMutation = useToggleFavorite();
  const archiveMutation = useToggleArchive();

  const updateFilter = (key, value) => {
    const next = new URLSearchParams(searchParams);
    if (value) next.set(key, value);
    else next.delete(key);
    next.delete('page');
    setSearchParams(next);
  };

  const onFilterSubmit = (e) => {
    e.preventDefault();
    const form = new FormData(e.target);
    const next = new URLSearchParams();
    for (const [key, value] of form.entries()) {
      if (value) next.set(key, value);
    }
    setSearchParams(next);
  };

  const onUpload = (e) => {
    e.preventDefault();
    setUploadError('');
    const form = e.target;
    uploadMutation.mutate(new FormData(form), {
      onSuccess: () => {
        form.reset();
        setUploadOpen(false);
      },
      onError: (err) => setUploadError(err.message),
    });
  };

  const stats = data?.stats;

  return (
    <div>
      <PageHeader title="Documents" subtitle="Upload once, reuse everywhere — the single source of truth for what your assistant can answer from." />

      <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
        <StatCard icon={FileText} label="Total Documents" value={stats?.total_documents ?? 0} numeric />
        <StatCard icon={CheckCircle2} label="Fully Ready" value={stats?.embedded_count ?? 0} numeric />
        <StatCard icon={HardDrive} label="Storage Used" value={stats?.total_storage ?? '0 B'} />
        <StatCard icon={Archive} label="Archived" value={stats?.archived_count ?? 0} numeric />
        <StatCard icon={Star} label="Favorites" value={stats?.favorites_count ?? 0} numeric />
      </div>

      <div className="mb-6 rounded-xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">
        <button onClick={() => setUploadOpen((v) => !v)} className="flex w-full items-center justify-between px-5 py-4">
          <span className="flex items-center gap-2.5 text-sm font-semibold text-ink dark:text-ink-dark">
            <UploadCloud className="h-4 w-4 text-primary dark:text-primary-soft" /> Upload Document
          </span>
          <ChevronDown className={`h-4 w-4 text-muted transition-transform dark:text-muted-dark ${uploadOpen ? 'rotate-180' : ''}`} />
        </button>

        {uploadOpen && (
          <div className="border-t border-line px-5 py-5 dark:border-line-dark">
            {uploadError && (
              <div className="mb-4 flex items-start gap-2.5 rounded-lg border border-danger/20 bg-danger/10 px-3.5 py-3 text-sm text-danger dark:text-danger-dark">
                {uploadError}
              </div>
            )}
            <form onSubmit={onUpload} className="flex flex-col gap-4">
              <div>
                <label className="mb-1.5 block text-xs font-medium text-muted dark:text-muted-dark">File (PDF, DOCX, TXT — max 20 MB)</label>
                <input
                  type="file" name="document" accept=".pdf,.docx,.txt" required
                  className="w-full rounded-lg border border-line bg-surface px-3.5 py-2 text-sm text-ink file:mr-3 file:rounded-md file:border-0 file:bg-primary file:px-3 file:py-1.5 file:text-xs file:font-semibold file:text-white dark:border-line-dark dark:bg-white/5 dark:text-ink-dark"
                />
                <p className="mt-1.5 text-xs text-muted dark:text-muted-dark">The document's title is taken from the file name — upload just saves the file; click <strong>Embed</strong> on its row below when you're ready to process it.</p>
              </div>

              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div>
                  <label className="mb-1.5 block text-xs font-medium text-muted dark:text-muted-dark">Add to Collection (optional)</label>
                  <select name="collection_id" className="w-full rounded-lg border border-line bg-surface px-3.5 py-2 text-sm text-ink focus:border-primary focus:outline-none dark:border-line-dark dark:bg-white/5 dark:text-ink-dark">
                    <option value="">No collection</option>
                    {meta?.collections.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                  </select>
                </div>

                {meta?.can_manage_org_library && (
                  <div className="flex items-start gap-2.5 rounded-lg border border-line bg-surface px-3.5 py-3 dark:border-line-dark dark:bg-white/5">
                    <input type="checkbox" name="add_to_org_library" id="upload-org-library" value="1" className="mt-0.5 h-4 w-4 shrink-0 rounded border-line text-primary focus:ring-primary dark:border-line-dark" />
                    <label htmlFor="upload-org-library" className="text-sm text-ink dark:text-ink-dark">
                      Add to Organization Library
                      <span className="mt-0.5 block text-xs font-normal text-muted dark:text-muted-dark">Makes this document visible to everyone in your organization, not just you.</span>
                    </label>
                  </div>
                )}
              </div>

              <div>
                <button type="submit" disabled={uploadMutation.isPending} className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-primary-dark disabled:opacity-60">
                  <UploadCloud className="h-4 w-4" /> {uploadMutation.isPending ? 'Uploading…' : 'Upload'}
                </button>
              </div>
            </form>
          </div>
        )}
      </div>

      <div className="mb-4 rounded-xl border border-line bg-card p-4 shadow-soft dark:border-line-dark dark:bg-card-dark">
        <form key={searchParams.toString()} onSubmit={onFilterSubmit} className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-6">
          <div className="lg:col-span-2">
            <label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">Search</label>
            <input type="text" name="q" defaultValue={filters.q} placeholder="Title…" className="w-full rounded-lg border border-line bg-transparent px-3 py-2 text-sm text-ink placeholder:text-muted focus:border-primary focus:outline-none dark:border-line-dark dark:text-ink-dark" />
          </div>
          <Select name="status" label="Status" defaultValue={filters.status} options={STATUS_OPTIONS} />
          <Select name="file_type" label="Type" defaultValue={filters.file_type} options={TYPE_OPTIONS} />
          <Select name="category" label="Category" defaultValue={filters.category} options={[['', 'Any'], ...(meta?.categories.map((c) => [String(c.id), c.name]) || [])]} />
          <Select name="tag" label="Tag" defaultValue={filters.tag} options={[['', 'Any'], ...(meta?.tags.map((t) => [String(t.id), t.name]) || [])]} />
          <Select name="sort" label="Sort" defaultValue={filters.sort} options={SORT_OPTIONS} />

          <label className="flex items-center gap-2 self-end pb-2 text-sm text-ink dark:text-ink-dark">
            <input type="checkbox" name="archived" value="1" defaultChecked={filters.archived === '1'} className="h-4 w-4 rounded border-line text-primary focus:ring-primary dark:border-line-dark" />
            Archived only
          </label>

          <div className="flex items-end gap-2 lg:col-span-2">
            <button type="submit" className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-primary-dark">
              <Filter className="h-4 w-4" /> Apply
            </button>
            <button type="button" onClick={() => setSearchParams({})} className="inline-flex items-center gap-2 rounded-lg border border-line px-4 py-2 text-sm font-medium text-ink transition-colors hover:bg-surface dark:border-line-dark dark:text-ink-dark dark:hover:bg-white/5">
              Reset
            </button>
          </div>
        </form>
      </div>

      <div className="overflow-hidden rounded-xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="sticky top-0 border-b border-line bg-surface dark:border-line-dark dark:bg-white/5">
              <tr className="text-xs font-semibold uppercase tracking-wide text-muted dark:text-muted-dark">
                <th className="px-5 py-3.5">Document</th>
                <th className="px-5 py-3.5">Type</th>
                <th className="px-5 py-3.5">Uploaded</th>
                <th className="px-5 py-3.5">Chunks</th>
                <th className="px-5 py-3.5">Status</th>
                <th className="px-5 py-3.5">Size</th>
                <th className="px-5 py-3.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line dark:divide-line-dark">
              {isLoading ? (
                <tr><td colSpan={7} className="px-5 py-14 text-center text-sm text-muted dark:text-muted-dark">Loading…</td></tr>
              ) : data.results.length ? (
                data.results.map((doc) => (
                  <DocumentRow
                    key={doc.id} doc={doc}
                    onEmbed={() => embedMutation.mutate(doc.id)}
                    onDelete={() => deleteMutation.mutate(doc.id)}
                    onToggleFavorite={() => favoriteMutation.mutate(doc.id)}
                    onToggleArchive={() => archiveMutation.mutate(doc.id)}
                    onPreview={() => setPreview({ id: doc.id, title: doc.title })}
                  />
                ))
              ) : (
                <tr><td colSpan={7} className="px-5 py-14 text-center text-sm text-muted dark:text-muted-dark">{filters.q ? `No documents match "${filters.q}".` : 'No documents uploaded yet.'}</td></tr>
              )}
            </tbody>
          </table>
        </div>

        {data && data.num_pages > 1 && (
          <div className="flex items-center justify-between border-t border-line px-5 py-3 dark:border-line-dark">
            <p className="text-xs text-muted dark:text-muted-dark">Page {data.page} of {data.num_pages} · {data.count} total</p>
            <div className="flex gap-2">
              {data.page > 1 && (
                <button onClick={() => updateFilter('page', String(data.page - 1))} className="rounded-lg border border-line px-3 py-1.5 text-xs font-medium text-ink hover:bg-surface dark:border-line-dark dark:text-ink-dark dark:hover:bg-white/5">Previous</button>
              )}
              {data.page < data.num_pages && (
                <button onClick={() => updateFilter('page', String(data.page + 1))} className="rounded-lg border border-line px-3 py-1.5 text-xs font-medium text-ink hover:bg-surface dark:border-line-dark dark:text-ink-dark dark:hover:bg-white/5">Next</button>
              )}
            </div>
          </div>
        )}
      </div>

      {preview && <PreviewModal doc={preview} onClose={() => setPreview(null)} />}
    </div>
  );
}

function Select({ name, label, defaultValue, options }) {
  return (
    <div>
      <label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">{label}</label>
      <select name={name} defaultValue={defaultValue} className="w-full rounded-lg border border-line bg-transparent px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none dark:border-line-dark dark:text-ink-dark">
        {options.map(([value, text]) => <option key={value} value={value}>{text}</option>)}
      </select>
    </div>
  );
}

function DocumentRow({ doc, onEmbed, onDelete, onToggleFavorite, onToggleArchive, onPreview }) {
  const [status, setStatus] = useState(doc.status);
  const [percent, setPercent] = useState(doc.percent);
  const [chunkCount, setChunkCount] = useState(doc.chunk_count);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const pollRef = useRef(null);

  useEffect(() => {
    setStatus(doc.status);
    setPercent(doc.percent);
    setChunkCount(doc.chunk_count);
  }, [doc.status, doc.percent, doc.chunk_count]);

  useEffect(() => {
    if (status !== 'Processing') return undefined;

    pollRef.current = setInterval(async () => {
      try {
        const data = await fetchDocumentStatus(doc.id);
        setPercent(data.percent);
        setChunkCount(data.chunk_count);
        if (data.status === 'processing') return;

        clearInterval(pollRef.current);
        if (data.status === 'failed') setStatus('Failed');
        else if (data.status === 'completed') setStatus(data.percent >= 100 ? 'Ready' : 'Partial');
        else setStatus('Pending');
      } catch {
        clearInterval(pollRef.current);
      }
    }, 2000);

    return () => clearInterval(pollRef.current);
  }, [status, doc.id]);

  const startEmbed = () => {
    setStatus('Processing');
    setPercent(0);
    onEmbed();
  };

  return (
    <tr className="transition-colors hover:bg-surface dark:hover:bg-white/5">
      <td className="px-5 py-3.5">
        <div className="flex items-center gap-2.5">
          <button type="button" onClick={onToggleFavorite} title="Favorite" className="shrink-0">
            <Star className={`h-4 w-4 transition-colors ${doc.is_favorite ? 'fill-warning text-warning' : 'text-muted dark:text-muted-dark'}`} />
          </button>
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary-soft/50 text-primary dark:bg-primary/15 dark:text-primary-soft">
            <FileText className="h-4 w-4" />
          </div>
          <button type="button" onClick={onPreview} className="max-w-[220px] truncate text-left font-medium text-ink hover:text-primary dark:text-ink-dark dark:hover:text-primary-soft">{doc.title}</button>
        </div>
      </td>
      <td className="px-5 py-3.5 text-muted dark:text-muted-dark">{doc.file_type?.toUpperCase()}</td>
      <td className="px-5 py-3.5 text-muted dark:text-muted-dark">{new Date(doc.uploaded_at).toLocaleDateString(undefined, { month: 'short', day: '2-digit', year: 'numeric' })}</td>
      <td className="px-5 py-3.5 text-muted dark:text-muted-dark">{chunkCount}</td>
      <td className="px-5 py-3.5">
        {status === 'Pending' && (
          <button onClick={startEmbed} className="inline-flex items-center gap-1.5 rounded-lg bg-primary/10 px-3 py-1.5 text-xs font-semibold text-primary transition-colors hover:bg-primary/15 dark:text-primary-soft">
            <Zap className="h-3.5 w-3.5" /> Embed
          </button>
        )}
        {status === 'Processing' && (
          <div className="w-32">
            <div className="mb-1 flex items-center justify-between text-[11px] font-medium text-muted dark:text-muted-dark">
              <span>Processing…</span><span>{percent}%</span>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-line dark:bg-white/10">
              <div className="h-full rounded-full bg-primary transition-all duration-500" style={{ width: `${percent}%` }} />
            </div>
          </div>
        )}
        {status === 'Ready' && (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-success/10 px-2.5 py-1 text-xs font-medium text-success dark:text-success-dark">
            <span className="h-1.5 w-1.5 rounded-full bg-success"></span> Ready
          </span>
        )}
        {status === 'Partial' && (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-warning/10 px-2.5 py-1 text-xs font-medium text-warning dark:text-warning-dark">
            <span className="h-1.5 w-1.5 rounded-full bg-warning"></span> Partial
          </span>
        )}
        {status === 'Failed' && (
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-danger/10 px-2.5 py-1 text-xs font-medium text-danger dark:text-danger-dark">
              <span className="h-1.5 w-1.5 rounded-full bg-danger"></span> Failed
            </span>
            <button onClick={startEmbed} className="text-xs font-semibold text-primary hover:underline dark:text-primary-soft">Retry</button>
          </div>
        )}
        {status === 'Archived' && (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-line px-2.5 py-1 text-xs font-medium text-muted dark:bg-white/10 dark:text-muted-dark">
            <Archive className="h-3 w-3" /> Archived
          </span>
        )}
      </td>
      <td className="px-5 py-3.5 text-muted dark:text-muted-dark">{doc.file_size}</td>
      <td className="px-5 py-3.5">
        <div className="flex items-center justify-end gap-1">
          <a href={`${getApiBaseUrl()}/api/documents/${doc.id}/download/`} target="_blank" rel="noreferrer" title="Open" className="rounded-lg p-2 text-muted transition-colors hover:bg-line hover:text-ink dark:text-muted-dark dark:hover:bg-white/10 dark:hover:text-ink-dark">
            <ExternalLink className="h-4 w-4" />
          </a>
          <a href={`${getApiBaseUrl()}/api/documents/${doc.id}/download/?download=1`} title="Download" className="rounded-lg p-2 text-muted transition-colors hover:bg-line hover:text-ink dark:text-muted-dark dark:hover:bg-white/10 dark:hover:text-ink-dark">
            <Download className="h-4 w-4" />
          </a>
          <button type="button" onClick={onToggleArchive} title="Archive / Unarchive" className="rounded-lg p-2 text-muted transition-colors hover:bg-line hover:text-ink dark:text-muted-dark dark:hover:bg-white/10 dark:hover:text-ink-dark">
            <Archive className="h-4 w-4" />
          </button>
          <button onClick={() => setConfirmOpen(true)} title="Delete" className="rounded-lg p-2 text-muted transition-colors hover:bg-danger/10 hover:text-danger dark:text-muted-dark dark:hover:text-danger-dark">
            <Trash2 className="h-4 w-4" />
          </button>

          {confirmOpen && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
              <div className="w-full max-w-sm rounded-xl border border-line bg-card p-5 shadow-soft dark:border-line-dark dark:bg-card-dark">
                <h3 className="mb-1 text-sm font-semibold text-danger dark:text-danger-dark">Delete document</h3>
                <p className="mb-4 text-sm text-muted dark:text-muted-dark">
                  Delete "<span className="font-medium text-ink dark:text-ink-dark">{doc.title}</span>" and all {chunkCount} of its chunks? This can't be undone.
                </p>
                <div className="flex justify-end gap-2">
                  <button onClick={() => setConfirmOpen(false)} className="rounded-lg border border-line px-3.5 py-2 text-sm font-medium text-ink hover:bg-surface dark:border-line-dark dark:text-ink-dark dark:hover:bg-white/5">Cancel</button>
                  <button onClick={onDelete} className="rounded-lg bg-danger px-3.5 py-2 text-sm font-semibold text-white hover:bg-danger/90">Delete</button>
                </div>
              </div>
            </div>
          )}
        </div>
      </td>
    </tr>
  );
}

function PreviewModal({ doc, onClose }) {
  const [state, setState] = useState({ loading: true, text: '', truncated: false, error: '' });

  useEffect(() => {
    fetchDocumentPreview(doc.id)
      .then((data) => setState({ loading: false, text: data.text || '', truncated: !!data.truncated, error: data.error || '' }))
      .catch(() => setState({ loading: false, text: '', truncated: false, error: 'Could not load preview.' }));
  }, [doc.id]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div className="max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-line bg-card p-6 shadow-2xl dark:border-line-dark dark:bg-card-dark" onClick={(e) => e.stopPropagation()}>
        <div className="mb-3 flex items-start justify-between gap-3">
          <h3 className="text-sm font-semibold text-ink dark:text-ink-dark">{doc.title}</h3>
          <button type="button" onClick={onClose} className="flex h-8 w-8 items-center justify-center rounded-lg text-muted hover:bg-surface dark:text-muted-dark dark:hover:bg-white/5">
            <X className="h-4 w-4" />
          </button>
        </div>
        {state.loading && <p className="text-sm text-muted dark:text-muted-dark">Loading preview…</p>}
        {!state.loading && state.error && <p className="text-sm text-muted dark:text-muted-dark">{state.error}</p>}
        {!state.loading && state.text && (
          <div>
            <p className="whitespace-pre-wrap rounded-lg bg-surface p-3 text-sm text-ink dark:bg-white/5 dark:text-ink-dark">{state.text}</p>
            {state.truncated && <p className="mt-2 text-xs text-muted dark:text-muted-dark">Preview truncated — download the document to see the rest.</p>}
          </div>
        )}
      </div>
    </div>
  );
}
