import { apiUrl } from './api';

export type NoteType = 'goal' | 'person' | 'opportunity' | 'org' | 'note';
export type Backlink = { path: string; title: string; snippet: string };
export type Note = { path: string; title: string; type: NoteType; frontmatter: Record<string, unknown>; body: string; backlinks: Backlink[]; resolved: Record<string, string | null> };
export type TreeItem = { name: string; path: string; type: 'folder' | 'note'; title?: string; note_type?: NoteType; children?: TreeItem[] };
export type SearchHit = { path: string; title: string; type: NoteType; link: string; snippet: string };
export type GraphNode = { id: string; label: string; type: NoteType | 'unresolved'; path: string | null; score?: number; stage?: string; state?: string; entity?: 'opportunity' | 'person' | 'org'; entity_id?: number | string; heading?: string; hub?: boolean; flag?: 'stale' | 'empty'; warn?: boolean };
export type GraphLink = { source: string; target: string; kind: 'wikilink' | 'attended' | 'org' | 'goal'; unresolved?: boolean };
export type Graph = { nodes: GraphNode[]; links: GraphLink[] };
export type FocusItem = { kind: 'task' | 'deadline' | 'retro' | 'follow_up'; title: string; path: string; exists: boolean; entity?: 'opportunity' | 'person'; entity_id?: number; note_title?: string; line?: number; hash?: string; due?: string | null; done?: boolean; deadline?: string; ended?: string; reason?: string; event?: string | null };
export type GoalProgress = { heading: string; path: string; counts: { opportunities: Record<string, number>; people_met: number; tasks_open: number; tasks_done: number; notes: number }; last_activity: string | null; flag: 'stale' | 'empty' | null };
export type Focus = { overdue_tasks: FocusItem[]; due_soon: FocusItem[]; deadlines: FocusItem[]; needs_retro: FocusItem[]; follow_ups: FocusItem[]; goals: GoalProgress[] };

async function json<T>(r: Response): Promise<T> {
  if (!r.ok) throw Object.assign(new Error((await r.text()) || r.statusText), { status: r.status });
  return r.json();
}
const withPath = (route: string, path: string) => `${apiUrl(route)}?path=${encodeURIComponent(path)}`;

export const notesApi = {
  tree: () => fetch(apiUrl('/notes/tree')).then(json<TreeItem>),
  get: (path: string) => fetch(withPath('/notes', path)).then(json<Note>),
  save: (path: string, body: string, frontmatter?: Record<string, unknown>) =>
    fetch(withPath('/notes', path), { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ body, frontmatter }) }).then(json<Note>),
  forEntity: (entity: string, id: string | number) => fetch(apiUrl(`/notes/for/${entity}/${encodeURIComponent(String(id))}`)).then(json<Note>),
  search: (q: string) => fetch(`${apiUrl('/notes/search')}?q=${encodeURIComponent(q)}`).then(json<SearchHit[]>),
  rename: (from: string, to: string) => fetch(apiUrl('/notes/rename'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ from, to }) }).then(json<Note>),
  graph: () => fetch(apiUrl('/graph')).then(json<Graph>),
  focus: () => fetch(apiUrl('/focus')).then(json<Focus>),
  toggleTask: (path: string, hash: string, line?: number, done?: boolean) =>
    fetch(apiUrl('/tasks'), { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path, hash, line, done }) }).then(json<{ done: boolean }>),
};

/** In-app URL for a note; the heading travels inside the query value (`Goals.md#Ship Omen`). */
export const noteHref = (path: string, heading?: string | null) => `/?note=${encodeURIComponent(heading ? `${path}#${heading}` : path)}`;
export const splitNoteParam = (raw: string | null): [string | null, string | null] => {
  if (!raw) return [null, null];
  const i = raw.indexOf('#');
  return i < 0 ? [raw, null] : [raw.slice(0, i), raw.slice(i + 1) || null];
};
/** `[[Target]]` text -> the path Obsidian would create for it. */
export const linkPath = (target: string) => {
  const t = target.trim().replace(/\\/g, '/').replace(/^\/+/, '');
  return /\.md$/i.test(t) ? t : `${t}.md`;
};
/** User-typed note name -> safe vault path (folders allowed with "/"). */
export const notePath = (name: string) => linkPath(name.split('/').map(p => p.replace(/[\\:*?"<>|#^[\]]/g, ' ').replace(/\s+/g, ' ').trim()).filter(p => p && !p.startsWith('.')).join('/'));
export const noteName = (path: string) => path.split('/').pop()!.replace(/\.md$/i, '');

/** Note path for a graph node, creating the entity stub or unresolved note when needed. */
export async function ensureNodeNote(n: GraphNode): Promise<[string, string | null]> {
  if (n.type !== 'unresolved' && n.path) return [n.path, n.heading ?? null];
  if (n.entity && n.entity_id !== undefined) return [(await notesApi.forEntity(n.entity, n.entity_id)).path, null];
  const path = linkPath(n.path || n.label);
  await notesApi.save(path, `# ${noteName(path)}\n`);
  return [path, null];
}
