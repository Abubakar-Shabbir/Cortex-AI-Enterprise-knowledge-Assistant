import { useState } from 'react';
import {
  Bell, ChevronDown, Eye, FileDown, FileText, Plus, Save, ScrollText, Search,
  Settings as SettingsIcon, Shield, ShieldCheck, Sparkles, Trash2, Users, BarChart3, HeartPulse, MessageSquare, Share2,
} from 'lucide-react';
import { useAdminRoles, useCreateAdminRole, useDeleteAdminRole, useUpdateRolePermissions } from '../api/hooks';
import PageSkeleton from '../components/PageSkeleton';
import Spinner from '../components/Spinner';

const MODULE_ICONS = {
  documents: FileText, knowledge_base: Share2, ask_ai: MessageSquare, queries: Search,
  analytics: BarChart3, reports: FileDown, ai_tasks: Sparkles, users: Users, roles: Shield,
  settings: SettingsIcon, system: HeartPulse, activity: ScrollText, notifications: Bell,
};

function ModuleAccordion({ module, selected, onToggleModule, onTogglePermission }) {
  const [open, setOpen] = useState(false);
  const Icon = MODULE_ICONS[module.slug] || Shield;
  const codenames = module.permissions.map((p) => p.codename);
  const grantedCount = codenames.filter((c) => selected.includes(c)).length;
  const allGranted = codenames.length > 0 && grantedCount === codenames.length;
  const badgeClass = grantedCount === 0
    ? 'bg-line/60 text-muted dark:bg-white/10 dark:text-muted-dark'
    : allGranted
      ? 'bg-success/10 text-success dark:text-success-dark'
      : 'bg-primary/10 text-primary dark:text-primary-soft';

  return (
    <div className="overflow-hidden rounded-xl border border-line dark:border-line-dark">
      <button type="button" onClick={() => setOpen((v) => !v)} className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left transition-colors hover:bg-surface dark:hover:bg-white/5">
        <span className="flex min-w-0 items-center gap-2.5">
          <Icon className="h-4 w-4 shrink-0 text-muted dark:text-muted-dark" />
          <span className="truncate text-sm font-semibold text-ink dark:text-ink-dark">{module.label}</span>
          {module.hidden_count > 0 && <span className="shrink-0 text-[10px] text-muted dark:text-muted-dark">+{module.hidden_count} hidden</span>}
        </span>
        <span className="flex shrink-0 items-center gap-3">
          <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold tabular-nums ${badgeClass}`}>{grantedCount} / {codenames.length}</span>
          <ChevronDown className={`h-4 w-4 shrink-0 text-muted transition-transform duration-150 dark:text-muted-dark ${open ? 'rotate-180' : ''}`} />
        </span>
      </button>

      {open && (
        <div className="border-t border-line bg-surface/60 px-4 py-3 dark:border-line-dark dark:bg-white/[0.03]">
          <label className="mb-2.5 flex items-center gap-2 border-b border-line pb-2.5 text-xs font-semibold text-primary dark:border-line-dark dark:text-primary-soft">
            <input type="checkbox" checked={allGranted} onChange={(e) => onToggleModule(codenames, e.target.checked)} className="rounded border-line text-primary focus:ring-primary/30 dark:border-line-dark" />
            Select All
          </label>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {module.permissions.map((permission) => (
              <label key={permission.codename} className="flex items-start gap-2 text-sm text-ink dark:text-ink-dark">
                <input
                  type="checkbox" checked={selected.includes(permission.codename)}
                  onChange={() => onTogglePermission(permission.codename)}
                  className="mt-0.5 rounded border-line text-primary focus:ring-primary/30 dark:border-line-dark"
                />
                <span className="flex items-center gap-1.5" title={permission.description}>
                  {permission.name}
                  {permission.sensitive && (
                    <span title="Exposes personally-identifiable data - grant only to explicitly authorized roles." className="inline-flex items-center gap-0.5 rounded-full bg-warning/10 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-warning dark:text-warning-dark">
                      <Eye className="h-2.5 w-2.5" /> Sensitive
                    </span>
                  )}
                </span>
              </label>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function RoleCard({ item, permissionModules, totalPermissionCount, onSave, onDelete, saving, deleting }) {
  const [selected, setSelected] = useState(item.granted);

  const toggleModule = (codenames, checked) => {
    setSelected((prev) => (checked ? [...new Set([...prev, ...codenames])] : prev.filter((c) => !codenames.includes(c))));
  };
  const togglePermission = (codename) => {
    setSelected((prev) => (prev.includes(codename) ? prev.filter((c) => c !== codename) : [...prev, codename]));
  };

  return (
    <div className="rounded-2xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-5 py-4 dark:border-line-dark">
        <div>
          <h2 className="flex items-center gap-2 text-sm font-semibold text-ink dark:text-ink-dark">
            {item.name}
            {item.is_system && <span className="inline-flex items-center rounded-full bg-line/60 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted dark:bg-white/5 dark:text-muted-dark">Built-in</span>}
          </h2>
          {item.description && <p className="mt-0.5 text-xs text-muted dark:text-muted-dark">{item.description}</p>}
        </div>
        {!item.is_system && (
          <button
            type="button"
            onClick={() => { if (window.confirm(`Delete the '${item.name}' role? Users must be reassigned first.`)) onDelete(item.id); }}
            disabled={deleting}
            className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium text-danger hover:bg-danger/10 disabled:opacity-60 dark:text-danger-dark"
          >
            <Trash2 className="h-3.5 w-3.5" /> Delete
          </button>
        )}
      </div>

      {item.slug === 'admin' ? (
        <div className="px-5 py-4">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-success/10 px-2.5 py-1 text-xs font-medium text-success dark:text-success-dark">
            <ShieldCheck className="h-3.5 w-3.5" /> Full system access
          </span>
          <p className="mt-2 text-sm text-muted dark:text-muted-dark">Admin always has every permission by design - including any added later - and can't be restricted. Create a custom role instead for narrower access.</p>
        </div>
      ) : (
        <form onSubmit={(e) => { e.preventDefault(); onSave(item.id, selected); }} className="px-5 py-4">
          <p className="mb-3 text-xs text-muted dark:text-muted-dark">
            {selected.length} of {totalPermissionCount} permissions granted, across {permissionModules.length} modules. Click a module to view and choose its actions.
            {item.hidden_granted_count > 0 && (
              <span className="mt-0.5 block text-[11px] italic">+{item.hidden_granted_count} more permission{item.hidden_granted_count === 1 ? '' : 's'} granted on this role, outside your own permissions - not shown or editable here.</span>
            )}
          </p>

          <div className="space-y-2">
            {permissionModules.map((module) => (
              <ModuleAccordion key={module.slug} module={module} selected={selected} onToggleModule={toggleModule} onTogglePermission={togglePermission} />
            ))}
          </div>

          <button type="submit" disabled={saving} className="mt-4 inline-flex items-center gap-2 rounded-lg bg-primary/10 px-4 py-2 text-sm font-semibold text-primary hover:bg-primary/15 disabled:opacity-60">
            {saving ? <Spinner size={16} /> : <Save className="h-4 w-4" />} Save Permissions
          </button>
        </form>
      )}
    </div>
  );
}

// Port of templates/admin/roles.html.
export default function AdminRoles() {
  const { data, isLoading } = useAdminRoles();
  const createRole = useCreateAdminRole();
  const updatePermissions = useUpdateRolePermissions();
  const deleteRole = useDeleteAdminRole();

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [error, setError] = useState('');

  const onCreate = async (e) => {
    e.preventDefault();
    setError('');
    try {
      await createRole.mutateAsync({ name, description });
      setName('');
      setDescription('');
    } catch (err) {
      setError(err.data?.error || err.message);
    }
  };

  if (isLoading || !data) return <PageSkeleton variant="detail" />;

  return (
    <>
      <div className="mb-6 flex flex-col gap-1">
        <h1 className="text-2xl font-bold tracking-tight text-ink dark:text-ink-dark">Roles</h1>
        <p className="text-sm text-muted dark:text-muted-dark">What each role can do. Admin always has full system access. Add a role for a future need (Manager, HR, Auditor…) without any code change — pick a module below, then choose exactly which actions it grants.</p>
      </div>

      <div className="mb-6 rounded-2xl border border-line bg-card p-5 shadow-soft dark:border-line-dark dark:bg-card-dark">
        <h2 className="mb-4 text-sm font-semibold text-ink dark:text-ink-dark">Create a Role</h2>
        <form onSubmit={onCreate} className="flex flex-col gap-3 sm:flex-row sm:items-end">
          {error && <p className="text-xs text-danger dark:text-danger-dark sm:basis-full">{error}</p>}
          <div className="flex-1">
            <label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">Name</label>
            <input type="text" value={name} onChange={(e) => setName(e.target.value)} required placeholder="e.g. Auditor" className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/15 dark:border-line-dark dark:bg-white/5 dark:text-ink-dark" />
          </div>
          <div className="flex-[2]">
            <label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">Description</label>
            <input type="text" value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Read-only access for compliance review" className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/15 dark:border-line-dark dark:bg-white/5 dark:text-ink-dark" />
          </div>
          <button type="submit" disabled={createRole.isPending} className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-primary-dark disabled:opacity-60">
            {createRole.isPending ? <Spinner size={16} /> : <Plus className="h-4 w-4" />} {createRole.isPending ? 'Creating…' : 'Create Role'}
          </button>
        </form>
      </div>

      <div className="space-y-5">
        {data.roles.map((item) => (
          <RoleCard
            key={item.id} item={item} permissionModules={data.permission_modules} totalPermissionCount={data.total_permission_count}
            onSave={(roleId, permissions) => updatePermissions.mutate({ roleId, permissions })}
            onDelete={(roleId) => deleteRole.mutate(roleId)}
            saving={updatePermissions.isPending} deleting={deleteRole.isPending}
          />
        ))}
      </div>
    </>
  );
}
