'use client';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import ForceGraph2D, { ForceGraphMethods, NodeObject, LinkObject } from 'react-force-graph-2d';
import { GraphLink, GraphNode, notesApi } from '../lib/notes';

type N = NodeObject<GraphNode>;
type L = LinkObject<GraphNode, GraphLink>;
export const NODE_TYPES = ['goal', 'opportunity', 'person', 'org', 'note', 'unresolved'] as const;
const LABELS: Record<string, string> = { goal: 'Goals', opportunity: 'Opportunities', person: 'People', org: 'Orgs', note: 'Notes', unresolved: 'Unresolved' };
const VARS = [...NODE_TYPES, 'link', 'label', 'bg', 'active', 'warn'];
const endId = (v: unknown) => typeof v === 'object' && v ? (v as N).id as string : v as string;

/** Graph colours come from --graph-* CSS variables so light and dark themes both apply. */
function useGraphColors() {
  const [colors, setColors] = useState<Record<string, string>>({});
  useEffect(() => {
    const read = () => { const s = getComputedStyle(document.documentElement); setColors(Object.fromEntries(VARS.map(k => [k, s.getPropertyValue(`--graph-${k}`).trim()]))); };
    read();
    const mq = matchMedia('(prefers-color-scheme: dark)'); mq.addEventListener('change', read);
    const mo = new MutationObserver(read); mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    return () => { mq.removeEventListener('change', read); mo.disconnect(); };
  }, []);
  return colors;
}
const radius = (n: GraphNode) => n.hub ? 9 : n.type === 'goal' ? 6 : n.type === 'opportunity' ? 3 + (n.score || 0) / 20 : n.type === 'person' ? 4 : n.type === 'org' ? 4.5 : 3.2;

