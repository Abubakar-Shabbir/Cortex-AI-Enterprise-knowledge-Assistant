import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowRight, Bot, Cog, Cpu, Database, MemoryStick, RefreshCw, ServerCog, SlidersHorizontal,
  Terminal, TriangleAlert, Zap,
} from 'lucide-react';
import AppLoader from '../components/AppLoader';
import Spinner from '../components/Spinner';
import { timeAgo } from '../lib/timeAgo';
import { fetchMonitoringLive, useMonitoring } from '../api/hooks';

function SettingRow({ label, description, value }) {
  return (
    <div className="flex items-center justify-between gap-4 px-4 py-2.5">
      <div>
        <p className="text-sm font-medium text-ink dark:text-ink-dark">{label}</p>
        {description && <p className="text-xs text-muted dark:text-muted-dark">{description}</p>}
      </div>
      <span className="shrink-0 rounded-lg bg-surface px-3 py-1.5 text-sm font-semibold text-ink dark:bg-white/5 dark:text-ink-dark">{value}</span>
    </div>
  );
}

function RecentErrorsPanel({ errors }) {
  if (!errors?.length) return null;
  return (
    <details className="mt-2 text-xs">
      <summary className="flex list-none cursor-pointer items-center gap-1 font-medium text-danger dark:text-danger-dark">
        <TriangleAlert className="h-3 w-3" /> {errors.length} recent issue{errors.length === 1 ? '' : 's'}
      </summary>
      <div className="mt-1.5 space-y-1.5 border-l-2 border-danger/20 pl-2 dark:border-danger-dark/20">
        {errors.map((group, idx) => (
          <div key={idx}>
            <p className="text-muted dark:text-muted-dark" title={group.message}>{group.message.length > 70 ? `${group.message.slice(0, 70)}…` : group.message}</p>
            <p className="text-[10px] text-muted/70 dark:text-muted-dark/70">×{group.occurrence_count} · last {timeAgo(group.last_seen)} ago</p>
          </div>
        ))}
      </div>
    </details>
  );
}

const RESOURCE_DOT = (percent) => (percent >= 90 ? 'bg-danger' : percent >= 75 ? 'bg-warning' : 'bg-success');

