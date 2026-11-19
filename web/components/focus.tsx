'use client';
import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronRight, Target } from 'lucide-react';
import { FocusItem, GoalProgress, noteHref, notesApi } from '../lib/notes';

type Open = (path: string, heading?: string | null) => void;
const DAY = 86400000;
const days = (iso: string) => Math.round((new Date(`${iso.slice(0, 10)}T00:00:00`).getTime() - new Date(new Date().toDateString()).getTime()) / DAY);
const when = (iso?: string | null) => { if (!iso) return ''; const d = days(iso); return d < 0 ? `${-d}d overdue` : d === 0 ? 'Today' : d === 1 ? 'Tomorrow' : `in ${d}d`; };
const ago = (iso: string) => { const d = -days(iso); return d <= 0 ? 'today' : d === 1 ? 'yesterday' : `${d}d ago`; };
/** Task text without its due marker, with [[Target|alias]] shown as the alias. */
const plain = (t: string) => t.replace(/📅️?\s*\d{4}-\d{2}-\d{2}|\[?due::\s*\d{4}-\d{2}-\d{2}\]?/g, '').replace(/\[\[([^\]|#]*)(?:#([^\]|]*))?(?:\|([^\]]*))?\]\]/g, (_m, a, h, al) => al || (a ? (h ? `${a} › ${h}` : a) : h)).trim();

function useToggle() {
  const qc = useQueryClient();
  return async (i: FocusItem) => {
    if (!i.hash) return;
    await notesApi.toggleTask(i.path, i.hash, i.line, !i.done);
    for (const k of ['focus', 'graph', 'note', 'tasks']) qc.invalidateQueries({ queryKey: [k] });
  };
}

function Row({ item, onOpen }: { item: FocusItem; onOpen: (i: FocusItem) => void }) {
  const toggle = useToggle(), [busy, setBusy] = useState(false);
  const meta = item.kind === 'task' ? `${item.note_title} · ${when(item.due)}` : item.kind === 'deadline' ? `Deadline ${when(item.deadline)}` : item.kind === 'retro' ? `Ended ${ago(item.ended!)}` : item.reason || '';
  return <li className={`focus-item ${item.kind}`}>
    {item.hash ? <input type="checkbox" checked={busy ? !item.done : Boolean(item.done)} disabled={busy} aria-label={`Mark "${plain(item.title)}" done`} onChange={async () => { setBusy(true); try { await toggle(item); } finally { setBusy(false); } }} /> : <i className={`dot ${item.entity || 'note'}`} />}
    <button onClick={() => onOpen(item)}><b>{item.kind === 'task' ? plain(item.title) : item.title}</b><small className={item.kind === 'task' && item.due && days(item.due) < 0 ? 'late' : ''}>{meta}</small></button>
  </li>;
}

/** Goal progress from links to [[Goals#X]]; shared by the home Focus panel and the Today page. */
export function GoalsSection({ onOpen }: { onOpen?: Open }) {
  const q = useQuery({ queryKey: ['focus'], queryFn: notesApi.focus });
  const goals = q.data?.goals || [];
  const summary = (g: GoalProgress) => {
    const opps = Object.values(g.counts.opportunities).reduce((a, b) => a + b, 0), tasks = g.counts.tasks_open + g.counts.tasks_done;
    return [opps && `${opps} ${opps === 1 ? 'opportunity' : 'opportunities'}`, g.counts.people_met && `${g.counts.people_met} met`, tasks && `${g.counts.tasks_done}/${tasks} tasks`, g.last_activity && `active ${ago(g.last_activity)}`].filter(Boolean).join(' · ');
  };
  return <section className="focus-goals">
    <h3><Target size={14} /> Goals <a href={noteHref('Goals.md')} onClick={e => { if (onOpen) { e.preventDefault(); onOpen('Goals.md'); } }}>Edit Goals.md</a></h3>
    {q.isError ? <small className="focus-empty">Could not load goals. Check that the API is running.</small>
      : !goals.length ? <small className="focus-empty">No goals yet. Add a <code>## heading</code> per goal to Goals.md.</small>
        : <ul>{goals.map(g => <li key={g.heading} className={g.flag ? `goal-${g.flag}` : ''}>
          <a href={noteHref('Goals.md', g.heading)} onClick={e => { if (onOpen) { e.preventDefault(); onOpen('Goals.md', g.heading); } }}>{g.heading}</a>
          {g.flag && <span className={`goal-badge goal-${g.flag}`}>{g.flag}</span>}
          <small>{summary(g) || 'Link notes here with [[Goals#' + g.heading + ']]'}</small>
        </li>)}</ul>}
  </section>;
}

const SECTIONS = [['overdue_tasks', 'Overdue'], ['due_soon', 'Due this week'], ['deadlines', 'Deadlines'], ['follow_ups', 'Follow up with'], ['needs_retro', 'Write a retro']] as const;

/** Collapsible "what needs attention" panel above the graph. Every item opens its note; tasks can be checked off here. */
export function FocusPanel({ onOpen }: { onOpen: Open }) {
  const q = useQuery({ queryKey: ['focus'], queryFn: notesApi.focus, refetchInterval: 60000 });
  const [open, setOpen] = useState(() => { try { return localStorage.getItem('omen-focus-open') !== '0'; } catch { return true; } });
  const toggle = () => setOpen(o => { try { localStorage.setItem('omen-focus-open', o ? '0' : '1'); } catch { /* per-viewer convenience only */ } return !o; });
  const go = async (i: FocusItem) => onOpen(i.exists || !i.entity ? i.path : (await notesApi.forEntity(i.entity, i.entity_id!)).path);
  const f = q.data, shown = f ? SECTIONS.filter(([k]) => f[k].length) : [];
  const total = shown.reduce((a, [k]) => a + f![k].length, 0), stale = f?.goals.filter(g => g.flag).length || 0;
  return <section className={`focus-panel ${open ? 'open' : ''}`}>
    <button className="focus-head" onClick={toggle} aria-expanded={open}><ChevronRight size={14} /><b>Focus</b>
      <span>{!f ? (q.isError ? 'unavailable' : 'loading…') : total ? `${total} ${total === 1 ? 'item needs' : 'items need'} attention` : 'Nothing urgent'}{stale ? ` · ${stale} ${stale === 1 ? 'goal needs' : 'goals need'} activity` : ''}</span></button>
    {open && f && <div className="focus-body">
      {shown.map(([k, label]) => <div key={k} className={`focus-section ${k}`}><h3>{label} <span>{f[k].length}</span></h3><ul>{f[k].map(i => <Row key={`${i.kind}:${i.path}:${i.line ?? i.entity_id ?? i.title}`} item={i} onOpen={go} />)}</ul></div>)}
      <GoalsSection onOpen={onOpen} />
    </div>}
  </section>;
}