export default function VaultGraph({ active, onOpen }: { active?: string | null; onOpen: (n: GraphNode) => void }) {
  const q = useQuery({ queryKey: ['graph'], queryFn: notesApi.graph });
  const colors = useGraphColors();
  const fg = useRef<ForceGraphMethods<N, L>>();
  const wrap = useRef<HTMLDivElement>(null), [size, setSize] = useState({ w: 0, h: 0 });
  const [hidden, setHidden] = useState<Set<string>>(new Set()), [hover, setHover] = useState<string | null>(null);
  const positions = useRef(new Map<string, { x?: number; y?: number }>()), refit = useRef(true);
  useEffect(() => {
    const el = wrap.current; if (!el) return;
    const ro = new ResizeObserver(([e]) => setSize({ w: e.contentRect.width, h: e.contentRect.height })); ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const counts = useMemo(() => (q.data?.nodes || []).reduce<Record<string, number>>((a, n) => ({ ...a, [n.type]: (a[n.type] || 0) + 1 }), {}), [q.data]);
  const data = useMemo(() => {
    const nodes: N[] = (q.data?.nodes || []).filter(n => !hidden.has(n.type)).map(n => ({ ...n, ...positions.current.get(n.id), ...(n.hub ? { fx: 0, fy: 0 } : {}) }));
    const ids = new Set(nodes.map(n => n.id));
    return { nodes, links: (q.data?.links || []).filter(l => ids.has(l.source) && ids.has(l.target)).map(l => ({ ...l })) as L[] };
  }, [q.data, hidden]);
  const neighbours = useMemo(() => {
    const m = new Map<string, Set<string>>();
    for (const l of q.data?.links || []) { for (const [a, b] of [[l.source, l.target], [l.target, l.source]]) { if (!m.has(a)) m.set(a, new Set()); m.get(a)!.add(b); } }
    return m;
  }, [q.data]);
  useEffect(() => {
    const g = fg.current; if (!g) return;
    (g.d3Force('charge') as unknown as { strength: (v: number) => void } | undefined)?.strength(-70);
    (g.d3Force('link') as unknown as { distance: (f: (l: L) => number) => void } | undefined)?.distance(l => l.kind === 'goal' ? 55 : l.kind === 'org' ? 45 : 60);
    let nodes: N[] = [];
    // Goals are pulled hard toward the centre; everything else gets gentle gravity so separate clusters stay in view.
    const gravity = Object.assign((alpha: number) => { for (const n of nodes) if (!n.hub) { const k = (n.type === 'goal' ? 0.2 : 0.035) * alpha; n.vx = (n.vx || 0) - (n.x || 0) * k; n.vy = (n.vy || 0) - (n.y || 0) * k; } }, { initialize: (ns: N[]) => { nodes = ns; } });
    g.d3Force('gravity', gravity);
    g.d3ReheatSimulation();
  }, [data, size.w > 0]);
  useEffect(() => { refit.current = true; const t = setTimeout(() => fg.current?.zoomToFit(300, 60), 150); return () => clearTimeout(t); }, [size.w, size.h, data]);
  const lit = (id: string) => !hover || id === hover || neighbours.get(hover)?.has(id);
  const toggle = (t: string) => setHidden(h => { const n = new Set(h); n.has(t) ? n.delete(t) : n.add(t); return n; });
  return <div className="vault-graph">
    <div className="graph-chips">{NODE_TYPES.filter(t => counts[t]).map(t => <button key={t} className={hidden.has(t) ? 'off' : ''} onClick={() => toggle(t)}><i style={{ background: colors[t] }} />{LABELS[t]} <span>{counts[t]}</span></button>)}</div>
    <div className="graph-canvas" ref={wrap}>
      {q.isError ? <div className="empty"><b>Could not load the graph</b><span>Check that the API is running.</span></div>
        : q.data && !q.data.nodes.length ? <div className="empty"><b>Your vault is empty</b><span>Add <code>## goals</code> to Goals.md, or save an opportunity to see it here.</span></div>
          : size.w > 0 && <ForceGraph2D<GraphNode, GraphLink> ref={fg} graphData={data} width={size.w} height={size.h} backgroundColor={colors.bg || undefined}
            nodeRelSize={1} nodeVal={n => radius(n) ** 2} nodeLabel={n => `${n.label} · ${n.type}${n.flag ? ` (${n.flag})` : ''}${n.warn ? ' · needs attention' : ''}`}
            nodeCanvasObject={(n, ctx, scale) => {
              const r = radius(n), x = n.x || 0, y = n.y || 0, color = colors[n.type] || '#888';
              ctx.globalAlpha = lit(n.id) ? (n.type === 'unresolved' ? 0.6 : n.flag ? 0.35 : 1) : 0.12;  // stale/empty goals are drawn faded
              ctx.beginPath(); ctx.arc(x, y, r, 0, 2 * Math.PI);
              if (n.type === 'unresolved') { ctx.setLineDash([1.5, 1.5]); ctx.strokeStyle = color; ctx.lineWidth = 0.8; ctx.stroke(); ctx.setLineDash([]); }
              else { ctx.fillStyle = color; ctx.fill(); }
              if (n.warn) { ctx.strokeStyle = colors.warn || '#dc2626'; ctx.lineWidth = 1.2; ctx.setLineDash([]); ctx.beginPath(); ctx.arc(x, y, r + 1.8, 0, 2 * Math.PI); ctx.stroke(); }
              if (active && n.path === active.split('#')[0] && (!n.heading || active.endsWith(`#${n.heading}`))) { ctx.strokeStyle = colors.active || color; ctx.lineWidth = 1.5; ctx.beginPath(); ctx.arc(x, y, r + 2.5, 0, 2 * Math.PI); ctx.stroke(); }
              if (n.type === 'goal' || data.nodes.length <= 80 || scale > 1.6 || n.id === hover || (hover && lit(n.id))) {
                ctx.font = `${n.type === 'goal' ? 600 : 400} ${Math.max(10 / scale, 2.5)}px system-ui, sans-serif`; ctx.textAlign = 'center'; ctx.textBaseline = 'top'; ctx.fillStyle = colors.label || '#333';
                const label = n.label.length > 42 ? `${n.label.slice(0, 40)}…` : n.label; ctx.fillText(label, x, y + r + 1.5);
              }
              ctx.globalAlpha = 1;
            }}
            linkColor={l => colors[(l as GraphLink).kind === 'goal' ? 'goal' : 'link'] || '#ccc'}
            linkVisibility={l => !hover || endId(l.source) === hover || endId(l.target) === hover}
            linkWidth={l => hover && (endId(l.source) === hover || endId(l.target) === hover) ? 1.4 : 0.6}
            linkLineDash={l => l.unresolved ? [2, 2] : null}
            onNodeHover={n => setHover(n ? n.id as string : null)}
            onNodeClick={n => onOpen(n)}
            onEngineTick={() => { for (const n of data.nodes) positions.current.set(n.id as string, { x: n.x, y: n.y }); }}
            onEngineStop={() => { if (refit.current) { refit.current = false; fg.current?.zoomToFit(400, 60); } }}
            cooldownTicks={120} />}
    </div>
  </div>;
}
