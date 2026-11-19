"""Markdown vault behind the notes workspace: notes, [[wikilinks]], backlinks and graph data.

The vault is a plain folder of .md files (OMEN_VAULT_PATH, default ./vault) that also opens in desktop Obsidian.
Opportunity and person notes are created lazily; their "## Notes" section is mirrored into the DB `notes` column.
"""
import hashlib, itertools, os, re, threading, unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
import yaml
from .db import ROOT, connect

FM_RE=re.compile(r'\A---[ \t]*\r?\n(.*?)^(?:---|\.\.\.)[ \t]*(?:\r?\n|\Z)',re.S|re.M)
LINK_RE=re.compile(r'\[\[([^\[\]\n]*?)\]\]')
CODE_RE=re.compile(r'```.*?(?:```|\Z)|~~~.*?(?:~~~|\Z)|`[^`\n]*`',re.S)
KEY_RE=re.compile(r'^([A-Za-z_][\w-]*)[ \t]*:(?=\s|$)')
H1_RE=re.compile(r'^# +(.+?)[ \t]*$',re.M)
H2_RE=re.compile(r'^## +(.+?)[ \t#]*$',re.M)
TASK_RE=re.compile(r'^([ \t]*)(?:[-*+]|\d+[.)])[ \t]+\[([ xX])\][ \t]+(.*?)[ \t]*\r?$')
DUE_RE=re.compile(r'(?:📅\ufe0f?[ \t]*|\bdue::[ \t]*)(\d{4}-\d{2}-\d{2})')
FENCE_RE=re.compile(r'^[ \t]*(```|~~~)')
HEAD_RE=re.compile(r'^(#{1,6}) +(.+?)[ \t#]*\r?$')
BAD_NAME=re.compile(r'[\\:*?"<>|#^\[\]]')
TYPES={'goal','person','opportunity','org','note'}
FOLDERS={'opportunity':'Opportunities','person':'People','org':'Orgs'}
TABLES={'opportunity':'opportunities','person':'people'}
INCLUDE={'goal':'goals','person':'people','org':'orgs','opportunity':'opportunities','note':'notes'}
GOALS_TEMPLATE='---\nomen_type: goal\n---\n# Goals\n\nEach `## heading` below is one goal. Omen ranks opportunities against this file, and any note can link to a goal with [[Goals#Heading]].\n'
lock=threading.RLock()
_cache={}  # (vault root, path) -> ((mtime_ns, size), parsed note)
_migrated=set()  # vault roots already checked for old '<title> <hash>.md' stub names
HASHED=re.compile(r'^(.*) [0-9a-f]{6,64}$')

