import { useEffect, useState } from 'react';
import { Upload, X } from 'lucide-react';
import { getApiBaseUrl } from '../api/client';
import { fetchDocumentVersions, useUploadDocumentVersion } from '../api/hooks';
import Spinner from './Spinner';

// Port of documents.html's Version History modal (openVersions Alpine method + upload form).
export default function VersionsModal({ doc, onClose }) {
  const [loading, setLoading] = useState(true);
  const [current, setCurrent] = useState(1);
  const [versions, setVersions] = useState([]);
  const [error, setError] = useState('');
  const uploadVersion = useUploadDocumentVersion();

  const load = () => {
    setLoading(true);
    fetchDocumentVersions(doc.id)
      .then((data) => {
        setCurrent(data.current_version);
        setVersions(data.versions || []);
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [doc.id]);

  const onSubmit = async (e) => {
    e.preventDefault();
    setError('');
    const form = e.target;
    const file = form.file.files?.[0];
    if (!file) return;
    try {
      const formData = new FormData();
      formData.append('file', file);
      await uploadVersion.mutateAsync({ docId: doc.id, formData });
      form.reset();
      load();
    } catch (err) {
      setError(err.data?.error || err.message);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="w-full max-w-md rounded-2xl border border-line bg-card p-6 shadow-2xl dark:border-line-dark dark:bg-card-dark">
        <div className="mb-4 flex items-start justify-between gap-3">
          <h3 className="text-sm font-semibold text-ink dark:text-ink-dark">Version history — "{doc.title}"</h3>
          <button type="button" onClick={onClose} className="flex h-8 w-8 items-center justify-center rounded-lg text-muted hover:bg-surface dark:text-muted-dark dark:hover:bg-white/5">
            <X className="h-4 w-4" />
          </button>
        </div>

        <form onSubmit={onSubmit} className="mb-4 flex flex-col gap-2">
          <label className="text-xs font-medium text-muted dark:text-muted-dark">Upload a new version</label>
          <input
            type="file" name="file" accept=".pdf,.docx,.txt" required
            className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-xs text-ink file:mr-3 file:rounded-md file:border-0 file:bg-primary file:px-2.5 file:py-1 file:text-xs file:font-semibold file:text-white dark:border-line-dark dark:bg-white/5 dark:text-ink-dark"
          />
          {error && <p className="text-xs text-danger dark:text-danger-dark">{error}</p>}
          <button type="submit" disabled={uploadVersion.isPending} className="inline-flex items-center justify-center gap-2 rounded-lg bg-primary px-3.5 py-2 text-sm font-semibold text-white hover:bg-primary-dark disabled:opacity-60">
            {uploadVersion.isPending ? <Spinner size={16} /> : <Upload className="h-4 w-4" />} {uploadVersion.isPending ? 'Uploading…' : 'Upload New Version'}
          </button>
          <p className="text-xs text-muted dark:text-muted-dark">Replaces the current version and re-processes it; the old version stays listed below.</p>
        </form>

        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted dark:text-muted-dark">History</p>
        {loading ? (
          <p className="flex items-center gap-2 text-sm text-muted dark:text-muted-dark"><Spinner size={14} /> Loading…</p>
        ) : (
          <div className="space-y-1.5">
            <div className="flex items-center justify-between rounded-lg border border-primary/30 bg-primary/5 px-3 py-2 text-sm dark:border-primary/40 dark:bg-primary/10">
              <span className="font-medium text-ink dark:text-ink-dark">Version {current} (current)</span>
            </div>
            {versions.map((v) => (
              <div key={v.id} className="flex items-center justify-between rounded-lg border border-line px-3 py-2 text-sm dark:border-line-dark">
                <span className="text-ink dark:text-ink-dark">Version {v.version_number} · {v.file_size} · {v.replaced_at}</span>
                <a href={`${getApiBaseUrl()}/api/documents/versions/${v.id}/download/`} className="text-xs font-medium text-primary hover:underline dark:text-primary-soft">Download</a>
              </div>
            ))}
            {versions.length === 0 && <p className="text-xs text-muted dark:text-muted-dark">No earlier versions yet.</p>}
          </div>
        )}
      </div>
    </div>
  );
}
