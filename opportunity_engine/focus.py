"""What needs attention, computed from the vault's notes and tasks plus the DB. Nothing here is stored."""
from datetime import date, datetime, timedelta, timezone
from pathlib import PurePosixPath
from . import vault
from .db import connect

STAGES=('saved','applied','going','attended','skipped')
GRACE=timedelta(days=3); STALE=timedelta(days=14)

def _when(v): return vault._when(v)
def _rows(c,sql,args=()): return [dict(r) for r in c.execute(sql,args)]
def _iso(ts): return datetime.fromtimestamp(ts,timezone.utc).isoformat() if ts else None

def compute(now=None):
    """{overdue_tasks, due_soon, deadlines, needs_retro, follow_ups, goals} — every item carries the note path it opens."""
    now=now or datetime.now(timezone.utc); today=now.date().isoformat(); week=(now.date()+timedelta(days=7)).isoformat()
    idx=vault.index(); res=vault.Resolver(idx); c=connect()
    try:
        noted={(n['type'],str(n['frontmatter'].get('omen_id'))):p for p,n in idx.items() if n['type'] in vault.TABLES and n['frontmatter'].get('omen_id') is not None}
        taken=set(); names=vault.stems(idx)
        def where(entity,rec):
            """Note path for an entity: its note, or the path its stub will get (opened through /notes/for)."""
            p=noted.get((entity,str(rec['id'])))
            if p: return {'path':p,'exists':True,'entity':entity,'entity_id':rec['id']}
            p=vault.planned(entity,rec,idx,taken,names=names); taken.add(p)
            return {'path':p,'exists':False,'entity':entity,'entity_id':rec['id']}
        def task_item(p,t): return {'kind':'task','title':t['text'],'path':p,'exists':True,'note_title':idx[p]['title'],'line':t['line'],'hash':t['hash'],'due':t['due'],'done':t['done']}
        open_tasks=[(p,t) for p,n in idx.items() for t in n['tasks'] if not t['done']]
        overdue=[task_item(p,t) for p,t in open_tasks if t['due'] and t['due']<today]
        due_soon=[task_item(p,t) for p,t in open_tasks if t['due'] and today<=t['due']<=week]

        tracked=_rows(c,"SELECT * FROM opportunities WHERE stage IN ('going','attended') OR (status='saved' AND stage='saved' AND deadline IS NOT NULL)")
        deadlines=[]; needs_retro=[]
        for o in tracked:
            dl=_when(o['deadline']); ended=_when(o['ends_at'] or o['starts_at'])
            if o['stage']=='saved' and o['status']=='saved' and dl and now<=dl<=now+timedelta(days=7):
                deadlines.append({'kind':'deadline','title':o['title'],'deadline':dl.isoformat(),**where('opportunity',o)})
            if o['stage'] in ('going','attended') and ended and ended<now:
                w=where('opportunity',o); retro=vault.section(idx[w['path']]['body'],'Retro') if w['exists'] else None
                if not (retro or '').strip(): needs_retro.append({'kind':'retro','title':o['title'],'ended':ended.isoformat(),**w})
        deadlines.sort(key=lambda x:x['deadline']); needs_retro.sort(key=lambda x:x['ended'])

        people=_rows(c,'SELECT * FROM people'); ev_ids=sorted({p['event_id'] for p in people if p['event_id']})
        events={o['id']:o for o in _rows(c,f"SELECT * FROM opportunities WHERE id IN ({','.join('?'*len(ev_ids))})",ev_ids)} if ev_ids else {}
        follow_ups=[]
        for person in people:
            w=where('person',person); n=idx.get(w['path']) if w['exists'] else None
            fu=[t for t in (n['tasks'] if n else []) if t['section']=='Follow-ups' and not t['done']]
            due=[t for t in fu if t['due'] and t['due']<=today]
            ev=events.get(person['event_id']); ended=_when((ev['ends_at'] or ev['starts_at'])) if ev else None
            quiet=person['state']=='met' and ended is not None and ended+GRACE<now and not fu and (n is None or n['mtime']<ended.timestamp())
            if due or quiet:
                follow_ups.append({'kind':'follow_up','title':person['name'],'reason':f"Follow-up due {min(t['due'] for t in due)}" if due else f"Met at {ev['title']}; nothing since",
                 'due':min(t['due'] for t in due) if due else (ended+GRACE).date().isoformat(),'event':ev['title'] if ev else None,**w,
                 **({'line':due[0]['line'],'hash':due[0]['hash']} if due else {})})
        follow_ups.sort(key=lambda x:x['due'])
        return {'overdue_tasks':sorted(overdue,key=lambda x:x['due']),'due_soon':sorted(due_soon,key=lambda x:x['due']),'deadlines':deadlines,
                'needs_retro':needs_retro,'follow_ups':follow_ups,'goals':goal_progress(idx,res,c,now,people)}
    finally: c.close()

