'use client';
import { useEffect, useMemo, useState } from 'react';
import dynamic from 'next/dynamic';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowUpRight, ChevronRight, Edit3, Eye, FilePlus2, Maximize2, Minimize2, Search, Target, X } from 'lucide-react';
import { DeadlineBadge, SaveBadge, SaveState, ScoreRing } from './system';
import { Opportunity, inAppBrowser, updateOpportunity } from './workspace';
import { Note, TreeItem, linkPath, notePath, notesApi } from '../lib/notes';
import { apiUrl } from '../lib/api';

// CodeMirror and react-markdown load only once a note is opened (the editor only in Edit mode).
const NoteEditor = dynamic(() => import('./note-editor').then(m => m.NoteEditor), { ssr: false, loading: () => <div className="skeleton note-skeleton" /> });
const NotePreview = dynamic(() => import('./note-preview').then(m => m.NotePreview), { ssr: false, loading: () => <div className="skeleton note-skeleton" /> });
const STAGES = ['saved', 'applied', 'going', 'attended', 'skipped'];
type Person = { id: number; name: string; role: string; organization: string; state: string; next_event?: string | null };
type Open = (path: string, heading?: string | null) => void;

function Folder({ item, active, onOpen, open: initial = false }: { item: TreeItem; active?: string | null; onOpen: Open; open?: boolean }) {
  const [open, setOpen] = useState(initial || Boolean(active?.startsWith(`${item.path}/`)));
  return <div className="tree-folder">
    <button className={`tree-row folder ${open ? 'open' : ''}`} onClick={() => setOpen(o => !o)}><ChevronRight size={13} />{item.name}<span>{count(item)}</span></button>
    {open && <div className="tree-children">{item.children?.length ? item.children.map(c => <Item key={c.path} item={c} active={active} onOpen={onOpen} />) : <small className="tree-empty">No notes yet</small>}</div>}
  </div>;
}
const count = (i: TreeItem): number => (i.children || []).reduce((a, c) => a + (c.type === 'note' ? 1 : count(c)), 0);
function Item({ item, active, onOpen }: { item: TreeItem; active?: string | null; onOpen: Open }) {
  return item.type === 'folder' ? <Folder item={item} active={active} onOpen={onOpen} />
    : <button className={`tree-row note ${item.path === active ? 'active' : ''}`} onClick={() => onOpen(item.path)} title={item.path}><i className={`dot ${item.note_type}`} />{item.title || item.name}</button>;
}

/** Left pane: Goals pinned, then People, Opportunities, Orgs and everything else; search and "New note". */
export function NoteTree({ active, onOpen }: { active?: string | null; onOpen: Open }) {
  const tree = useQuery({ queryKey: ['tree'], queryFn: notesApi.tree });
  const [q, setQ] = useState(''), [term, setTerm] = useState('');
  useEffect(() => { const t = setTimeout(() => setTerm(q.trim()), 200); return () => clearTimeout(t); }, [q]);
  const hits = useQuery({ queryKey: ['note-search', term], queryFn: () => notesApi.search(term), enabled: Boolean(term) });
  const qc = useQueryClient();
  const sections = useMemo(() => {
    const kids = tree.data?.children || [], pick = (n: string) => kids.find(k => k.type === 'folder' && k.name === n);
    return { goals: kids.find(k => k.path === 'Goals.md'), folders: ['People', 'Opportunities', 'Orgs'].map(pick).filter(Boolean) as TreeItem[], other: kids.filter(k => k.path !== 'Goals.md' && !(k.type === 'folder' && ['People', 'Opportunities', 'Orgs'].includes(k.name))) };
  }, [tree.data]);
  async function create() {
    const name = window.prompt('New note name (use / for folders)');
    if (!name?.trim()) return;
    const path = notePath(name);
    try { await notesApi.get(path); } catch { await notesApi.save(path, `# ${path.split('/').pop()!.slice(0, -3)}\n`); }
    qc.invalidateQueries({ queryKey: ['tree'] }); qc.invalidateQueries({ queryKey: ['graph'] }); onOpen(path);
  }
  return <div className="note-tree">
    <div className="tree-tools"><label className="tree-search"><Search size={13} /><input value={q} onChange={e => setQ(e.target.value)} placeholder="Search notes" /></label><button onClick={create} title="New note"><FilePlus2 size={15} /></button></div>
    {term ? <div className="tree-results">{(hits.data || []).map(h => <button key={h.path} className={`tree-row result ${h.path === active ? 'active' : ''}`} onClick={() => onOpen(h.path)}><b><i className={`dot ${h.type}`} />{h.title}</b>{h.snippet && <small>{h.snippet}</small>}</button>)}{hits.data && !hits.data.length && <small className="tree-empty">No matches</small>}</div>
      : tree.isError ? <small className="tree-empty">Could not load notes. Check that the API is running.</small>
        : <>
          {sections.goals && <button className={`tree-row pinned ${active === 'Goals.md' ? 'active' : ''}`} onClick={() => onOpen('Goals.md')}><Target size={14} />Goals</button>}
          {sections.folders.map(f => <Folder key={f.path} item={f} active={active} onOpen={onOpen} />)}
          {sections.other.length > 0 && <div className="tree-other"><small>Other notes</small>{sections.other.map(i => <Item key={i.path} item={i} active={active} onOpen={onOpen} />)}</div>}
        </>}
  </div>;
}

