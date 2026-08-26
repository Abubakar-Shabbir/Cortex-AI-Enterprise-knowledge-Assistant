import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Folder, FolderPlus, MoreVertical, Pencil, Trash2, X } from 'lucide-react';
import PageHeader from '../components/PageHeader';
import EmptyState from '../components/EmptyState';
import AppLoader from '../components/AppLoader';
import Spinner from '../components/Spinner';
import DocumentsTabs from '../layout/DocumentsTabs';
import { useCollectionAction, useCollections } from '../api/hooks';

function CollectionCard({ collection, onRename, onDelete }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [renameOpen, setRenameOpen] = useState(false);
  const [name, setName] = useState(collection.name);

  return (
    <div className="rounded-xl border border-line bg-card p-5 shadow-soft transition-transform hover:-translate-y-0.5 dark:border-line-dark dark:bg-card-dark">
      <div className="flex items-start justify-between">
        <Link to={`/documents/collections/${collection.id}`} className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary-soft/50 text-primary dark:bg-primary/15 dark:text-primary-soft">
          <Folder className="h-5 w-5" />
        </Link>
        <div className="relative">
          <button onClick={() => setMenuOpen((v) => !v)} className="rounded-lg p-1.5 text-muted hover:bg-surface dark:text-muted-dark dark:hover:bg-white/5">
            <MoreVertical className="h-4 w-4" />
          </button>
          {menuOpen && (
            <div className="absolute right-0 z-10 mt-1 w-36 rounded-lg border border-line bg-card p-1 shadow-lg dark:border-line-dark dark:bg-card-dark">
              <button onClick={() => { setRenameOpen(true); setMenuOpen(false); }} className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-xs font-medium text-ink hover:bg-surface dark:text-ink-dark dark:hover:bg-white/5">
                <Pencil className="h-3.5 w-3.5" /> Rename
              </button>
              <button
                onClick={() => { setMenuOpen(false); if (window.confirm('Delete this collection? Documents inside are not deleted.')) onDelete(collection.id); }}
                className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-xs font-medium text-danger hover:bg-danger/10 dark:text-danger-dark"
              >
                <Trash2 className="h-3.5 w-3.5" /> Delete
              </button>
            </div>
          )}
        </div>
      </div>

      <Link to={`/documents/collections/${collection.id}`}>
        <h3 className="mt-3 text-sm font-semibold text-ink dark:text-ink-dark">{collection.name}</h3>
        {collection.description && <p className="mt-1 text-xs text-muted dark:text-muted-dark">{collection.description}</p>}
        <p className="mt-3 text-xs font-medium text-muted dark:text-muted-dark">{collection.doc_count} document{collection.doc_count === 1 ? '' : 's'}</p>
      </Link>

      {renameOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={(e) => { if (e.target === e.currentTarget) setRenameOpen(false); }}>
          <div className="w-full max-w-sm rounded-xl border border-line bg-card p-5 shadow-soft dark:border-line-dark dark:bg-card-dark">
            <h3 className="mb-3 text-sm font-semibold text-ink dark:text-ink-dark">Rename collection</h3>
            <form
              onSubmit={(e) => { e.preventDefault(); onRename(collection.id, name); setRenameOpen(false); }}
              className="flex flex-col gap-3"
            >
              <input
                type="text" value={name} onChange={(e) => setName(e.target.value)} required
                className="w-full rounded-lg border border-line bg-transparent px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none dark:border-line-dark dark:text-ink-dark"
              />
              <div className="flex justify-end gap-2">
                <button type="button" onClick={() => setRenameOpen(false)} className="rounded-lg border border-line px-3.5 py-2 text-sm font-medium text-ink hover:bg-surface dark:border-line-dark dark:text-ink-dark dark:hover:bg-white/5">Cancel</button>
                <button type="submit" className="rounded-lg bg-primary px-3.5 py-2 text-sm font-semibold text-white hover:bg-primary-dark">Save</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

// Port of templates/documents/collections.html.
export default function Collections() {
  const { data, isLoading } = useCollections();
  const action = useCollectionAction();
  const [createOpen, setCreateOpen] = useState(false);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [error, setError] = useState('');

  const onCreate = async (e) => {
    e.preventDefault();
    setError('');
    try {
      await action.mutateAsync({ action: 'create', name, description });
      setName('');
      setDescription('');
      setCreateOpen(false);
    } catch (err) {
      setError(err.data?.error || err.message);
    }
  };

  const onRename = (collectionId, newName) => action.mutate({ action: 'rename', collection_id: collectionId, name: newName });
  const onDelete = (collectionId) => action.mutate({ action: 'delete', collection_id: collectionId });

  return (
    <>
      <PageHeader title="Collections" subtitle="Personal folders for organizing documents you own or can access." />
      <DocumentsTabs />

      <div className="mb-6 flex justify-end">
        <button onClick={() => setCreateOpen(true)} className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-primary-dark">
          <FolderPlus className="h-4 w-4" /> New Collection
        </button>
      </div>

      {isLoading || !data ? <AppLoader variant="page" /> : data.collections.length > 0 ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {data.collections.map((c) => (
            <CollectionCard key={c.id} collection={c} onRename={onRename} onDelete={onDelete} />
          ))}
        </div>
      ) : (
        <EmptyState icon={FolderPlus} title="No collections yet" message="Create a collection to organize documents you own or can access." />
      )}

      {createOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={(e) => { if (e.target === e.currentTarget) setCreateOpen(false); }}>
          <div className="w-full max-w-sm rounded-xl border border-line bg-card p-5 shadow-soft dark:border-line-dark dark:bg-card-dark">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-ink dark:text-ink-dark">New collection</h3>
              <button onClick={() => setCreateOpen(false)} className="flex h-7 w-7 items-center justify-center rounded-lg text-muted hover:bg-surface dark:text-muted-dark dark:hover:bg-white/5"><X className="h-4 w-4" /></button>
            </div>
            <form onSubmit={onCreate} className="flex flex-col gap-3">
              {error && <p className="text-xs text-danger dark:text-danger-dark">{error}</p>}
              <input
                type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="Collection name" required
                className="w-full rounded-lg border border-line bg-transparent px-3 py-2 text-sm text-ink placeholder:text-muted focus:border-primary focus:outline-none dark:border-line-dark dark:text-ink-dark"
              />
              <textarea
                value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Description (optional)" rows={2}
                className="w-full rounded-lg border border-line bg-transparent px-3 py-2 text-sm text-ink placeholder:text-muted focus:border-primary focus:outline-none dark:border-line-dark dark:text-ink-dark"
              />
              <div className="flex justify-end gap-2">
                <button type="button" onClick={() => setCreateOpen(false)} className="rounded-lg border border-line px-3.5 py-2 text-sm font-medium text-ink hover:bg-surface dark:border-line-dark dark:text-ink-dark dark:hover:bg-white/5">Cancel</button>
                <button type="submit" disabled={action.isPending} className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3.5 py-2 text-sm font-semibold text-white hover:bg-primary-dark disabled:opacity-60">
                  {action.isPending && <Spinner size={14} />} {action.isPending ? 'Creating…' : 'Create'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
}