def goal_progress(idx,res,c,now,people):
    """Per `## Goal`: what links to [[Goals#Goal]] — opportunities by stage, people met, tasks, last activity, stale/empty."""
    heads={g.casefold():g for g in vault.goals()}; linked={g:set() for g in heads.values()}; task_sets={g:{} for g in heads.values()}
    for p,n in idx.items():
        if p=='Goals.md': continue
        for l in n['links']:
            g=heads.get((l['heading'] or '').casefold())
            if g and l['target'] and res(l['target'])=='Goals.md': linked[g].add(p)
        for t in n['tasks']:
            for l in t['links']:
                g=heads.get((l['heading'] or '').casefold())
                if g and res(l['target'])=='Goals.md': task_sets[g][(p,t['line'])]=t
    opp_ids={int(idx[p]['frontmatter']['omen_id']) for ps in linked.values() for p in ps if idx[p]['type']=='opportunity' and str(idx[p]['frontmatter'].get('omen_id','')).isdigit()}
    opps={o['id']:o for o in _rows(c,f"SELECT id,stage FROM opportunities WHERE id IN ({','.join('?'*len(opp_ids))})",list(opp_ids))} if opp_ids else {}
    by_person={p['id']:p for p in people}
    out=[]
    for g in heads.values():
        ps=linked[g]; stages={}; met=set()
        for p in ps:
            n=idx[p]; oid=str(n['frontmatter'].get('omen_id',''))
            for t in n['tasks']: task_sets[g].setdefault((p,t['line']),t)
            if n['type']=='opportunity' and oid.isdigit() and int(oid) in opps:
                s=opps[int(oid)]['stage'] or 'saved'; stages[s]=stages.get(s,0)+1
                met|={x['id'] for x in people if x['event_id']==int(oid) and x['state']=='met'}
            if n['type']=='person' and oid.isdigit() and by_person.get(int(oid),{}).get('state')=='met': met.add(int(oid))
        ts=list(task_sets[g].values()); last=max((idx[p]['mtime'] for p in ps|{k[0] for k in task_sets[g]}),default=0)
        flag='empty' if not ps and not ts else 'stale' if now.timestamp()-last>STALE.total_seconds() else None
        out.append({'heading':g,'path':'Goals.md','counts':{'opportunities':stages,'people_met':len(met),'tasks_open':sum(not t['done'] for t in ts),'tasks_done':sum(t['done'] for t in ts),'notes':len(ps)},
                    'last_activity':_iso(last),'flag':flag})
    return out

def mark_graph(graph,f=None):
    """Graph decoration: stale/empty goals get `flag`; notes with overdue tasks, due follow-ups and missing retros get `warn`."""
    f=f or compute(); warn={x['path'].casefold() for k in ('overdue_tasks','follow_ups','needs_retro') for x in f[k]}
    flags={g['heading'].casefold():g['flag'] for g in f['goals']}
    for n in graph['nodes']:
        if n['type']=='goal' and n.get('heading') and flags.get(n['heading'].casefold()): n['flag']=flags[n['heading'].casefold()]
        if (n.get('path') or n['id']).casefold() in warn: n['warn']=True
    return graph
