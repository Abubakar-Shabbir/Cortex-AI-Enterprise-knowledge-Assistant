import { useEffect, useState } from 'react';
import { Bot, CircleAlert, Cpu, Database, Eye, Lock, Save, Scissors, SlidersHorizontal, Zap } from 'lucide-react';
import PageSkeleton from '../components/PageSkeleton';
import Spinner from '../components/Spinner';
import ToggleSwitch from '../components/ToggleSwitch';
import { timeAgo } from '../lib/timeAgo';
import { useSession } from '../auth/SessionContext';
import { useAdminSettings, useSaveAdminSettings, useTestLlmProvider } from '../api/hooks';

// Port of templates/admin/settings.html.
export default function AdminSettings() {
  const { permissions } = useSession();
  const has = (code) => permissions.includes(code);

  const { data, isLoading } = useAdminSettings();
  const save = useSaveAdminSettings();
  const testConnection = useTestLlmProvider();

  const [form, setForm] = useState(null);
  const [dirty, setDirty] = useState(false);
  const [errors, setErrors] = useState([]);
  const [testing, setTesting] = useState({});
  const [testResults, setTestResults] = useState({});

  useEffect(() => {
    if (data && !dirty) {
      setForm(data.config);
    }
  }, [data]); // eslint-disable-line react-hooks/exhaustive-deps

  const set = (field, value) => {
    setForm((f) => ({ ...f, [field]: value }));
    setDirty(true);
  };

  if (isLoading || !form) return <PageSkeleton variant="detail" />;

  const { system_status: status, db_name: dbName, db_host: dbHost, llm_provider_options: providerOptions, can_edit_any: canEditAny } = data;

  const runTest = async (providerKey) => {
    setTesting((t) => ({ ...t, [providerKey]: true }));
    setTestResults((t) => ({ ...t, [providerKey]: null }));
    try {
      const result = await testConnection.mutateAsync(providerKey);
      setTestResults((t) => ({ ...t, [providerKey]: result }));
    } catch {
      setTestResults((t) => ({ ...t, [providerKey]: { ok: false, latency_ms: null, message: 'Request failed.' } }));
    } finally {
      setTesting((t) => ({ ...t, [providerKey]: false }));
    }
  };

  const onSubmit = async (e) => {
    e.preventDefault();
    setErrors([]);
    try {
      await save.mutateAsync(form);
      setDirty(false);
    } catch (err) {
      setErrors(err.data?.errors || [err.message]);
    }
  };

  const discard = () => {
    setForm(data.config);
    setDirty(false);
    setErrors([]);
  };

  return (
    <div>
      <div className="mb-4 flex flex-col gap-1">
        <h1 className="text-2xl font-bold tracking-tight text-ink dark:text-ink-dark">Settings</h1>
        <p className="text-sm text-muted dark:text-muted-dark">Live RAG pipeline configuration — changes here take effect immediately, no redeploy.</p>
      </div>

      <form onSubmit={onSubmit} className="pb-16">
        {errors.length > 0 && (
          <div className="mb-4 space-y-1 rounded-xl border border-danger/30 bg-danger/5 p-3.5 text-sm text-danger dark:border-danger-dark/30 dark:bg-danger-dark/10 dark:text-danger-dark">
            {errors.map((err, idx) => <p key={idx}>{err}</p>)}
          </div>
        )}

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {has('settings.manage_llm') && (
            <div className="rounded-2xl border border-line bg-card p-4 shadow-soft dark:border-line-dark dark:bg-card-dark lg:col-span-2">
              <h2 className="mb-1 flex items-center gap-2 text-sm font-semibold text-ink dark:text-ink-dark">
                <Bot className="h-4 w-4 text-primary dark:text-primary-soft" /> LLM Configuration
              </h2>
              <p className="mb-3 text-xs text-muted dark:text-muted-dark">
                The active provider below is what actually answers every request. By default there is no fallback — if it fails, times out, or hits a rate limit, the request fails with a clear error instead of silently switching providers. Turn on "Allow fallback" if you'd rather the request fall through to another configured provider than fail outright.
              </p>

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">Active Provider</label>
                  <select
                    value={form.llm_provider}
                    onChange={(e) => set('llm_provider', e.target.value)}
                    className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/15 dark:border-line-dark dark:bg-white/5 dark:text-ink-dark"
                  >
                    {providerOptions.map((opt) => <option key={opt.key} value={opt.key}>{opt.label}</option>)}
                  </select>
                </div>

                {providerOptions.filter((opt) => opt.key === form.llm_provider).map((opt) => (
                  <div key={opt.key}>
                    <label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">{opt.label} Model</label>
                    <select
                      value={form[opt.field_name]}
                      onChange={(e) => set(opt.field_name, e.target.value)}
                      className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/15 dark:border-line-dark dark:bg-white/5 dark:text-ink-dark"
                    >
                      {opt.model_choices.map((m) => <option key={m} value={m}>{m}</option>)}
                    </select>
                  </div>
                ))}
              </div>

              <div className="mt-3">
                <label className="mb-1 flex items-center justify-between text-xs font-medium text-muted dark:text-muted-dark">
                  <span>Answer temperature</span>
                  <span className="rounded-md bg-primary/10 px-1.5 py-0.5 font-mono text-[11px] font-semibold text-primary dark:text-primary-soft">{Number(form.answer_temperature).toFixed(2)}</span>
                </label>
                <input
                  type="range" step="0.05" min="0" max="1" value={form.answer_temperature}
                  onChange={(e) => set('answer_temperature', parseFloat(e.target.value))}
                  className="h-1.5 w-full max-w-xs cursor-pointer appearance-none rounded-full bg-line accent-primary dark:bg-line-dark"
                />
                <div className="mt-0.5 flex max-w-xs justify-between text-[10px] text-muted dark:text-muted-dark"><span>0 — deterministic</span><span>1 — creative</span></div>
              </div>

              <div className="mt-3 flex items-start gap-2">
                <input
                  type="checkbox" id="enable_fallback" checked={form.enable_fallback}
                  onChange={(e) => set('enable_fallback', e.target.checked)}
                  className="mt-0.5 h-4 w-4 rounded border-line text-primary focus:ring-primary/30 dark:border-line-dark"
                />
                <label htmlFor="enable_fallback" className="text-xs text-ink dark:text-ink-dark">
                  <span className="font-medium">Allow fallback to another provider</span>
                  <span className="block text-muted dark:text-muted-dark">Off by default. When off, a failure on the active provider fails the request instead of silently answering via a different provider/model.</span>
                </label>
              </div>

              <div className="mt-3 border-t border-line pt-3 dark:border-line-dark">
                <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted dark:text-muted-dark">Provider Status</p>
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                  {providerOptions.map((opt) => (
                    <div key={opt.key} className="rounded-lg border border-line px-3 py-2 dark:border-line-dark">
                      <div className="flex items-center justify-between gap-2">
                        <p className="flex items-center gap-1.5 text-sm font-medium text-ink dark:text-ink-dark">
                          {opt.label}
                          {opt.key === form.llm_provider && (
                            <span className="rounded-full bg-primary/10 px-1.5 py-0.5 text-[10px] font-semibold text-primary dark:text-primary-soft">Active</span>
                          )}
                        </p>
                        <button
                          type="button" onClick={() => runTest(opt.key)} disabled={testing[opt.key]}
                          className="shrink-0 inline-flex items-center gap-1 rounded-lg border border-line px-2 py-1 text-[11px] font-medium text-ink transition-colors hover:border-primary/30 hover:bg-primary/5 hover:text-primary disabled:opacity-50 dark:border-line-dark dark:text-ink-dark dark:hover:bg-primary/10"
                        >
                          {testing[opt.key] ? <Spinner size={12} /> : <Zap className="h-3 w-3" />}
                          Test
                        </button>
                      </div>
                      <p className={`mt-1 flex items-center gap-1.5 text-xs ${opt.configured ? 'text-success dark:text-success-dark' : 'text-muted dark:text-muted-dark'}`}>
                        <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${opt.configured ? 'bg-success dark:bg-success-dark' : 'bg-line dark:bg-line-dark'}`}></span>
                        {opt.configured ? 'API key configured' : 'No API key set'}
                      </p>
                      {testResults[opt.key] && (
                        <p className={`mt-1 text-xs ${testResults[opt.key].ok ? 'text-success dark:text-success-dark' : 'text-danger dark:text-danger-dark'}`}>
                          {testResults[opt.key].message}
                          {testResults[opt.key].latency_ms ? ` (${testResults[opt.key].latency_ms}ms)` : ''}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {has('settings.manage_embedding') && (
            <div className="rounded-2xl border border-line bg-card p-4 shadow-soft dark:border-line-dark dark:bg-card-dark">
              <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-ink dark:text-ink-dark">
                <Cpu className="h-4 w-4 text-primary dark:text-primary-soft" /> Embedding Model
              </h2>
              <dl className="space-y-2 text-sm">
                <div className="flex items-center justify-between"><dt className="text-muted dark:text-muted-dark">Model</dt><dd className="font-medium text-ink dark:text-ink-dark">{status.embedding_model || '—'}</dd></div>
                <div className="flex items-center justify-between"><dt className="text-muted dark:text-muted-dark">Dimensions</dt><dd className="font-medium text-ink dark:text-ink-dark">{status.embedding_dimension || '—'}</dd></div>
              </dl>
              <p className="mt-2 flex items-start gap-2 text-xs text-muted dark:text-muted-dark">
                <Lock className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                Not editable here — changing it requires re-embedding every existing chunk and a dimension migration, not just a config flip.
              </p>
            </div>
          )}

          {has('settings.manage_chunking') && (
            <div className="rounded-2xl border border-line bg-card p-4 shadow-soft dark:border-line-dark dark:bg-card-dark">
              <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-ink dark:text-ink-dark">
                <Scissors className="h-4 w-4 text-primary dark:text-primary-soft" /> Retrieval &amp; Chunking
              </h2>

              <div className="grid grid-cols-2 gap-2.5">
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">Chunk size</label>
                  <input type="number" min="100" value={form.chunk_size} onChange={(e) => set('chunk_size', parseInt(e.target.value, 10) || 0)} className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/15 dark:border-line-dark dark:bg-white/5 dark:text-ink-dark" />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">Chunk overlap</label>
                  <input type="number" min="0" value={form.chunk_overlap} onChange={(e) => set('chunk_overlap', parseInt(e.target.value, 10) || 0)} className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/15 dark:border-line-dark dark:bg-white/5 dark:text-ink-dark" />
                </div>
              </div>
              <p className="mb-2.5 mt-1 text-xs text-muted dark:text-muted-dark">Applies to newly-uploaded documents only — existing chunks aren't retroactively resized.</p>

              <label className="mb-1 block text-xs font-medium text-muted dark:text-muted-dark">Retrieval top-K</label>
              <input type="number" min="1" max="20" value={form.top_k} onChange={(e) => set('top_k', parseInt(e.target.value, 10) || 0)} className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/15 dark:border-line-dark dark:bg-white/5 dark:text-ink-dark" />
            </div>
          )}

          {has('settings.manage_database') && (
            <div className="rounded-2xl border border-line bg-card p-4 shadow-soft dark:border-line-dark dark:bg-card-dark">
              <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-ink dark:text-ink-dark">
                <Database className="h-4 w-4 text-primary dark:text-primary-soft" /> Database
              </h2>
              <dl className="space-y-2 text-sm">
                <div className="flex items-center justify-between"><dt className="text-muted dark:text-muted-dark">Database</dt><dd className="font-medium text-ink dark:text-ink-dark">{dbName}</dd></div>
                <div className="flex items-center justify-between"><dt className="text-muted dark:text-muted-dark">Host</dt><dd className="font-medium text-ink dark:text-ink-dark">{dbHost}</dd></div>
                <div className="flex items-center justify-between">
                  <dt className="text-muted dark:text-muted-dark">pgvector</dt>
                  <dd className={`flex items-center gap-1.5 font-medium ${status.pgvector_enabled ? 'text-success dark:text-success-dark' : 'text-danger dark:text-danger-dark'}`}>
                    <span className={`h-1.5 w-1.5 rounded-full ${status.pgvector_enabled ? 'bg-success dark:bg-success-dark' : 'bg-danger dark:bg-danger-dark'}`}></span>
                    {status.pgvector_enabled ? 'Enabled' : 'Not enabled'}
                  </dd>
                </div>
              </dl>
              <p className="mt-2 flex items-start gap-2 text-xs text-muted dark:text-muted-dark">
                <Lock className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                Not editable here — changing it live would mean writing the new connection through the very connection being replaced.
              </p>
            </div>
          )}
        </div>

        {has('settings.manage_retrieval') && (
          <div className="mt-4 rounded-2xl border border-line bg-card p-4 shadow-soft dark:border-line-dark dark:bg-card-dark">
            <h2 className="mb-1 flex items-center gap-2 text-sm font-semibold text-ink dark:text-ink-dark">
              <SlidersHorizontal className="h-4 w-4 text-primary dark:text-primary-soft" /> Advanced Retrieval
            </h2>
            <p className="mb-3 text-xs text-muted dark:text-muted-dark">Sprint 6-8 retrieval enhancements — each reuses the existing hybrid search pipeline, no restart required to flip one on or off.</p>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <ToggleSwitch
                checked={form.enable_query_expansion} onChange={(v) => set('enable_query_expansion', v)}
                title="Query Expansion" description="Enriches BM25 with LLM-generated phrasings." warning="+1 LLM call, adds latency."
              />
              <ToggleSwitch
                checked={form.enable_hyde} onChange={(v) => set('enable_hyde', v)}
                title="HyDE" description="Embeds a hypothetical answer instead of the question." warning="+1 LLM call, adds latency."
              />
              <div>
                <ToggleSwitch
                  checked={form.enable_multi_query} onChange={(v) => set('enable_multi_query', v)}
                  title="Multi-Query (RAG-Fusion)" description="Fuses results across rephrased variants." warning="+1 LLM call, adds latency."
                />
                <input type="number" min="1" max="10" value={form.multi_query_variants} onChange={(e) => set('multi_query_variants', parseInt(e.target.value, 10) || 0)} title="Number of variants" className="mt-2 w-24 rounded-lg border border-line bg-surface px-2 py-1 text-xs text-ink focus:border-primary focus:outline-none dark:border-line-dark dark:bg-white/5 dark:text-ink-dark" />
              </div>
              <div>
                <ToggleSwitch
                  checked={form.enable_dynamic_top_k} onChange={(v) => set('enable_dynamic_top_k', v)}
                  title="Dynamic Top-K" description="Widens retrieval depth for complex questions."
                />
                <input type="number" min="1" max="50" value={form.dynamic_top_k_max} onChange={(e) => set('dynamic_top_k_max', parseInt(e.target.value, 10) || 0)} title="Max top-K" className="mt-2 w-24 rounded-lg border border-line bg-surface px-2 py-1 text-xs text-ink focus:border-primary focus:outline-none dark:border-line-dark dark:bg-white/5 dark:text-ink-dark" />
              </div>
              <div>
                <ToggleSwitch
                  checked={form.enable_reranker} onChange={(v) => set('enable_reranker', v)}
                  title="Cross-Encoder Reranker" description="Re-scores candidates with BAAI/bge-reranker-base."
                />
                <input type="number" min="1" max="10" value={form.reranker_candidate_multiplier} onChange={(e) => set('reranker_candidate_multiplier', parseInt(e.target.value, 10) || 0)} title="Candidate multiplier" className="mt-2 w-24 rounded-lg border border-line bg-surface px-2 py-1 text-xs text-ink focus:border-primary focus:outline-none dark:border-line-dark dark:bg-white/5 dark:text-ink-dark" />
              </div>
              <div>
                <ToggleSwitch
                  checked={form.enable_context_compression} onChange={(v) => set('enable_context_compression', v)}
                  title="Context Compression" description="Drops redundant chunks before the LLM sees them."
                />
                <input type="number" step="0.01" min="0" max="1" value={form.context_compression_threshold} onChange={(e) => set('context_compression_threshold', parseFloat(e.target.value) || 0)} title="Similarity threshold" className="mt-2 w-24 rounded-lg border border-line bg-surface px-2 py-1 text-xs text-ink focus:border-primary focus:outline-none dark:border-line-dark dark:bg-white/5 dark:text-ink-dark" />
              </div>
            </div>
          </div>
        )}

        <p className="mt-3 text-xs text-muted dark:text-muted-dark">
          {form.updated_by ? <>Last updated by {form.updated_by}, {timeAgo(form.updated_at)} ago.</> : 'Not yet edited — showing settings.py defaults.'}
          {!canEditAny && (
            <span className="ml-1 inline-flex items-center gap-1"><Eye className="h-3.5 w-3.5" /> View-only access.</span>
          )}
        </p>

        {canEditAny && dirty && (
          <div className="fixed inset-x-0 bottom-0 z-40 border-t border-line bg-card/95 px-4 py-3 shadow-2xl backdrop-blur dark:border-line-dark dark:bg-card-dark/95 lg:pl-64">
            <div className="mx-auto flex max-w-5xl items-center justify-between gap-3">
              <p className="flex items-center gap-2 text-sm font-medium text-ink dark:text-ink-dark">
                <CircleAlert className="h-4 w-4 text-warning" /> You have unsaved changes.
              </p>
              <div className="flex items-center gap-2">
                <button type="button" onClick={discard} className="rounded-lg border border-line px-3.5 py-2 text-xs font-medium text-ink transition-colors hover:bg-surface dark:border-line-dark dark:text-ink-dark dark:hover:bg-white/5">
                  Discard
                </button>
                <button type="submit" disabled={save.isPending} className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-xs font-semibold text-white transition-colors hover:bg-primary-dark disabled:opacity-60">
                  {save.isPending ? <Spinner size={14} /> : <Save className="h-3.5 w-3.5" />} Save Settings
                </button>
              </div>
            </div>
          </div>
        )}
      </form>
    </div>
  );
}
