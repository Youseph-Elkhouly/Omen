'use client';
import { useMemo, ReactNode } from 'react';
import ReactMarkdown, { defaultUrlTransform } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Note } from '../lib/notes';

type MdNode = { type: string; value?: string; url?: string; children?: MdNode[]; data?: Record<string, unknown> };
const LINK = /\[\[([^[\]\n]*?)\]\]/g;
/** remark plugin: `[[Target#Heading|alias]]` in text -> link nodes with a `wikilink:` URL (code is left alone). */
function remarkWikilinks() {
  const walk = (node: MdNode) => {
    if (!node.children) return;
    node.children = node.children.flatMap((c): MdNode[] => {
      if (c.type !== 'text' || !c.value?.includes('[[')) { if (!['code', 'inlineCode', 'link'].includes(c.type)) walk(c); return [c]; }
      const out: MdNode[] = []; let last = 0;
      for (const m of c.value.matchAll(LINK)) {
        if (m.index! > last) out.push({ type: 'text', value: c.value.slice(last, m.index) });
        const [target, alias] = m[1].split('|');
        out.push({ type: 'link', url: `wikilink:${encodeURIComponent(m[1])}`, children: [{ type: 'text', value: (alias || target.replace(/^#/, '')).trim() }] });
        last = m.index! + m[0].length;
      }
      if (last < c.value.length) out.push({ type: 'text', value: c.value.slice(last) });
      return out;
    });
  };
  return (tree: MdNode) => walk(tree);
}
const text = (n: unknown): string => typeof n === 'string' ? n : Array.isArray(n) ? n.map(text).join('') : n && typeof n === 'object' && 'props' in n ? text((n as { props: { children?: ReactNode } }).props.children) : '';

/** Rendered note. Wikilinks resolve through `note.resolved`; unresolved ones are styled and create the note on click. */
export function NotePreview({ note, onLink }: { note: Pick<Note, 'body' | 'resolved'>; onLink: (target: string, heading: string | null, path: string | null) => void }) {
  const components = useMemo(() => {
    const heading = (Tag: 'h1' | 'h2' | 'h3' | 'h4') => function H({ children }: { children?: ReactNode }) { return <Tag data-heading={text(children)}>{children}</Tag>; };
    return {
      h1: heading('h1'), h2: heading('h2'), h3: heading('h3'), h4: heading('h4'),
      a: ({ href, children }: { href?: string; children?: ReactNode }) => {
        if (!href?.startsWith('wikilink:')) return <a href={href} target="_blank" rel="noreferrer">{children}</a>;
        const [raw] = decodeURIComponent(href.slice(9)).split('|'), i = raw.indexOf('#');
        const target = (i < 0 ? raw : raw.slice(0, i)).trim(), heading = i < 0 ? null : raw.slice(i + 1).trim() || null;
        const path = target ? note.resolved[target] ?? null : '';
        return <a href="#" className={`wikilink ${path === null ? 'unresolved' : ''}`} title={path === null ? `Create "${target}"` : path || heading || ''} onClick={e => { e.preventDefault(); onLink(target, heading, path || null); }}>{children}</a>;
      },
    };
  }, [note.resolved, onLink]);
  return <div className="note-preview"><ReactMarkdown remarkPlugins={[remarkGfm, remarkWikilinks]} urlTransform={url => url.startsWith('wikilink:') ? url : defaultUrlTransform(url)} components={components}>{note.body}</ReactMarkdown></div>;
}
