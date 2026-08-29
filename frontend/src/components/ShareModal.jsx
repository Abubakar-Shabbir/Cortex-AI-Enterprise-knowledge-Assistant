import { useEffect, useState } from 'react';
import { UserPlus, X } from 'lucide-react';
import { createDocumentShare, fetchDocumentShares, revokeDocumentShare } from '../api/hooks';
import { SkeletonRows } from './PageSkeleton';

// Port of documents.html's Share modal (openShare/addShare/revokeShare Alpine methods).
export default function ShareModal({ doc, roles, onClose }) {
  const [shares, setShares] = useState([]);
  const [loading, setLoading] = useState(true);
  const [targetType, setTargetType] = useState('user');
  const [targetValue, setTargetValue] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const load = () => fetchDocumentShares(doc.id).then((data) => setShares(data.shares || [])).finally(() => setLoading(false));

  useEffect(() => { load(); }, [doc.id]);

  const onSubmit = async (e) => {
    e.preventDefault();
    if (!targetValue) return;
    setSubmitting(true);
    setError('');
    try {
      const payload = targetType === 'role' ? { target_type: 'role', target_id: targetValue } : { target_type: 'user', target_username: targetValue };
      const data = await createDocumentShare(doc.id, payload);
      setTargetValue('');
      setShares(data.shares || shares);
    } catch (err) {
      setError(err.data?.error || err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const onRevoke = async (shareId) => {
    await revokeDocumentShare(shareId);
    setShares((prev) => prev.filter((s) => s.id !== shareId));
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="w-full max-w-md rounded-2xl border border-line bg-card p-6 shadow-2xl dark:border-line-dark dark:bg-card-dark">
        <div className="mb-4 flex items-start justify-between gap-3">
          <h3 className="text-sm font-semibold text-ink dark:text-ink-dark">Share "{doc.title}"</h3>
          <button type="button" onClick={onClose} className="flex h-8 w-8 items-center justify-center rounded-lg text-muted hover:bg-surface dark:text-muted-dark dark:hover:bg-white/5">
            <X className="h-4 w-4" />
          </button>
        </div>

        <form onSubmit={onSubmit} className="mb-4 flex flex-col gap-2">
          <div className="flex gap-2">
            <select value={targetType} onChange={(e) => { setTargetType(e.target.value); setTargetValue(''); }} className="rounded-lg border border-line bg-transparent px-2.5 py-2 text-sm text-ink focus:border-primary focus:outline-none dark:border-line-dark dark:text-ink-dark">
              <option value="user">User</option>
              <option value="role">Role</option>
            </select>
            {targetType === 'user' ? (
              <input type="text" value={targetValue} onChange={(e) => setTargetValue(e.target.value)} placeholder="Username or email" className="flex-1 rounded-lg border border-line bg-transparent px-3 py-2 text-sm text-ink placeholder:text-muted focus:border-primary focus:outline-none dark:border-line-dark dark:text-ink-dark" />
            ) : (
              <select value={targetValue} onChange={(e) => setTargetValue(e.target.value)} className="flex-1 rounded-lg border border-line bg-transparent px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none dark:border-line-dark dark:text-ink-dark">
                <option value="">Select a role…</option>
                {roles.map((role) => <option key={role.id} value={role.id}>{role.name}</option>)}
              </select>
            )}
          </div>
          {error && <p className="text-xs text-danger dark:text-danger-dark">{error}</p>}
          <button type="submit" disabled={submitting} className="inline-flex items-center justify-center gap-2 rounded-lg bg-primary px-3.5 py-2 text-sm font-semibold text-white hover:bg-primary-dark disabled:opacity-60">
            <UserPlus className="h-4 w-4" /> Share
          </button>
        </form>

        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted dark:text-muted-dark">Shared with</p>
        {loading ? (
          <SkeletonRows rows={3} />
        ) : (
          <div className="space-y-1.5">
            {shares.map((s) => (
              <div key={s.id} className="flex items-center justify-between rounded-lg border border-line px-3 py-2 text-sm dark:border-line-dark">
                <span className="text-ink dark:text-ink-dark">{s.target}</span>
                <button type="button" onClick={() => onRevoke(s.id)} className="text-xs font-medium text-danger hover:underline dark:text-danger-dark">Revoke</button>
              </div>
            ))}
            {shares.length === 0 && <p className="text-xs text-muted dark:text-muted-dark">Not shared with anyone yet.</p>}
          </div>
        )}
      </div>
    </div>
  );
}
