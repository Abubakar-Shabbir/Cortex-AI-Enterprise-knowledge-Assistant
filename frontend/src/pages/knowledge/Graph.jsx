import { useEffect, useRef, useState } from 'react';
import { DataSet } from 'vis-data/standalone';
import { Network } from 'vis-network/standalone';
import {
  Crosshair, ExternalLink, FileText, Maximize, Minimize2, Network as NetworkIcon,
  Search, Share2, SlidersHorizontal, Star, Tag, UnfoldVertical, X, ZoomIn, ZoomOut,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import PageHeader from '../../components/PageHeader';
import StatCard from '../../components/StatCard';
import EmptyState from '../../components/EmptyState';
import AppLoader from '../../components/AppLoader';
import Spinner from '../../components/Spinner';
import KnowledgeTabs from '../../layout/KnowledgeTabs';
import { fetchGraphEdgeDetail, useGraphNodeDetail, useKnowledgeGraph } from '../../api/hooks';

const DIMMED_COLOR = { border: '#c9bdbd', background: '#e9e2e2' };
const HIGHLIGHT_EDGE_COLOR = '#8B1E2D';
const IDLE_EDGE_COLOR = 'rgba(109, 102, 101, 0.35)';

// Port of templates/knowledge/graph.html's knowledgeGraphExplorer()
// Alpine component - same vis-network config/behavior, now as a real
// npm dependency (vis-network/vis-data) instead of a CDN <script>.
export default function KnowledgeGraph() {
  const { data, isLoading } = useKnowledgeGraph();

  const containerRef = useRef(null);
  const networkRef = useRef(null);
  const nodesRef = useRef(null);
  const edgesRef = useRef(null);
  const rawNodesRef = useRef([]);
  const rawEdgesRef = useRef([]);

  const [search, setSearch] = useState('');
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [panelOpen, setPanelOpen] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [focusedId, setFocusedId] = useState(null);
  const [entityTypes, setEntityTypes] = useState([]);
  const [relationTypes, setRelationTypes] = useState([]);
  const [activeTypes, setActiveTypes] = useState({});
  const [activeRelations, setActiveRelations] = useState({});
  const [selectedNodeId, setSelectedNodeId] = useState(null);
  const [selectedEdge, setSelectedEdge] = useState(null);
  const [edgeLoading, setEdgeLoading] = useState(false);

  const selectedNode = useGraphNodeDetail(selectedNodeId);

  useEffect(() => {
    if (!data || !containerRef.current) return undefined;
    const { graph_data: graphData, entity_type_colors: colors } = data;

    rawNodesRef.current = graphData.nodes;
    rawEdgesRef.current = graphData.edges;

    const typeCounts = {};
    graphData.nodes.forEach((n) => { typeCounts[n.group] = (typeCounts[n.group] || 0) + 1; });
    const types = Object.keys(typeCounts).sort().map((name) => ({ name, count: typeCounts[name], color: colors[name] || '#8a7d7d' }));
    setEntityTypes(types);
    setActiveTypes(Object.fromEntries(types.map((t) => [t.name, true])));

    const relationCounts = {};
    graphData.edges.forEach((e) => { relationCounts[e.label] = (relationCounts[e.label] || 0) + 1; });
    const relations = Object.keys(relationCounts).sort().map((name) => ({ name, count: relationCounts[name] }));
    setRelationTypes(relations);
    setActiveRelations(Object.fromEntries(relations.map((r) => [r.name, true])));

    const groups = {};
    types.forEach((t) => {
      groups[t.name] = { color: { border: t.color, background: `${t.color}33`, highlight: { border: t.color, background: `${t.color}55` }, hover: { border: t.color, background: `${t.color}44` } } };
    });

    const nodes = new DataSet(graphData.nodes.map((n) => ({ ...n, font: { color: '#8a7d7d', face: 'Inter, ui-sans-serif, system-ui, sans-serif', size: 13 } })));
    const edges = new DataSet(graphData.edges.map((e, idx) => ({
      ...e, id: idx, arrows: { to: { scaleFactor: 0.6 } },
      color: { color: IDLE_EDGE_COLOR, highlight: HIGHLIGHT_EDGE_COLOR, hover: HIGHLIGHT_EDGE_COLOR },
      font: { color: '#8a7d7d', size: 10, strokeWidth: 0, align: 'middle' },
    })));

    nodesRef.current = nodes;
    edgesRef.current = edges;

    const network = new Network(containerRef.current, { nodes, edges }, {
      groups,
      nodes: { shape: 'dot', scaling: { min: 10, max: 36 }, borderWidth: 2, borderWidthSelected: 4, shadow: { enabled: true, color: 'rgba(31,27,27,0.18)', size: 8, x: 0, y: 2 } },
      edges: { smooth: { type: 'continuous', roundness: 0.55 }, width: 1.5, hoverWidth: 0.5, selectionWidth: 1, shadow: { enabled: true, color: 'rgba(31,27,27,0.06)', size: 4, x: 0, y: 1 } },
      physics: { stabilization: { iterations: 120 }, barnesHut: { gravitationalConstant: -6500, springLength: 150 } },
      interaction: { hover: true, tooltipDelay: 150, hideEdgesOnDrag: true },
    });

    network.once('stabilizationIterationsDone', () => network.setOptions({ physics: false }));

    network.on('click', (params) => {
      if (params.nodes.length) {
        setPanelOpen(true);
        setSelectedEdge(null);
        setSelectedNodeId(params.nodes[0]);
      } else if (params.edges.length) {
        const edge = edges.get(params.edges[0]);
        if (edge) {
          setPanelOpen(true);
          setSelectedNodeId(null);
          setEdgeLoading(true);
          setSelectedEdge(null);
          fetchGraphEdgeDetail(edge.from, edge.to)
            .then((detail) => setSelectedEdge(detail))
            .catch(() => setSelectedEdge(null))
            .finally(() => setEdgeLoading(false));
        }
      } else {
        setPanelOpen(false);
        setSelectedNodeId(null);
        setSelectedEdge(null);
      }
    });

    networkRef.current = network;

    return () => {
      network.destroy();
      networkRef.current = null;
    };
  }, [data]);

  const applyFilters = (nextTypes = activeTypes, nextRelations = activeRelations, nextSearch = search) => {
    if (!nodesRef.current) return;
    const query = nextSearch.trim().toLowerCase();

    const hiddenNodeIds = new Set();
    const nodeUpdates = rawNodesRef.current.map((n) => {
      const typeOn = nextTypes[n.group] !== false;
      const matchesSearch = !query || n.label.toLowerCase().includes(query);
      const hidden = !typeOn || !matchesSearch;
      if (hidden) hiddenNodeIds.add(n.id);
      return { id: n.id, hidden };
    });
    nodesRef.current.update(nodeUpdates);

    edgesRef.current.update(rawEdgesRef.current.map((e, idx) => {
      const relOn = nextRelations[e.label] !== false;
      const hidden = !relOn || hiddenNodeIds.has(e.from) || hiddenNodeIds.has(e.to);
      return { id: idx, hidden };
    }));
  };

  const onSearchChange = (value) => {
    setSearch(value);
    applyFilters(activeTypes, activeRelations, value);
  };

  const toggleType = (name) => {
    const next = { ...activeTypes, [name]: !activeTypes[name] };
    setActiveTypes(next);
    applyFilters(next, activeRelations, search);
  };

  const toggleRelation = (name) => {
    const next = { ...activeRelations, [name]: !activeRelations[name] };
    setActiveRelations(next);
    applyFilters(activeTypes, next, search);
  };

  const zoomIn = () => networkRef.current?.moveTo({ scale: networkRef.current.getScale() * 1.25, animation: true });
  const zoomOut = () => networkRef.current?.moveTo({ scale: networkRef.current.getScale() * 0.8, animation: true });
  const fit = () => networkRef.current?.fit({ animation: true });

  const toggleFullscreen = () => {
    setIsFullscreen((v) => !v);
    setTimeout(() => {
      networkRef.current?.redraw();
      networkRef.current?.fit({ animation: true });
    }, 220);
  };

  useEffect(() => {
    const onEscape = (e) => { if (e.key === 'Escape' && isFullscreen) toggleFullscreen(); };
    window.addEventListener('keydown', onEscape);
    return () => window.removeEventListener('keydown', onEscape);
  }, [isFullscreen]);

  const focusNode = (id) => {
    if (!networkRef.current) return;
    setFocusedId(id);
    const connected = new Set(networkRef.current.getConnectedNodes(id));
    connected.add(id);

    nodesRef.current.update(rawNodesRef.current.map((n) => ({ id: n.id, color: connected.has(n.id) ? undefined : DIMMED_COLOR })));
    edgesRef.current.update(rawEdgesRef.current.map((e, idx) => ({
      id: idx,
      color: { color: (connected.has(e.from) && connected.has(e.to)) ? IDLE_EDGE_COLOR : 'rgba(109, 102, 101, 0.08)', highlight: HIGHLIGHT_EDGE_COLOR },
    })));
    networkRef.current.focus(id, { scale: 1.1, animation: true });
  };

  const clearFocus = () => {
    setFocusedId(null);
    nodesRef.current.update(rawNodesRef.current.map((n) => ({ id: n.id, color: undefined })));
    edgesRef.current.update(rawEdgesRef.current.map((e, idx) => ({ id: idx, color: { color: IDLE_EDGE_COLOR, highlight: HIGHLIGHT_EDGE_COLOR } })));
  };

  const expandNode = (id) => {
    const connected = networkRef.current.getConnectedNodes(id);
    nodesRef.current.update(connected.map((nid) => ({ id: nid, hidden: false })));
    edgesRef.current.update(
      rawEdgesRef.current.map((e, idx) => ({ e, idx })).filter(({ e }) => e.from === id || e.to === id).map(({ idx }) => ({ id: idx, hidden: false })),
    );
  };

  const closePanel = () => {
    setPanelOpen(false);
    setSelectedNodeId(null);
    setSelectedEdge(null);
  };

  const insights = data?.insights;

  if (isLoading || !data) return <AppLoader variant="page" />;

  const hasNodes = data.graph_data.nodes.length > 0;

  return (
    <>
      <PageHeader title="Knowledge Graph" subtitle="A visual map of how topics connect across everything you can access. Click a node or connection to explore it in place." />
      <KnowledgeTabs />

      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard icon={Tag} label="Entities" value={insights.total_entities} iconBg="bg-primary/10" iconColor="text-primary dark:text-primary-soft" />
        <StatCard icon={Share2} label="Relationships" value={insights.total_relationships} iconBg="bg-info/10" iconColor="text-info" />
        <StatCard icon={Star} label="Most Mentioned" value={insights.most_mentioned_entity?.display_name || '—'} sublabel={insights.most_mentioned_entity?.mention_count} iconBg="bg-warning/10" iconColor="text-warning" />
        <StatCard icon={NetworkIcon} label="Most Connected" value={insights.most_connected?.entity?.display_name || '—'} sublabel={insights.most_connected?.degree} iconBg="bg-accent/10" iconColor="text-accent" />
      </div>

      {hasNodes ? (
        <div className={isFullscreen ? 'fixed inset-0 z-50 overflow-y-auto rounded-none border border-line bg-card dark:border-line-dark dark:bg-card-dark' : 'rounded-xl border border-line bg-card shadow-soft dark:border-line-dark dark:bg-card-dark'}>
          <div className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2.5 dark:border-line-dark">
            <div className="relative min-w-[180px] flex-1">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted dark:text-muted-dark" />
              <input
                type="text" value={search} onChange={(e) => onSearchChange(e.target.value)} placeholder="Search topics…"
                className="w-full rounded-lg border border-line bg-surface py-1.5 pl-8 pr-3 text-sm text-ink focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/15 dark:border-line-dark dark:bg-white/5 dark:text-ink-dark"
              />
            </div>

            <button type="button" onClick={() => setFiltersOpen((v) => !v)} title="Show/hide entity and relationship type filters"
              className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-medium transition-colors ${filtersOpen ? 'border-primary/30 bg-primary/5 text-primary dark:text-primary-soft' : 'border-line text-ink hover:bg-surface dark:border-line-dark dark:text-ink-dark dark:hover:bg-white/5'}`}>
              <SlidersHorizontal className="h-3.5 w-3.5" /> Filters
            </button>

            <div className="flex items-center gap-0.5 rounded-lg border border-line p-0.5 dark:border-line-dark">
              <button type="button" onClick={zoomOut} title="Zoom out" className="rounded-md p-1.5 text-muted transition-colors hover:bg-surface hover:text-ink dark:text-muted-dark dark:hover:bg-white/5 dark:hover:text-ink-dark"><ZoomOut className="h-4 w-4" /></button>
              <button type="button" onClick={zoomIn} title="Zoom in" className="rounded-md p-1.5 text-muted transition-colors hover:bg-surface hover:text-ink dark:text-muted-dark dark:hover:bg-white/5 dark:hover:text-ink-dark"><ZoomIn className="h-4 w-4" /></button>
              <span className="h-4 w-px bg-line dark:bg-line-dark"></span>
              <button type="button" onClick={fit} title="Fit to view" className="rounded-md p-1.5 text-muted transition-colors hover:bg-surface hover:text-ink dark:text-muted-dark dark:hover:bg-white/5 dark:hover:text-ink-dark"><Maximize className="h-4 w-4" /></button>
              <button type="button" onClick={toggleFullscreen} title={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'} className="rounded-md p-1.5 text-muted transition-colors hover:bg-surface hover:text-ink dark:text-muted-dark dark:hover:bg-white/5 dark:hover:text-ink-dark">
                {isFullscreen ? <Minimize2 className="h-4 w-4" /> : <Maximize className="h-4 w-4" />}
              </button>
            </div>

            {focusedId && (
              <button type="button" onClick={clearFocus} className="inline-flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1.5 text-xs font-medium text-ink hover:bg-surface dark:border-line-dark dark:text-ink-dark dark:hover:bg-white/5">
                <X className="h-3.5 w-3.5" /> Clear focus
              </button>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-line bg-surface/60 px-3 py-1.5 text-xs dark:border-line-dark dark:bg-white/[0.02]">
            {entityTypes.map((type) => (
              <span key={type.name} className="inline-flex items-center gap-1.5 text-muted dark:text-muted-dark">
                <span className="h-2 w-2 rounded-full" style={{ backgroundColor: type.color }}></span>
                <span className="capitalize">{type.name.toLowerCase()}</span>
              </span>
            ))}
          </div>

          {filtersOpen && (
            <div className="border-b border-line px-3 py-3 dark:border-line-dark">
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div>
                  <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted dark:text-muted-dark">Entity types</p>
                  <div className="flex flex-wrap gap-1.5">
                    {entityTypes.map((type) => (
                      <label key={type.name} className={`flex cursor-pointer items-center gap-1.5 rounded-full border border-line px-2.5 py-1 text-xs transition-colors dark:border-line-dark ${activeTypes[type.name] ? 'text-ink dark:text-ink-dark' : 'text-muted opacity-50 dark:text-muted-dark'}`}>
                        <input type="checkbox" checked={activeTypes[type.name] !== false} onChange={() => toggleType(type.name)} className="sr-only" />
                        <span className="h-2 w-2 rounded-full" style={{ backgroundColor: type.color }}></span>
                        <span>{type.name}</span>
                        <span className="text-muted dark:text-muted-dark">({type.count})</span>
                      </label>
                    ))}
                  </div>
                </div>
                <div>
                  <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted dark:text-muted-dark">Relationship types</p>
                  <div className="flex flex-wrap gap-1.5">
                    {relationTypes.map((rel) => (
                      <label key={rel.name} className={`flex cursor-pointer items-center gap-1.5 rounded-full border border-line px-2.5 py-1 text-xs transition-colors dark:border-line-dark ${activeRelations[rel.name] ? 'text-ink dark:text-ink-dark' : 'text-muted opacity-50 dark:text-muted-dark'}`}>
                        <input type="checkbox" checked={activeRelations[rel.name] !== false} onChange={() => toggleRelation(rel.name)} className="sr-only" />
                        <span>{rel.name}</span>
                        <span className="text-muted dark:text-muted-dark">({rel.count})</span>
                      </label>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}

          <div className="flex flex-col lg:flex-row">
            <div className="relative flex-1 p-2">
              <div
                ref={containerRef}
                className={`w-full rounded-lg bg-surface transition-[height] duration-200 dark:bg-white/[0.02] [background-image:radial-gradient(circle,rgba(109,102,101,0.16)_1px,transparent_1px)] [background-size:20px_20px] dark:[background-image:radial-gradient(circle,rgba(169,152,154,0.14)_1px,transparent_1px)] ${isFullscreen ? 'h-[calc(100vh-7.5rem)]' : 'h-[620px]'}`}
              ></div>
            </div>

            {panelOpen && (
              <div className="w-full shrink-0 border-t border-line p-4 dark:border-line-dark lg:w-80 lg:border-l lg:border-t-0">
                <div className="mb-3 flex items-center justify-between">
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-muted dark:text-muted-dark">{selectedEdge ? 'Connection' : 'Topic'}</p>
                  <button type="button" onClick={closePanel} className="rounded-lg p-1 text-muted hover:bg-surface hover:text-ink dark:text-muted-dark dark:hover:bg-white/5 dark:hover:text-ink-dark">
                    <X className="h-4 w-4" />
                  </button>
                </div>

                {(selectedNodeId && selectedNode.isLoading) || edgeLoading ? (
                  <div className="flex items-center gap-2 py-8 text-sm text-muted dark:text-muted-dark">
                    <Spinner size={16} /> Loading…
                  </div>
                ) : selectedNodeId && selectedNode.data ? (
                  <div className="space-y-4">
                    <div className="-mx-4 -mt-4 flex items-center gap-3 rounded-t-lg px-4 py-3.5" style={{ backgroundColor: `${selectedNode.data.color}14` }}>
                      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-sm font-bold text-white shadow-soft" style={{ backgroundColor: selectedNode.data.color }}>
                        {selectedNode.data.display_name.charAt(0).toUpperCase()}
                      </span>
                      <div className="min-w-0">
                        <h3 className="truncate text-sm font-semibold text-ink dark:text-ink-dark">{selectedNode.data.display_name}</h3>
                        <p className="mt-0.5 text-xs text-muted dark:text-muted-dark">
                          {selectedNode.data.entity_type} · {selectedNode.data.mention_count} mentions · {selectedNode.data.document_count} document{selectedNode.data.document_count !== 1 ? 's' : ''}
                        </p>
                      </div>
                    </div>

                    <div className="flex flex-wrap gap-1.5">
                      <button type="button" onClick={() => focusNode(selectedNode.data.id)} className="inline-flex items-center gap-1 rounded-lg border border-line px-2 py-1 text-xs font-medium text-ink hover:bg-surface dark:border-line-dark dark:text-ink-dark dark:hover:bg-white/5">
                        <Crosshair className="h-3 w-3" /> Focus
                      </button>
                      <button type="button" onClick={() => expandNode(selectedNode.data.id)} className="inline-flex items-center gap-1 rounded-lg border border-line px-2 py-1 text-xs font-medium text-ink hover:bg-surface dark:border-line-dark dark:text-ink-dark dark:hover:bg-white/5">
                        <UnfoldVertical className="h-3 w-3" /> Expand
                      </button>
                      <Link to={`/knowledge/entities/${selectedNode.data.id}`} className="inline-flex items-center gap-1 rounded-lg bg-primary/10 px-2 py-1 text-xs font-medium text-primary hover:bg-primary/15 dark:text-primary-soft">
                        <ExternalLink className="h-3 w-3" /> Full page
                      </Link>
                    </div>

                    {selectedNode.data.documents.length > 0 && (
                      <div>
                        <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted dark:text-muted-dark">Connected documents</p>
                        <ul className="space-y-1">
                          {selectedNode.data.documents.map((doc) => (
                            <li key={doc.id} className="flex items-center gap-1.5 truncate text-xs text-ink dark:text-ink-dark"><FileText className="h-3 w-3 shrink-0 text-muted dark:text-muted-dark" /> <span className="truncate">{doc.title}</span></li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {(selectedNode.data.outgoing.length > 0 || selectedNode.data.incoming.length > 0) && (
                      <div>
                        <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted dark:text-muted-dark">Connections</p>
                        <ul className="space-y-1.5">
                          {selectedNode.data.outgoing.map((rel, idx) => (
                            <li key={`out-${idx}`} className="text-xs text-ink dark:text-ink-dark"><span className="text-muted dark:text-muted-dark">{rel.relation_type} →</span> {rel.target}</li>
                          ))}
                          {selectedNode.data.incoming.map((rel, idx) => (
                            <li key={`in-${idx}`} className="text-xs text-ink dark:text-ink-dark">{rel.source} <span className="text-muted dark:text-muted-dark">→ {rel.relation_type}</span></li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                ) : selectedEdge ? (
                  <div className="space-y-4">
                    <div>
                      <h3 className="text-sm font-semibold text-ink dark:text-ink-dark">{selectedEdge.topic_a.display_name} ↔ {selectedEdge.topic_b.display_name}</h3>
                      <p className="mt-0.5 text-xs text-muted dark:text-muted-dark">{selectedEdge.total} supporting connection{selectedEdge.total !== 1 ? 's' : ''}</p>
                    </div>
                    <ul className="space-y-2.5">
                      {selectedEdge.relationships.map((rel, idx) => (
                        <li key={idx} className="rounded-lg border border-line p-2.5 text-xs dark:border-line-dark">
                          <p className="font-medium text-ink dark:text-ink-dark">{rel.source} <span className="text-primary dark:text-primary-soft">— {rel.relation_type} →</span> {rel.target}</p>
                          <p className="mt-1 text-muted dark:text-muted-dark">Confirmed {rel.weight} time{rel.weight !== 1 ? 's' : ''}</p>
                          {rel.context && <p className="mt-1 italic text-muted dark:text-muted-dark">“{rel.context}”</p>}
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </div>
            )}
          </div>

          <p className="border-t border-line px-3 py-2 text-xs text-muted dark:border-line-dark dark:text-muted-dark">
            Showing your {data.graph_data.nodes.length} most-mentioned topics. Node size reflects mention count; color reflects entity type. Drag to rearrange, scroll or use the toolbar to zoom, click a node or connection for detail.
          </p>
        </div>
      ) : (
        <div className="rounded-xl border border-line bg-card p-2 shadow-soft dark:border-line-dark dark:bg-card-dark">
          <EmptyState icon={Share2} title="Nothing to visualize yet" message="Once your documents are processed and entities are extracted, their relationships will appear here as a graph." />
        </div>
      )}
    </>
  );
}