/** Live DB data for an opportunity or person note, with the stage/state controls. */
function EntityHeader({ note, onChanged }: { note: Note; onChanged: () => void }) {
  const id = Number(note.frontmatter.omen_id), isOpp = note.type === 'opportunity';
  const opp = useQuery({ queryKey: ['opportunity', id], enabled: isOpp && id > 0, queryFn: async () => { const r = await fetch(apiUrl(`/opportunities/${id}`)); if (!r.ok) throw new Error('Not found'); return r.json() as Promise<Opportunity>; } });
  const people = useQuery({ queryKey: ['people'], enabled: !isOpp && id > 0, queryFn: async () => { const r = await fetch(apiUrl('/people')); return r.json() as Promise<Person[]>; } });
  const qc = useQueryClient();
  if (isOpp && opp.data) {
    const o = opp.data, when = o.starts_at ? new Date(o.starts_at).toLocaleString('en-CA', { weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }) : 'Date TBD';
    const stage = async (s: string) => { await updateOpportunity(o.id, { stage: s }); qc.invalidateQueries({ queryKey: ['opportunity', id] }); qc.invalidateQueries({ queryKey: ['graph'] }); qc.invalidateQueries({ queryKey: ['focus'] }); onChanged(); };
    return <div className="entity-card"><ScoreRing score={o.score || 0} /><div><span className="entity-kind">{o.type} · {o.org || 'Organizer TBA'}</span><b>{when}{o.location ? ` · ${o.location}` : ''}</b>{o.deadline && <DeadlineBadge date={o.deadline} />}</div>
      <select value={o.stage || 'saved'} onChange={e => stage(e.target.value)} aria-label="Stage">{STAGES.map(s => <option key={s} value={s}>{s}</option>)}</select>
      <a href={inAppBrowser(o.url)}>Event page <ArrowUpRight size={13} /></a></div>;
  }
  const p = people.data?.find(x => x.id === id);
  if (!isOpp && p) {
    const toggle = async () => { await fetch(apiUrl(`/people/${p.id}`), { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ state: p.state === 'met' ? 'want_to_meet' : 'met' }) }); qc.invalidateQueries({ queryKey: ['people'] }); qc.invalidateQueries({ queryKey: ['graph'] }); onChanged(); };
    return <div className="entity-card"><div className="person-avatar">{p.name.split(' ').map(x => x[0]).join('').slice(0, 2)}</div><div><span className="entity-kind">{p.role || 'Person'}{p.organization ? ` · ${p.organization}` : ''}</span><b>{p.next_event || 'No linked event'}</b></div><button onClick={toggle}>{p.state === 'met' ? 'Met' : 'Want to meet'}</button></div>;
  }
  return null;
}

const show = (v: unknown) => Array.isArray(v) ? v.join(', ') : v && typeof v === 'object' ? JSON.stringify(v) : String(v ?? '');