class _Dumper(yaml.SafeDumper): pass
_Dumper.add_representer(type(None),lambda d,_:d.represent_scalar('tag:yaml.org,2002:null',''))
_Dumper.add_representer(datetime,lambda d,v:d.represent_scalar('tag:yaml.org,2002:timestamp',v.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')))
def _dump(data): return yaml.dump(data,Dumper=_Dumper,sort_keys=False,allow_unicode=True,default_flow_style=False,width=10**9) if data else ''

def root(): return Path(os.getenv('OMEN_VAULT_PATH') or ROOT/'vault').expanduser().resolve()

def ensure():
    """Create the vault layout; seed Goals.md from profile/goals.md on first run."""
    r=root()
    for d in ('',*FOLDERS.values()): (r/d).mkdir(parents=True,exist_ok=True)
    if not (r/'Goals.md').exists():
        src=ROOT/'opportunity_engine/profile/goals.md'; text=src.read_text(encoding='utf-8') if src.exists() else ''
        _atomic(r/'Goals.md',text if text.strip() else GOALS_TEMPLATE)
    return r

def goals_path():
    """Goals.md in the vault is the single source of truth for goals."""
    try: return ensure()/'Goals.md'
    except OSError: return ROOT/'opportunity_engine/profile/goals.md'

def goals():
    p=goals_path(); return [m.group(1).strip() for m in H2_RE.finditer(split(p.read_text(encoding='utf-8'))[1])] if p.exists() else []

def safe(rel):
    """(normalised path, absolute path) for a .md note inside the vault; anything else raises ValueError."""
    rel=(rel or '').strip().replace('\\','/'); parts=rel.split('/')
    if not rel.endswith('.md') or rel.startswith('/') or re.match(r'^[A-Za-z]:',rel) or any(not p or p in ('.','..') or p.startswith('.') or BAD_NAME.search(p) for p in parts):
        raise ValueError(f'Invalid note path: {rel!r}')
    r=root(); p=(r/rel).resolve()
    if p==r or not p.is_relative_to(r): raise ValueError(f'Note path escapes the vault: {rel!r}')
    return rel,p

def _atomic(p,text):
    p.parent.mkdir(parents=True,exist_ok=True); tmp=p.with_name(f'.{p.name}.omen-tmp')
    with open(tmp,'w',encoding='utf-8',newline='') as f: f.write(text); f.flush(); os.fsync(f.fileno())
    os.replace(tmp,p)

def split(text):
    m=FM_RE.match(text)
    return (m.group(1),text[m.end():]) if m else (None,text)

def frontmatter(fm):
    try: d=yaml.safe_load(fm) if fm else {}
    except yaml.YAMLError: return {}
    return d if isinstance(d,dict) else {}

def set_keys(fm,values):
    """Rewrite only the top-level frontmatter keys in `values`; other lines stay as they are."""
    blocks=[]
    for line in (fm or '').splitlines(keepends=True):
        if blocks and (not line.strip() or line[0] in ' \t-'): blocks[-1][1]+=line; continue
        m=KEY_RE.match(line); blocks.append([m.group(1) if m else None,line])
    out,done=[],set()
    for k,t in blocks:
        if k not in values: out.append(t if t.endswith('\n') else t+'\n')
        elif k not in done: done.add(k); out.append(_dump({k:values[k]}))
    return ''.join(out+[_dump({k:v}) for k,v in values.items() if k not in done])

def links(text):
    """[[Target]], [[Target|alias]] and [[Target#Heading]] outside code, with offsets into `text`."""
    out=[]
    for m in LINK_RE.finditer(CODE_RE.sub(lambda m:' '*len(m.group()),text)):
        target,_,alias=m.group(1).partition('|'); target,_,heading=target.partition('#')
        if target.strip() or heading.strip(): out.append({'target':target.strip(),'heading':heading.strip() or None,'alias':alias.strip() or None,'start':m.start(),'end':m.end()})
    return out

def section(body,name):
    """Text under '## <name>' up to the next level 1-2 heading, or None when the section is missing."""
    m=re.search(rf'^## +{re.escape(name)}[ \t]*\r?$',body,re.M)
    if not m: return None
    n=re.compile(r'^#{1,2} ',re.M).search(body,m.end())
    return body[m.end():n.start() if n else len(body)].strip('\n')

def set_section(body,name,text):
    m=re.search(rf'^## +{re.escape(name)}[ \t]*\r?$',body,re.M); text=(text or '').strip('\n')
    if not m: return body.rstrip('\n')+f'\n\n## {name}\n'+(f'{text}\n' if text else '')
    n=re.compile(r'^#{1,2} ',re.M).search(body,m.end()); end=n.start() if n else len(body)
    return body[:m.end()]+'\n'+(f'{text}\n' if text else '')+('\n' if n else '')+body[end:]

def _type(rel,meta):
    t=meta.get('omen_type')
    if t in TYPES: return t
    if rel=='Goals.md': return 'goal'
    return {'People':'person','Opportunities':'opportunity','Orgs':'org'}.get(rel.split('/')[0] if '/' in rel else '','note')

def task_hash(line): return hashlib.sha1(line.rstrip().encode()).hexdigest()[:12]

def tasks(body):
    """`- [ ]` / `- [x]` lines outside code fences, with due dates (`📅 YYYY-MM-DD` or `due:: YYYY-MM-DD`) and their ## section."""
    out=[]; fence=None; section=None
    for i,line in enumerate(body.split('\n')):
        f=FENCE_RE.match(line)
        if f: fence=None if fence and f.group(1)==fence else fence or f.group(1); continue
        if fence: continue
        h=HEAD_RE.match(line)
        if h:
            if len(h.group(1))<=2: section=h.group(2).strip()
            continue
        m=TASK_RE.match(line)
        if not m: continue
        due=DUE_RE.search(m.group(3))
        out.append({'line':i,'hash':task_hash(line),'text':m.group(3),'done':m.group(2)!=' ','due':due.group(1) if due else None,'indent':len(m.group(1).expandtabs(4)),'section':section,'links':[l for l in links(m.group(3)) if l['target']]})
    return out

def _parse(rel,text,mtime=0.0):
    fm,body=split(text); meta=frontmatter(fm); h=H1_RE.search(body)
    return {'path':rel,'title':h.group(1) if h else PurePosixPath(rel).stem,'type':_type(rel,meta),'frontmatter':meta,'body':body,'links':links(body),'tasks':tasks(body),'mtime':mtime}

def index():
    """{path: parsed note} for every .md file; only files whose mtime or size changed are re-read."""
    with lock:
        r=ensure(); out={}; changed=[]
        for d,dirs,files in os.walk(r):
            dirs[:]=sorted(x for x in dirs if not x.startswith('.'))
            for f in files:
                if f.startswith('.') or not f.endswith('.md'): continue
                p=Path(d)/f
                if not p.resolve().is_relative_to(r): continue
                rel=p.relative_to(r).as_posix(); st=p.stat(); key=(st.st_mtime_ns,st.st_size); hit=_cache.get((r,rel))
                if not hit or hit[0]!=key: hit=_cache[(r,rel)]=(key,_parse(rel,p.read_text(encoding='utf-8',errors='replace'),st.st_mtime)); changed.append(hit[1])
                out[rel]=hit[1]
        for k in [k for k in _cache if k[0]==r and k[1] not in out]: del _cache[k]
        _mirror(changed)
        if r not in _migrated:
            _migrated.add(r)
            if _migrate(out): return index()
        return out

def _mirror(notes):
    """Copy '## Notes' from changed opportunity/person notes into the DB, so edits made in Obsidian reach the digest."""
    todo=[(n,section(n['body'],'Notes')) for n in notes if n['type'] in TABLES and str(n['frontmatter'].get('omen_id','')).isdigit()]
    if not todo: return
    c=connect()
    for n,text in todo:
        if text is not None: c.execute(f"UPDATE {TABLES[n['type']]} SET notes=? WHERE id=? AND COALESCE(notes,'')!=?",(text.strip(),int(n['frontmatter']['omen_id']),text.strip()))
    c.commit(); c.close()

class Resolver:
    """Obsidian-style link resolution: exact path, then a unique path-suffix/basename match, case-insensitive."""
    def __init__(self,paths):
        self.exact={p.casefold():p for p in paths}; self.suffix={}
        for p in paths:
            parts=p.casefold().split('/')
            for i in range(1,len(parts)): self.suffix.setdefault('/'.join(parts[i:]),[]).append(p)
    @staticmethod
    def key(target):
        t=(target or '').strip().replace('\\','/').lstrip('/')
        return t if not t or t.casefold().endswith('.md') else t+'.md'
    def __call__(self,target):
        t=self.key(target).casefold()
        if not t: return None
        if t in self.exact: return self.exact[t]
        hits=self.suffix.get(t,[])
        return hits[0] if len(hits)==1 else None

def _snippet(body,start,end):
    a=body.rfind('\n',0,start)+1; b=body.find('\n',end); line=body[a:b if b>=0 else len(body)].strip()
    return line if len(line)<=180 else line[:177]+'…'

def get(rel):
    rel,_=safe(rel); idx=index()
    if rel not in idx: raise FileNotFoundError(rel)
    n=idx[rel]; res=Resolver(idx); backlinks=[]
    for p,o in idx.items():
        hits=[l for l in o['links'] if l['target'] and res(l['target'])==rel]
        if hits and p!=rel: backlinks.append({'path':p,'title':o['title'],'snippet':_snippet(o['body'],hits[0]['start'],hits[0]['end'])})
    resolved={l['target']:res(l['target']) for l in n['links'] if l['target']}
    return {'path':rel,'title':n['title'],'type':n['type'],'frontmatter':n['frontmatter'],'body':n['body'],'backlinks':sorted(backlinks,key=lambda b:b['title'].casefold()),'resolved':resolved}

def save(rel,body,meta=None):
    """Write a note (creating it if new). `meta` replaces the frontmatter; None keeps the file's own."""
    with lock:
        rel,p=safe(rel); ensure()
        fm,_=split(p.read_text(encoding='utf-8')) if p.is_file() else (None,'')
        if meta is not None: fm=_dump(meta) if meta else None
        _atomic(p,(f'---\n{fm}---\n' if fm is not None else '')+body)
        return get(rel)

def name(text,limit=80):
    """Filesystem- and wikilink-safe note name."""
    t=re.sub(r"[^\w\s\-.,'()&+!]",' ',unicodedata.normalize('NFKC',text or ''))
    return re.sub(r'\s+',' ',t).strip(' .-')[:limit].rstrip(' .-') or 'Untitled'

def _when(v):
    if not v: return None
    d=datetime.fromisoformat(str(v).replace('Z','+00:00')); return d if d.tzinfo else d.replace(tzinfo=timezone.utc)

def _label(entity,rec): return rec['title'] if entity=='opportunity' else rec['name']
def org_path(org): return f'Orgs/{name(org)}.md'
def _rec(c,entity,eid): r=c.execute(f'SELECT * FROM {TABLES[entity]} WHERE id=?',(eid,)).fetchone(); return dict(r) if r else None

def _mapped(c,entity,eid,idx=None):
    """Path of an entity's existing note: the stored path, else a scan for its omen_id (the file was renamed)."""
    ok=lambda n:n and n['type']==entity and str(n['frontmatter'].get('omen_id'))==str(eid)
    row=c.execute('SELECT path FROM vault_notes WHERE entity=? AND entity_id=?',(entity,str(eid))).fetchone()
    idx=idx if idx is not None else index()
    if row and ok(idx.get(row[0])): return row[0]
    for p,n in idx.items():
        if ok(n): c.execute('INSERT OR REPLACE INTO vault_notes(entity,entity_id,path) VALUES(?,?,?)',(entity,str(eid),p)); c.commit(); return p
    return None

def _org(entity,rec): return ((rec['org'] if entity=='opportunity' else rec['organization']) or '').strip()

def _stem(p): return p.rsplit('/',1)[-1][:-3].casefold()
def stems(idx):
    """{casefolded file name: [paths]}; build once and pass to planned() when naming many entities."""
    out={}
    for p in idx: out.setdefault(_stem(p),[]).append(p)
    return out

def planned(entity,rec,idx,taken=(),own=None,names=None):
    """Path for a new stub: the plain title, so [[Title]] resolves in Omen and Obsidian.
    File names must be unique vault-wide; on a clash add " (Org)", or " YYYY-MM-DD" for a repeat of the same org's event."""
    names=names if names is not None else stems(idx)
    taken={_stem(t) for t in taken}; used=lambda n:n in taken or any(p!=own for p in names.get(n,()))
    base=name(_label(entity,rec)); org=name(_org(entity,rec)) if _org(entity,rec) else ''
    when=_when(rec['starts_at']) if entity=='opportunity' else None; day=when.date().isoformat() if when else ''
    holder=next((idx[p] for p in names.get(base.casefold(),()) if p!=own),None)
    repeat=bool(day) and holder is not None and name(str(holder['frontmatter'].get('org') or '')).casefold()==org.casefold()
    options=[base]+([f'{base} {day}'] if repeat else [])+([f'{base} ({org})'] if org else [])+([f'{base} {day}'] if day else [])+([f'{base} ({org}) {day}'] if org and day else [])
    for n in itertools.chain(options,(f'{base} {i}' for i in itertools.count(2))):
        if not used(n.casefold()): return f'{FOLDERS[entity]}/{n}.md'

def link_text(rel,idx):
    """Shortest link that resolves to `rel`: the bare file name when it is unique, else the path."""
    s=PurePosixPath(rel).stem
    return s if sum(PurePosixPath(p).stem.casefold()==s.casefold() for p in idx)<=1 else rel[:-3]

def _migrate(idx):
    """Rename stubs still using the old '<title> <hash>.md' names to plain names; rename() rewrites their links."""
    c=connect(); moved=False
    try:
        for p,n in sorted(idx.items()):
            m=HASHED.match(PurePosixPath(p).stem); oid=str(n['frontmatter'].get('omen_id',''))
            if not m or n['type'] not in TABLES or not oid.isdigit(): continue
            rec=_rec(c,n['type'],int(oid))
            if not rec or m.group(1)!=name(_label(n['type'],rec)): continue
            cur=index(); dst=str(PurePosixPath(p).parent/PurePosixPath(planned(n['type'],rec,cur,own=p)).name)
            if dst!=p: rename(p,dst); moved=True
        return moved
    finally: c.close()

def _mirrored(entity,rec):
    if entity=='opportunity': return {'omen_type':'opportunity','omen_id':rec['id'],'url':rec['url'],'org':rec['org'] or '','type':rec['type'],'stage':rec['stage'],'starts':_when(rec['starts_at']),'deadline':_when(rec['deadline']),'score':rec['score']}
    return {'omen_type':'person','omen_id':rec['id'],'role':rec['role'] or '','org':rec['organization'] or '','state':rec['state']}

def _stub(c,entity,rec,idx):
    if entity=='opportunity':
        when=_when(rec['starts_at']); bits=[f"[[{org_path(rec['org'])[:-3]}]]" if (rec['org'] or '').strip() else '',f'{when:%a %b} {when.day}, {when:%Y}' if when else '',f"[Event page]({rec['url']})"]
        deadline=_when(rec['deadline']); apply=f'- [ ] Apply 📅 {deadline.date().isoformat()}\n' if deadline else ''
        body=f"# {rec['title']}\n\n{' · '.join(b for b in bits if b)}\n\n## Notes\n{(rec['notes'] or '').strip()}\n\n## Prep\n{apply}\n## Retro\n"
    else:
        event=_rec(c,'opportunity',rec['event_id']) if rec['event_id'] else None
        ev=note_for('opportunity',event['id']) if event else None  # create the event's note so the link resolves
        if ev: idx=index()
        org=(rec['organization'] or '').strip(); who=' at '.join(x for x in [rec['role'] or '',f'[[{org_path(org)[:-3]}]]' if org else ''] if x)
        line=' · '.join(x for x in [who,f'met at [[{link_text(ev,idx)}]]' if ev else ''] if x)
        ended=_when((event['ends_at'] or event['starts_at']) if event else None)
        follow=f"- [ ] Follow up with {rec['name']}"+(f" 📅 {(ended+timedelta(days=3)).date().isoformat()}" if ended else '')
        body=f"# {rec['name']}\n\n{line}\n\n## Why\n{(rec['why'] or '').strip()}\n\n## Notes\n{(rec['notes'] or '').strip()}\n\n## Follow-ups\n{follow}\n"
    return f'---\n{_dump(_mirrored(entity,rec))}---\n'+re.sub(r'\n{3,}','\n\n',body)

def note_for(entity,eid):
    """Path of the note for an opportunity, person or org, creating the stub the first time it is requested."""
    with lock:
        idx=index()
        if entity=='org':
            rel=Resolver(idx)(org_path(eid)) or org_path(eid)
            if rel not in idx: _atomic(safe(rel)[1],f"---\nomen_type: org\n---\n# {eid.strip()}\n\n## Notes\n")
            return rel
        c=connect()
        try:
            rec=_rec(c,entity,int(eid))
            if not rec: raise KeyError(f'{entity} {eid} not found')
            rel=_mapped(c,entity,rec['id'],idx)
            if rel: _refresh(c,entity,rec,rel)
            else:
                text=_stub(c,entity,rec,idx); rel=planned(entity,rec,index()); _atomic(safe(rel)[1],text)
                c.execute('INSERT OR REPLACE INTO vault_notes(entity,entity_id,path) VALUES(?,?,?)',(entity,str(rec['id']),rel)); c.commit()
            return rel
        finally: c.close()

def _refresh(c,entity,rec,rel,notes=None):
    """Bring the mirrored frontmatter (and optionally ## Notes) of an existing note up to date with the DB."""
    _,p=safe(rel); text=p.read_text(encoding='utf-8'); fm,body=split(text)
    new_fm=set_keys(fm,_mirrored(entity,rec)); new_body=body if notes is None else set_section(body,'Notes',notes)
    new=f'---\n{new_fm}---\n{new_body}'
    if new!=text: _atomic(p,new)

def sync_entity(entity,eid,notes=None):
    """After a PATCH: update the entity's note if it exists. Never creates the vault or a note."""
    if not root().is_dir(): return None
    with lock:
        c=connect()
        try:
            row=c.execute('SELECT path FROM vault_notes WHERE entity=? AND entity_id=?',(entity,str(eid))).fetchone(); rec=_rec(c,entity,eid)
            if not row or not rec: return None
            rel=_mapped(c,entity,eid)
            if rel: _refresh(c,entity,rec,rel,notes)
            return rel
        finally: c.close()

def tree():
    idx=index(); top={'name':'','path':'','type':'folder','children':[]}
    for rel in sorted(idx,key=str.casefold):
        node=top; parts=rel.split('/')
        for i,part in enumerate(parts[:-1]):
            nxt=next((x for x in node['children'] if x['type']=='folder' and x['name']==part),None)
            if not nxt: nxt={'name':part,'path':'/'.join(parts[:i+1]),'type':'folder','children':[]}; node['children'].append(nxt)
            node=nxt
        node['children'].append({'name':parts[-1][:-3],'path':rel,'type':'note','title':idx[rel]['title'],'note_type':idx[rel]['type']})
    for d in FOLDERS.values():
        if not any(x['name']==d for x in top['children']): top['children'].append({'name':d,'path':d,'type':'folder','children':[]})
    return top

def search(q,limit=20):
    """Title matches first, then full-text. `link` is the shortest unambiguous [[link]] text for autocomplete."""
    idx=index(); q=(q or '').strip().casefold(); stems={}
    for p in idx: stems.setdefault(PurePosixPath(p).stem.casefold(),[]).append(p)
    hits=[]
    for p,n in idx.items():
        hay=f"{n['title']} {PurePosixPath(p).stem}".casefold()
        stem=PurePosixPath(p).stem
        rank=0 if not q or q in (stem.casefold(),n['title'].casefold()) else 1 if hay.startswith(q) or any(w.startswith(q) for w in hay.split()) else 2 if q in hay or q in p.casefold() else 3 if q in n['body'].casefold() else None
        if rank is None: continue
        at=n['body'].casefold().find(q) if rank==3 else -1
        hits.append((rank,n['title'].casefold(),len(stem),stem.casefold(),{'path':p,'title':n['title'],'type':n['type'],'link':stem if len(stems[stem.casefold()])==1 else p[:-3],'snippet':_snippet(n['body'],at,at+len(q)) if at>=0 else ''}))
    return [h[-1] for h in sorted(hits,key=lambda h:h[:-1])[:limit]]

def rename(src,dst):
    """Move a note and rewrite every [[link]] that pointed at it."""
    with lock:
        src,sp=safe(src); dst,dp=safe(dst)
        if not sp.is_file(): raise FileNotFoundError(src)
        if dp.exists() and not sp.samefile(dp): raise FileExistsError(dst)
        idx=index(); res=Resolver(idx); edits={p:[l for l in n['links'] if l['target'] and res(l['target'])==src] for p,n in idx.items()}
        after=[x for x in idx if x!=src]+[dst]; stem=PurePosixPath(dst).stem
        unique=sum(PurePosixPath(x).stem.casefold()==stem.casefold() for x in after)==1
        dp.parent.mkdir(parents=True,exist_ok=True); os.replace(sp,dp)
        for p,ls in edits.items():
            if not ls: continue
            path=safe(dst if p==src else p)[1]; text=path.read_text(encoding='utf-8'); fm,body=split(text); head=text[:len(text)-len(body)]
            for l in sorted(ls,key=lambda l:-l['start']):
                t=stem if unique and '/' not in l['target'] else dst[:-3]
                body=body[:l['start']]+'[['+t+(f"#{l['heading']}" if l['heading'] else '')+(f"|{l['alias']}" if l['alias'] else '')+']]'+body[l['end']:]
            _atomic(path,head+body)
        c=connect(); c.execute('UPDATE vault_notes SET path=? WHERE path=?',(dst,src)); c.commit(); c.close()
        return get(dst)

def _rows(c,sql,args=()): return [dict(r) for r in c.execute(sql,args)]

def graph(include=None,stages=('saved','applied')):
    """Nodes for goals, people, orgs, tracked or noted opportunities and free notes; links of kind wikilink/attended/org/goal."""
    inc=set(include or INCLUDE.values()); idx=index(); res=Resolver(idx); nodes={}; edges={}
    def add(nid,label,typ,**kw):
        if INCLUDE.get(typ,'notes') in inc or typ=='unresolved': nodes.setdefault(nid.casefold(),{'id':nid,'label':label,'type':typ,**kw})
        return nodes.get(nid.casefold())
    def link(a,b,kind,**kw):
        a,b=nodes.get(a.casefold()),nodes.get(b.casefold())
        if a and b and a is not b: edges.setdefault((a['id'],b['id'],kind),{'source':a['id'],'target':b['id'],'kind':kind,**kw})
    c=connect()
    try:
        noted={(n['type'],str(n['frontmatter'].get('omen_id'))):p for p,n in idx.items() if n['type'] in TABLES and n['frontmatter'].get('omen_id') is not None}
        people=_rows(c,'SELECT * FROM people ORDER BY id'); st=[s for s in stages if s] or ['saved','applied']; ph=','.join('?'*len(st))
        opps={o['id']:o for o in _rows(c,f"SELECT * FROM opportunities WHERE status IN ('saved','applied') AND (stage IN ({ph}) OR status IN ({ph}))",st+st)}
        want={int(i) for t,i in noted if t=='opportunity' and i.isdigit()}|{p['event_id'] for p in people if p['event_id']}
        for o in _rows(c,f"SELECT * FROM opportunities WHERE id IN ({','.join('?'*len(want))})",list(want)) if want else []: opps[o['id']]=o
        if 'goals' in inc:
            add('Goals.md','Goals','goal',path='Goals.md',hub=True)
            for g in goals(): add(f'Goals.md#{g}',g,'goal',path='Goals.md',heading=g); link('Goals.md',f'Goals.md#{g}','goal')
        taken=set(); names=stems(idx)
        def entity_node(entity,rec):
            p=noted.get((entity,str(rec['id'])))
            if not p: p=planned(entity,rec,idx,taken,names=names); taken.add(p)
            extra={'score':rec['score'] or 0,'stage':rec['stage']} if entity=='opportunity' else {'state':rec['state']}
            return add(p,_label(entity,rec),entity,path=p if p in idx else None,entity=entity,entity_id=rec['id'],**extra)
        def org_node(org):
            p=res(org_path(org)) or org_path(org)
            return add(p,org.strip(),'org',path=p if p in idx else None,entity='org',entity_id=org.strip())
        onode={i:entity_node('opportunity',o) for i,o in opps.items()}
        for i,o in opps.items():
            if onode[i] and (o['org'] or '').strip() and (g:=org_node(o['org'])): link(onode[i]['id'],g['id'],'org')
        for p in people:
            n=entity_node('person',p)
            if not n: continue
            if p['event_id'] in onode and onode[p['event_id']]: link(n['id'],onode[p['event_id']]['id'],'attended')
            if (p['organization'] or '').strip() and (g:=org_node(p['organization'])): link(n['id'],g['id'],'org')
        for p,n in idx.items():
            if p!='Goals.md': add(p,n['title'],n['type'],path=p)
        for p,n in idx.items():
            if p.casefold() not in nodes: continue
            for l in n['links']:
                if not l['target']: continue
                r=res(l['target'])
                if r=='Goals.md' and l['heading'] and f"goals.md#{l['heading']}".casefold() in nodes: link(p,f"Goals.md#{l['heading']}",'goal')
                elif r: link(p,r,'wikilink')
                else:
                    t=Resolver.key(l['target'])
                    if t.casefold() not in nodes: add(t,PurePosixPath(t).stem,'unresolved',path=t)
                    link(p,t,'wikilink',unresolved=nodes[t.casefold()]['type']=='unresolved')
        return {'nodes':list(nodes.values()),'links':list(edges.values())}
    finally: c.close()

def task_list(status=None,due_before=None):
    """Every task in the vault with its note, the goals it links to and the entity notes it links to."""
    idx=index(); res=Resolver(idx); out=[]
    for p,n in idx.items():
        own={'type':n['type'],'id':n['frontmatter'].get('omen_id')} if n['type'] in TABLES else None
        for t in n['tasks']:
            if status=='open' and t['done'] or status=='done' and not t['done'] or due_before and not (t['due'] and t['due']<due_before): continue
            linked=[{'target':l['target'],'heading':l['heading'],'path':res(l['target'])} for l in t['links']]
            out.append({**{k:v for k,v in t.items() if k!='links'},'path':p,'note_title':n['title'],'note_type':n['type'],'entity':own,'links':linked,
             'goals':[l['heading'] for l in linked if l['path']=='Goals.md' and l['heading']],
             'entities':[{'type':idx[l['path']]['type'],'id':idx[l['path']]['frontmatter'].get('omen_id'),'path':l['path']} for l in linked if l['path'] in idx and idx[l['path']]['type'] in TABLES]})
    return out

def toggle_task(rel,hash_,done=None,line=None):
    """Check or uncheck one task, rewriting only that line. `line` disambiguates identical lines."""
    with lock:
        rel,p=safe(rel)
        if not p.is_file(): raise FileNotFoundError(rel)
        with open(p,encoding='utf-8',newline='') as f: text=f.read()  # keep the file's own line endings
        fm,body=split(text); head=text[:len(text)-len(body)]; lines=body.split('\n')
        hits=[t for t in tasks(body) if t['hash']==hash_]
        if not hits: raise LookupError('That task changed or no longer exists; reload the note.')
        t=min(hits,key=lambda t:abs(t['line']-(line if line is not None else t['line'])))
        want=(not t['done']) if done is None else done
        lines[t['line']]=re.sub(r'\[[ xX]\]','[x]' if want else '[ ]',lines[t['line']],count=1)
        if want!=t['done']: _atomic(p,head+'\n'.join(lines))
        return next(x for x in task_list() if x['path']==rel and x['line']==t['line'])