// Port of templates/monitoring.html.
export default function Monitoring() {
  const [checkedAt, setCheckedAt] = useState(new Date());
  const [ago, setAgo] = useState(0);
  const [checkingNow, setCheckingNow] = useState(false);
  const [liveOverride, setLiveOverride] = useState(null);
  const { data: queryPayload } = useMonitoring();
  const payload = liveOverride || queryPayload;

  useEffect(() => {
    const t = setInterval(() => setAgo(Math.floor((Date.now() - checkedAt.getTime()) / 1000)), 1000);
    return () => clearInterval(t);
  }, [checkedAt]);

  useEffect(() => {
    if (queryPayload) {
      setLiveOverride(null); // the next lightweight auto-refresh supersedes a one-off live check
      setCheckedAt(new Date());
    }
  }, [queryPayload]);

  const checkNow = async () => {
    if (checkingNow) return;
    setCheckingNow(true);
    try {
      const data = await fetchMonitoringLive();
      setLiveOverride(data);
      setCheckedAt(new Date());
    } finally {
      setCheckingNow(false);
    }
  };

  if (!payload) return <AppLoader variant="page" />;

  const { status, health, chunk_size: chunkSize, chunk_overlap: chunkOverlap, top_k: topK, django_version: djangoVersion, uptime_display: uptimeDisplay, can_view_system_logs: canViewSystemLogs } = payload;

  const agoLabel = ago < 5 ? 'just now' : ago < 60 ? `${ago}s ago` : `${Math.floor(ago / 60)}m ago`;
  const statusDotClass = health.status === 'ok' ? 'bg-success' : health.status === 'critical' ? 'bg-danger' : 'bg-warning';
  const statusLabel = health.status === 'ok' ? 'All systems operational' : health.status.charAt(0).toUpperCase() + health.status.slice(1);

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-ink dark:text-ink-dark">Monitoring</h1>
          <p className="mt-1 text-sm text-muted dark:text-muted-dark">Live infrastructure health and RAG pipeline configuration. Visible to administrators only.</p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-2 rounded-lg border border-line bg-card px-3.5 py-2 text-xs font-medium shadow-soft dark:border-line-dark dark:bg-card-dark">
            <span className={`h-1.5 w-1.5 rounded-full ${statusDotClass}`}></span>
            <span className="text-ink dark:text-ink-dark">{statusLabel}</span>
            <span className="text-muted dark:text-muted-dark">· checked {agoLabel}</span>
          </div>
          <button
            type="button" onClick={checkNow} disabled={checkingNow}
            className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-card px-3.5 py-2 text-xs font-medium text-ink shadow-soft transition-colors hover:border-primary/30 hover:text-primary disabled:opacity-60 dark:border-line-dark dark:bg-card-dark dark:text-ink-dark dark:hover:bg-primary/10"
          >
            {checkingNow ? <Spinner size={14} /> : <RefreshCw className="h-3.5 w-3.5" />}
            <span>{checkingNow ? 'Checking…' : 'Check Now'}</span>
          </button>
        </div>
      </div>

      <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
        <div className="rounded-xl border border-line bg-card p-3.5 shadow-soft dark:border-line-dark dark:bg-card-dark">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-muted dark:text-muted-dark">PostgreSQL</span>
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary-soft/50 text-primary dark:bg-primary/15 dark:text-primary-soft"><Database className="h-3.5 w-3.5" /></div>
          </div>
          <div className="mt-2.5 flex items-center gap-1.5 text-sm font-semibold text-ink dark:text-ink-dark">
            <span className={`h-1.5 w-1.5 rounded-full ${health.checks.database ? 'bg-success' : 'bg-danger'}`}></span>
            {health.checks.database ? 'Connected' : 'Unreachable'}
          </div>
          <p className="mt-1 text-xs text-muted dark:text-muted-dark">pgvector {health.checks.pgvector ? 'enabled' : 'not enabled'}</p>
          <RecentErrorsPanel errors={health.recent_errors.database} />
        </div>

        <div className="rounded-xl border border-line bg-card p-3.5 shadow-soft dark:border-line-dark dark:bg-card-dark">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-muted dark:text-muted-dark">Cache</span>
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary-soft/50 text-primary dark:bg-primary/15 dark:text-primary-soft"><Zap className="h-3.5 w-3.5" /></div>
          </div>
          <div className="mt-2.5 flex items-center gap-1.5 text-sm font-semibold text-ink dark:text-ink-dark">
            <span className="h-1.5 w-1.5 rounded-full bg-success"></span> Active
          </div>
          <p className="mt-1 text-xs text-muted dark:text-muted-dark">In-memory (process-local)</p>
        </div>

        <div className="rounded-xl border border-line bg-card p-3.5 shadow-soft dark:border-line-dark dark:bg-card-dark">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-muted dark:text-muted-dark">Background Jobs</span>
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary-soft/50 text-primary dark:bg-primary/15 dark:text-primary-soft"><Cog className="h-3.5 w-3.5" /></div>
          </div>
          <div className="mt-2.5 flex items-center gap-1.5 text-sm font-semibold text-ink dark:text-ink-dark">
            <span className={`h-1.5 w-1.5 rounded-full ${health.checks.background_jobs ? 'bg-success' : 'bg-danger'}`}></span>
            {health.checks.background_jobs ? 'Available' : 'Unavailable'}
          </div>
          <p className="mt-1 text-xs text-muted dark:text-muted-dark">{health.background_jobs.active} active · {health.background_jobs.max_workers} worker threads</p>
          <RecentErrorsPanel errors={health.recent_errors.background_jobs} />
        </div>

        <div className="rounded-xl border border-line bg-card p-3.5 shadow-soft dark:border-line-dark dark:bg-card-dark">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-muted dark:text-muted-dark">LLM Providers</span>
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary-soft/50 text-primary dark:bg-primary/15 dark:text-primary-soft"><Bot className="h-3.5 w-3.5" /></div>
          </div>
          {Object.keys(health.checks.llm_providers || {}).length > 0 ? (
            <>
              <div className="mt-2.5 space-y-1.5">
                {Object.entries(health.checks.llm_providers).map(([provider, result]) => (
                  <div key={provider} title={result.message} className="flex items-center justify-between gap-2 text-xs">
                    <span className="flex items-center gap-1.5 font-medium text-ink dark:text-ink-dark">
                      <span className={`h-1.5 w-1.5 rounded-full ${result.ok === true ? 'bg-success' : result.ok === false ? 'bg-danger' : 'bg-muted'}`}></span>
                      {provider.charAt(0).toUpperCase() + provider.slice(1)}
                      {provider === status.llm_provider && <span className="rounded-full bg-primary/10 px-1.5 py-0.5 text-[10px] font-semibold text-primary dark:text-primary-soft">Active</span>}
                    </span>
                    <span className="text-muted dark:text-muted-dark">
                      {result.ok === null ? 'no data' : result.latency_ms ? `${result.latency_ms}ms` : result.ok ? 'ok' : 'down'}
                    </span>
                  </div>
                ))}
              </div>
              <p className="mt-1.5 text-[10px] text-muted/70 dark:text-muted-dark/70">
                {health.live_llm_check ? 'Live check' : 'From recent usage'} · <button type="button" onClick={checkNow} className="underline hover:text-primary">check now</button>
              </p>
            </>
          ) : (
            <>
              <div className="mt-2.5 flex items-center gap-1.5 text-sm font-semibold text-ink dark:text-ink-dark">
                <span className="h-1.5 w-1.5 rounded-full bg-warning"></span> None configured
              </div>
              <p className="mt-1 text-xs text-muted dark:text-muted-dark">Add an API key to .env</p>
            </>
          )}
          <RecentErrorsPanel errors={health.recent_errors.llm_providers} />
        </div>

        <div className="rounded-xl border border-line bg-card p-3.5 shadow-soft dark:border-line-dark dark:bg-card-dark">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-muted dark:text-muted-dark">CPU</span>
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary-soft/50 text-primary dark:bg-primary/15 dark:text-primary-soft"><Cpu className="h-3.5 w-3.5" /></div>
          </div>
          {health.resources.available ? (
            <>
              <div className="mt-2.5 flex items-center gap-1.5 text-sm font-semibold text-ink dark:text-ink-dark">
                <span className={`h-1.5 w-1.5 rounded-full ${RESOURCE_DOT(health.resources.cpu_percent)}`}></span> {health.resources.cpu_percent}%
              </div>
              <div className="mt-1.5 h-1 w-full overflow-hidden rounded-full bg-line dark:bg-line-dark">
                <div className={`h-full rounded-full ${RESOURCE_DOT(health.resources.cpu_percent)}`} style={{ width: `${health.resources.cpu_percent}%` }}></div>
              </div>
              <p className="mt-1.5 text-xs text-muted dark:text-muted-dark">Host CPU utilization</p>
            </>
          ) : (
            <div className="mt-2.5 flex items-center gap-1.5 text-sm font-semibold text-ink dark:text-ink-dark">
              <span className="h-1.5 w-1.5 rounded-full bg-muted"></span> Unavailable
            </div>
          )}
        </div>

        <div className="rounded-xl border border-line bg-card p-3.5 shadow-soft dark:border-line-dark dark:bg-card-dark">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-muted dark:text-muted-dark">Memory</span>
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary-soft/50 text-primary dark:bg-primary/15 dark:text-primary-soft"><MemoryStick className="h-3.5 w-3.5" /></div>
          </div>
          {health.resources.available ? (
            <>
              <div className="mt-2.5 flex items-center gap-1.5 text-sm font-semibold text-ink dark:text-ink-dark">
                <span className={`h-1.5 w-1.5 rounded-full ${RESOURCE_DOT(health.resources.memory_percent)}`}></span> {health.resources.memory_percent}%
              </div>
              <div className="mt-1.5 h-1 w-full overflow-hidden rounded-full bg-line dark:bg-line-dark">
                <div className={`h-full rounded-full ${RESOURCE_DOT(health.resources.memory_percent)}`} style={{ width: `${health.resources.memory_percent}%` }}></div>
              </div>
              <p className="mt-1.5 text-xs text-muted dark:text-muted-dark">Host memory utilization</p>
            </>
          ) : (
            <div className="mt-2.5 flex items-center gap-1.5 text-sm font-semibold text-ink dark:text-ink-dark">
              <span className="h-1.5 w-1.5 rounded-full bg-muted"></span> Unavailable
            </div>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <div className="rounded-xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">
          <div className="flex items-center gap-2 border-b border-line px-4 py-3 dark:border-line-dark">
            <SlidersHorizontal className="h-4 w-4 text-primary dark:text-primary-soft" />
            <h2 className="text-sm font-semibold text-ink dark:text-ink-dark">RAG Pipeline Configuration</h2>
          </div>
          <div className="divide-y divide-line dark:divide-line-dark">
            <SettingRow label="LLM Model" description="Used to generate answers from retrieved context" value={status.llm_model} />
            <SettingRow label="Embedding Model" description="Used to embed document chunks and questions" value={status.embedding_model} />
            <SettingRow label="Embedding Dimension" description="Vector size stored in pgvector" value={status.embedding_dimension} />
            <SettingRow label="Chunk Size" description="Max characters per recursive chunk" value={chunkSize} />
            <SettingRow label="Chunk Overlap" description="Overlapping characters between chunks" value={chunkOverlap} />
            <SettingRow label="Top K" description="Chunks retrieved per question" value={topK} />
          </div>
        </div>

        <div className="rounded-xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark">
          <div className="flex items-center gap-2 border-b border-line px-4 py-3 dark:border-line-dark">
            <ServerCog className="h-4 w-4 text-primary dark:text-primary-soft" />
            <h2 className="text-sm font-semibold text-ink dark:text-ink-dark">System Information</h2>
          </div>
          <div className="divide-y divide-line dark:divide-line-dark">
            <SettingRow label="Django Version" value={djangoVersion} />
            <SettingRow label="Total Documents" value={status.total_documents} />
            <SettingRow label="Total Chunks" value={status.total_chunks} />
            <SettingRow label="Total Embeddings" value={status.total_embeddings} />
            <SettingRow label="Total Storage" value={status.total_storage} />
            {health.storage.percent_free !== null && health.storage.percent_free !== undefined ? (
              <SettingRow label="Disk Free Space" description="On the volume backing document storage" value={`${health.storage.percent_free.toFixed(1)}%`} />
            ) : health.storage.backend === 's3' ? (
              <SettingRow label="Document Storage" description="S3-compatible object storage - not disk-usage-tracked here" value="Remote (S3)" />
            ) : (
              <SettingRow label="Disk Free Space" description="On the volume backing document storage" value="Unavailable" />
            )}
            <SettingRow label="Server Uptime" description="Since this process started" value={uptimeDisplay} />
          </div>
        </div>
      </div>

      {canViewSystemLogs && (
        <div className="mt-4 flex items-center justify-between rounded-xl border border-line bg-card p-3.5 shadow-soft dark:border-line-dark dark:bg-card-dark">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary-soft/50 text-primary dark:bg-primary/15 dark:text-primary-soft"><Terminal className="h-4 w-4" /></div>
            <div>
              <p className="text-sm font-semibold text-ink dark:text-ink-dark">System Logs</p>
              <p className="text-xs text-muted dark:text-muted-dark">Full request traces, deduped/grouped errors, and the workspace activity feed above — all in one place.</p>
            </div>
          </div>
          <Link to="/admin/system-logs" className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-line px-3.5 py-2 text-xs font-medium text-ink transition-colors hover:border-primary/30 hover:text-primary dark:border-line-dark dark:text-ink-dark dark:hover:bg-primary/10">
            Open Logs <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>
      )}
    </div>
  );
}
