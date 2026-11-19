'use client';
import { Suspense, useEffect, useState } from 'react';
import dynamic from 'next/dynamic';
import { useRouter, useSearchParams } from 'next/navigation';
import { FolderTree, Network, NotebookPen } from 'lucide-react';
import { Workspace } from '../components/workspace';
import { NoteTree, NoteView } from '../components/notes';
import { FocusPanel } from '../components/focus';
import { GraphNode, ensureNodeNote, noteHref, splitNoteParam } from '../lib/notes';

const VaultGraph = dynamic(() => import('../components/graph'), { ssr: false, loading: () => <div className="skeleton graph-skeleton" /> });
type Tab = 'files' | 'graph' | 'note';

function Home() {
  const params = useSearchParams(), router = useRouter(), raw = params.get('note');
  const [path, heading] = splitNoteParam(raw);
  const [tab, setTab] = useState<Tab>(raw ? 'note' : 'graph'), [focus, setFocus] = useState(false);
  useEffect(() => { if (!raw) { setFocus(false); setTab(t => t === 'note' ? 'graph' : t); } else setTab('note'); }, [raw]);
  const open = (p: string, h?: string | null) => router.push(noteHref(p, h));
  const openNode = async (n: GraphNode) => { const [p, h] = await ensureNodeNote(n); open(p, h); };
  return <Workspace active="Home" bare>
    <div className={`vault-shell ${path ? 'has-note' : ''} ${focus ? 'focus' : ''}`} data-tab={tab}>
      <nav className="vault-tabs" aria-label="Workspace panes">
        <button className={tab === 'files' ? 'on' : ''} onClick={() => setTab('files')}><FolderTree size={14} /> Files</button>
        <button className={tab === 'graph' ? 'on' : ''} onClick={() => setTab('graph')}><Network size={14} /> Graph</button>
        <button className={tab === 'note' ? 'on' : ''} onClick={() => setTab('note')} disabled={!path}><NotebookPen size={14} /> Note</button>
      </nav>
      <aside className="vault-pane vault-files" data-pane="files"><NoteTree active={path} onOpen={(p, h) => { open(p, h); setTab('note'); }} /></aside>
      <section className="vault-pane vault-graph-pane" data-pane="graph"><FocusPanel onOpen={(p, h) => { open(p, h); setTab('note'); }} /><VaultGraph active={raw} onOpen={n => { openNode(n); setTab('note'); }} /></section>
      {path && <section className="vault-pane vault-note" data-pane="note"><NoteView key={path} path={path} heading={heading} onOpen={open} onClose={() => router.push('/')} focus={focus} setFocus={setFocus} /></section>}
    </div>
  </Workspace>;
}

export default function HomePage() { return <Suspense fallback={null}><Home /></Suspense>; }
