import { Download, ExternalLink } from 'lucide-react';
import { getApiBaseUrl } from '../api/client';

const STATUS_CLASSES = {
  Ready: 'bg-success/10 text-success dark:text-success-dark',
  Failed: 'bg-danger/10 text-danger dark:text-danger-dark',
  Archived: 'bg-line text-muted dark:bg-white/10 dark:text-muted-dark',
};

// Shared table shape backing Favorites/SharedWithMe/OrgLibrary - ports
// the near-identical markup those three Django templates repeat
// (Document/Owner/Type/Status/Size/Actions), taking a per-row `icon`
// and an optional `renderExtraActions` for the page-specific action
// (unfavorite / remove-from-library).
export default function SimpleDocumentTable({ documents, badgeIcon: BadgeIcon, leadingIcon: LeadingIcon, renderExtraActions, emptyState, pagination, onPageChange }) {
  const base = getApiBaseUrl();

  if (documents.length === 0) return emptyState;

  return (
    <div className="overflow-hidden rounded-xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="sticky top-0 border-b border-line bg-surface dark:border-line-dark dark:bg-white/5">
            <tr className="text-xs font-semibold uppercase tracking-wide text-muted dark:text-muted-dark">
              <th className="px-5 py-3.5">Document</th>
              <th className="px-5 py-3.5">Owner</th>
              <th className="px-5 py-3.5">Type</th>
              <th className="px-5 py-3.5">Status</th>
              <th className="px-5 py-3.5">Size</th>
              <th className="px-5 py-3.5 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line dark:divide-line-dark">
            {documents.map((doc) => (
              <tr key={doc.id} className="transition-colors hover:bg-surface dark:hover:bg-white/5">
                <td className="px-5 py-3.5">
                  <div className="flex items-center gap-2.5">
                    {LeadingIcon && <LeadingIcon className="h-4 w-4 shrink-0 fill-warning text-warning" />}
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary-soft/50 text-primary dark:bg-primary/15 dark:text-primary-soft">
                      <BadgeIcon className="h-4 w-4" />
                    </div>
                    <span className="max-w-[220px] truncate font-medium text-ink dark:text-ink-dark">{doc.title}</span>
                  </div>
                </td>
                <td className="px-5 py-3.5 text-muted dark:text-muted-dark">{doc.owner}</td>
                <td className="px-5 py-3.5 text-muted dark:text-muted-dark">{doc.file_type?.toUpperCase()}</td>
                <td className="px-5 py-3.5">
                  <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${STATUS_CLASSES[doc.status] || 'bg-warning/10 text-warning dark:text-warning-dark'}`}>
                    {doc.status}
                  </span>
                </td>
                <td className="px-5 py-3.5 text-muted dark:text-muted-dark">{doc.file_size}</td>
                <td className="px-5 py-3.5">
                  <div className="flex items-center justify-end gap-1">
                    <a href={`${base}/api/documents/${doc.id}/download/`} target="_blank" rel="noreferrer" title="Open" className="rounded-lg p-2 text-muted transition-colors hover:bg-line hover:text-ink dark:text-muted-dark dark:hover:bg-white/10 dark:hover:text-ink-dark">
                      <ExternalLink className="h-4 w-4" />
                    </a>
                    <a href={`${base}/api/documents/${doc.id}/download/?download=1`} title="Download" className="rounded-lg p-2 text-muted transition-colors hover:bg-line hover:text-ink dark:text-muted-dark dark:hover:bg-white/10 dark:hover:text-ink-dark">
                      <Download className="h-4 w-4" />
                    </a>
                    {renderExtraActions?.(doc)}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {pagination && pagination.num_pages > 1 && (
        <div className="flex items-center justify-between border-t border-line px-5 py-3 dark:border-line-dark">
          <p className="text-xs text-muted dark:text-muted-dark">Page {pagination.page} of {pagination.num_pages} · {pagination.count} total</p>
          <div className="flex gap-2">
            {pagination.has_previous && <button onClick={() => onPageChange(pagination.page - 1)} className="rounded-lg border border-line px-3 py-1.5 text-xs font-medium text-ink hover:bg-surface dark:border-line-dark dark:text-ink-dark dark:hover:bg-white/5">Previous</button>}
            {pagination.has_next && <button onClick={() => onPageChange(pagination.page + 1)} className="rounded-lg border border-line px-3 py-1.5 text-xs font-medium text-ink hover:bg-surface dark:border-line-dark dark:text-ink-dark dark:hover:bg-white/5">Next</button>}
          </div>
        </div>
      )}
    </div>
  );
}