/** Centre/right pane: header card, properties, Edit/Preview, backlinks. */
export function NoteView({ path, heading, onOpen, onClose, focus, setFocus }: { path: string; heading?: string | null; onOpen: Open; onClose: () => void; focus: boolean; setFocus: (v: boolean) => void }) {
  const qc = useQueryClient();
  const note = useQuery({ queryKey: ['note', path], queryFn: () => notesApi.get(path), retry: (n, e) => (e as { status?: number }).status !== 404 && n < 2 });
  const [mode, setMode] = useState<'edit' | 'preview'>(() => { try { return (localStorage.getItem('omen-note-mode') as 'edit' | 'preview') || 'preview'; } catch { return 'preview'; } });
  const [state, setState] = useState<SaveState>('saved');
  const pick = (m: 'edit' | 'preview') => { setMode(m); try { localStorage.setItem('omen-note-mode', m); } catch { /* per-viewer convenience only */ } };
  const refresh = () => { qc.invalidateQueries({ queryKey: ['note', path] }); };
  const saved = (n: Note) => { qc.setQueryData<Note>(['note', path], n); qc.invalidateQueries({ queryKey: ['graph'] }); qc.invalidateQueries({ queryKey: ['tree'] }); };
  useEffect(() => { if (!heading || mode !== 'preview' || !note.data) return; const el = document.querySelector(`.note-view [data-heading="${CSS.escape(heading)}"]`); el?.scrollIntoView({ block: 'start', behavior: 'smooth' }); }, [heading, mode, note.data]);
  const link = async (target: string, h: string | null, resolved: string | null) => {
    if (!target) return h && document.querySelector(`.note-view [data-heading="${CSS.escape(h)}"]`)?.scrollIntoView({ behavior: 'smooth' });
    if (resolved) return onOpen(resolved, h);
    const created = linkPath(target);
    await notesApi.save(created, `# ${created.split('/').pop()!.slice(0, -3)}\n`);
    qc.invalidateQueries({ queryKey: ['tree'] }); qc.invalidateQueries({ queryKey: ['graph'] }); qc.invalidateQueries({ queryKey: ['note', path] });
    onOpen(created);
  };
  const missing = (note.error as { status?: number } | null)?.status === 404;
  const props = Object.entries(note.data?.frontmatter || {}).filter(([k]) => !['omen_type', 'omen_id'].includes(k));
  return <article className="note-view">
    <header className="note-head">
      <div className="note-crumb" title={path}>{path.replace(/\.md$/, '').split('/').join(' / ')}</div>
      <div className="note-actions">
        {note.data && <><div className="mode-toggle"><button className={mode === 'edit' ? 'on' : ''} onClick={() => pick('edit')}><Edit3 size={13} /> Edit</button><button className={mode === 'preview' ? 'on' : ''} onClick={() => pick('preview')}><Eye size={13} /> Preview</button></div><SaveBadge state={state} /></>}
        <button className="icon" onClick={() => setFocus(!focus)} title={focus ? 'Show graph' : 'Focus note'}>{focus ? <Minimize2 size={14} /> : <Maximize2 size={14} />}</button>
        <button className="icon" onClick={onClose} title="Close note"><X size={15} /></button>
      </div>
    </header>
    {note.isLoading ? <div className="skeleton note-skeleton" />
      : missing ? <div className="empty"><b>This note doesn&apos;t exist yet</b><button className="create-note" onClick={() => link(path, null, null)}>Create {path.split('/').pop()}</button></div>
        : note.isError || !note.data ? <div className="empty"><b>Could not load this note</b><span>Check that the API is running.</span></div>
          : <>
            {(note.data.type === 'opportunity' || note.data.type === 'person') && <EntityHeader note={note.data} onChanged={refresh} />}
            {props.length > 0 && <dl className="note-props">{props.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{show(v)}</dd></div>)}</dl>}
            {mode === 'edit' ? <NoteEditor key={path} path={path} initial={note.data.body} onSaved={saved} onState={setState} /> : <NotePreview note={note.data} onLink={link} />}
            <section className="backlinks"><h3>Backlinks <span>{note.data.backlinks.length}</span></h3>
              {note.data.backlinks.length ? note.data.backlinks.map(b => <button key={b.path} onClick={() => onOpen(b.path)}><b>{b.title}</b><small>{b.snippet}</small></button>) : <small className="tree-empty">No other note links here yet.</small>}
            </section>
          </>}
  </article>;
}
