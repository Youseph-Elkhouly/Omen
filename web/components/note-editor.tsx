'use client';
import { useEffect, useRef, useState } from 'react';
import CodeMirror from '@uiw/react-codemirror';
import { markdown, markdownLanguage } from '@codemirror/lang-markdown';
import { autocompletion, CompletionContext, Completion } from '@codemirror/autocomplete';
import { EditorView } from '@codemirror/view';
import { Note, notesApi } from '../lib/notes';
import { SaveBadge, SaveState } from './system';

/** `[[` autocomplete from /notes/search; inserts a plain `[[Title]]` link (the path only when the name is ambiguous). */
const wikiCompletion = autocompletion({
  override: [async (ctx: CompletionContext) => {
    const m = ctx.matchBefore(/\[\[[^\][\n|#]*$/);
    if (!m) return null;
    const hits = await notesApi.search(m.text.slice(2)).catch(() => []);
    return {
      from: m.from + 2, validFor: /^[^\][\n|#]*$/,
      options: hits.map((h): Completion => ({
        label: h.title, detail: h.link === h.title ? undefined : h.link, type: 'text',
        apply: (view, _c, from, to) => {
          const closed = view.state.sliceDoc(to, to + 2) === ']]', text = h.link;
          view.dispatch({ changes: { from, to: closed ? to + 2 : to, insert: `${text}]]` }, selection: { anchor: from + text.length + 2 } });
        },
      })),
    };
  }],
});
const extensions = [markdown({ base: markdownLanguage }), wikiCompletion, EditorView.lineWrapping];

/** Markdown editor with debounced (800 ms) autosave; pending edits are flushed when it unmounts. */
export function NoteEditor({ path, initial, compact = false, onSaved, onState }: { path: string; initial: string; compact?: boolean; onSaved?: (n: Note) => void; onState?: (s: SaveState) => void }) {
  const [text, setText] = useState(initial), [state, setState] = useState<SaveState>('saved');
  const latest = useRef(initial), timer = useRef<ReturnType<typeof setTimeout> | null>(null), saved = useRef(onSaved);
  saved.current = onSaved;
  const mark = (s: SaveState) => { setState(s); onState?.(s); };
  const flush = async () => {
    timer.current = null; mark('saving');
    const sent = latest.current;
    try { const n = await notesApi.save(path, sent); mark(latest.current === sent ? 'saved' : 'unsaved'); saved.current?.(n); } catch { mark('error'); }
  };
  useEffect(() => () => { if (timer.current) { clearTimeout(timer.current); notesApi.save(path, latest.current).then(n => saved.current?.(n), () => undefined); } }, [path]);
  const change = (v: string) => { setText(v); latest.current = v; mark('unsaved'); if (timer.current) clearTimeout(timer.current); timer.current = setTimeout(flush, 800); };
  return <div className={`note-editor ${compact ? 'compact' : ''}`}>
    <CodeMirror value={text} onChange={change} extensions={extensions} basicSetup={{ lineNumbers: false, foldGutter: false, highlightActiveLine: false, highlightActiveLineGutter: false }} placeholder="Write in Markdown. Type [[ to link a note." minHeight={compact ? '160px' : '320px'} maxHeight={compact ? '320px' : undefined} />
    {compact && <SaveBadge state={state} />}
  </div>;
}
