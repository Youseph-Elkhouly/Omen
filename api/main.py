from __future__ import annotations
import logging, sqlite3, subprocess, sys, uuid, os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field
from opportunity_engine import focus, vault
from opportunity_engine.db import connect, db_path

ROOT=Path(__file__).resolve().parents[1]
DB=db_path()
log=logging.getLogger(__name__)
app=FastAPI(title='Omen API',version='0.1.0')
app.add_middleware(CORSMiddleware,allow_origins=[x.strip() for x in os.getenv('WEB_ORIGINS','').split(',') if x.strip()],allow_origin_regex=os.getenv('WEB_ORIGIN_REGEX') or None,allow_methods=['*'],allow_headers=['*'])

def db(): return connect()
def write_note(entity,eid,notes=None):
 try: vault.sync_entity(entity,eid,notes)
 except Exception: log.exception('Could not update the vault note for %s %s',entity,eid)
class OpportunityPatch(BaseModel):
 status:Literal['new','saved','applied','skipped','expired']|None=None
 stage:Literal['saved','applied','going','attended','skipped']|None=None
 notes:str|None=None
class Feedback(BaseModel): action:Literal['save','skip']
class PersonPatch(BaseModel):
 state:Literal['want_to_meet','met']|None=None
 notes:str|None=None

@app.get('/opportunities')
def opportunities(type:str|None=None,from_:str|None=Query(None,alias='from'),to:str|None=None,remote:bool|None=None,min_score:int=0,tags:str|None=None,sort:str='score',q:str|None=None):
 c=db(); sql='SELECT * FROM opportunities WHERE 1=1';args=[]
 if type:sql+=' AND type=?';args.append(type)
 if from_:sql+=' AND (starts_at IS NULL OR starts_at>=?)';args.append(from_)
 if to:sql+=' AND (starts_at IS NULL OR starts_at<=?)';args.append(to)
 if remote is not None:sql+=' AND is_remote=?';args.append(int(remote))
 sql+=' AND COALESCE(score,0)>=?';args.append(min_score)
 if q:sql+=' AND (title LIKE ? OR org LIKE ? OR description LIKE ?)';args.extend([f'%{q}%']*3)
 if tags:
  for tag in tags.split(','):sql+=' AND tags LIKE ?';args.append(f'%{tag.strip()}%')
 sql+= {'date':' ORDER BY starts_at IS NULL, starts_at','newest':' ORDER BY first_seen DESC','score':' ORDER BY score DESC'}.get(sort,' ORDER BY score DESC')
 rows=[dict(r) for r in c.execute(sql,args)];c.close();return rows
@app.get('/opportunities/{oid}')
def opportunity(oid:int):
 c=db();r=c.execute('SELECT * FROM opportunities WHERE id=?',(oid,)).fetchone();c.close()
 if not r:raise HTTPException(404,'Opportunity not found')
 return dict(r)
@app.patch('/opportunities/{oid}')
def patch_opportunity(oid:int,p:OpportunityPatch):
 fields={k:v for k,v in p.model_dump(exclude_none=True).items()}
 if 'stage' in fields and 'status' not in fields: fields['status']={'saved':'saved','skipped':'skipped'}.get(fields['stage'],'applied')
 if not fields: return opportunity(oid)
 c=db();c.execute('UPDATE opportunities SET '+','.join(f'{k}=?' for k in fields)+' WHERE id=?',(*fields.values(),oid));c.commit();exists=c.total_changes;c.close()
 if not exists:raise HTTPException(404,'Opportunity not found')
 write_note('opportunity',oid,fields.get('notes'));return opportunity(oid)
@app.post('/opportunities/{oid}/feedback')
def feedback(oid:int,p:Feedback): return patch_opportunity(oid,OpportunityPatch(status='saved' if p.action=='save' else 'skipped',stage='saved' if p.action=='save' else 'skipped'))
@app.get('/profile')
def profile():
 import json
 path=ROOT/'opportunity_engine/profile/resume.json'; goals=vault.goals_path()
 return {'resume':json.loads(path.read_text()) if path.exists() else {},'goals':goals.read_text() if goals.exists() else ''}

@app.get('/people')
def people():
 c=db();rows=[dict(r) for r in c.execute('SELECT p.*,o.title AS next_event FROM people p LEFT JOIN opportunities o ON o.id=p.event_id ORDER BY p.name')];c.close();return rows
@app.patch('/people/{pid}')
def patch_person(pid:int,p:PersonPatch):
 fields=p.model_dump(exclude_none=True);c=db()
 if fields:c.execute('UPDATE people SET '+','.join(f'{k}=?' for k in fields)+' WHERE id=?',(*fields.values(),pid));c.commit()
 r=c.execute('SELECT * FROM people WHERE id=?',(pid,)).fetchone();c.close()
 if not r:raise HTTPException(404,'Person not found')
 if fields:write_note('person',pid,fields.get('notes'))
 return dict(r)
@app.get('/x/posts')
def x_posts():
 c=db();rows=[dict(r) for r in c.execute('SELECT * FROM x_posts ORDER BY score DESC,created_at DESC')];c.close();return rows
@app.post('/x/posts/{post_id}/track')
def track_post(post_id:int):
 c=db();p=c.execute('SELECT * FROM x_posts WHERE id=?',(post_id,)).fetchone()
 if not p: c.close();raise HTTPException(404,'Post not found')
 if p['opportunity_id']:
  row=c.execute('SELECT * FROM opportunities WHERE id=?',(p['opportunity_id'],)).fetchone();c.close();return dict(row)
 now=datetime.now(timezone.utc).isoformat();source_id=f"x-post-{post_id}"
 c.execute('INSERT INTO opportunities(source,source_id,url,title,org,type,description,location,is_remote,raw,first_seen,last_seen,score,score_reason,status,stage,notes) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',('x',source_id,p['url'] or '',p['text'][:100],p['author'],'other',p['text'],'',0,'{}',now,now,p['score'],'Added from an X post.', 'new','saved',''))
 oid=c.execute('SELECT id FROM opportunities WHERE source=? AND source_id=?',('x',source_id)).fetchone()[0];c.execute('UPDATE x_posts SET opportunity_id=? WHERE id=?',(oid,post_id));c.commit();row=c.execute('SELECT * FROM opportunities WHERE id=?',(oid,)).fetchone();c.close();return dict(row)

@app.get('/today')
def today():
 items=opportunities(type=None,from_=None,to=None,remote=None,min_score=0,tags=None,sort='score',q=None);now=datetime.now(timezone.utc);week=(now+timedelta(days=7)).isoformat()
 picks=sorted([x for x in items if x.get('status')=='new' and x.get('type') in {'event','hackathon','competition','program','fellowship','other'}],key=lambda x:x.get('score') or 0,reverse=True)[:5]
 closing=[x for x in items if x.get('deadline') and x['deadline']<week and x['deadline']>now.isoformat()]
 saved=[x for x in items if x.get('status')=='saved'][:5]
 goals=vault.goals()
 return {'picks':picks,'deadlines':closing,'saved':saved,'goals':goals,'synced_at':now.isoformat()}
@app.get('/calendar.ics')
def calendar_ics():
 c=db();rows=c.execute("SELECT title,url,starts_at,ends_at,description FROM opportunities WHERE status IN ('saved','applied') AND starts_at IS NOT NULL").fetchall();c.close()
 lines=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//Omen//Calendar//EN']
 for r in rows:
  dt=datetime.fromisoformat(r['starts_at'].replace('Z','+00:00')).strftime('%Y%m%dT%H%M%SZ')
  lines+=['BEGIN:VEVENT',f'UID:{r[1]}',f'DTSTART:{dt}',f'SUMMARY:{r[0]}',f'URL:{r[1]}','END:VEVENT']
 lines.append('END:VCALENDAR');from fastapi.responses import Response
 return Response('\r\n'.join(lines),media_type='text/calendar')
@app.get('/sources')
def sources():
    timelines=[u.strip() for u in os.getenv('X_PUBLIC_TIMELINES','').split(',') if u.strip()]
    return {'luma':{'enabled':True,'mode':'public_discover'},'x':{'enabled':bool(timelines),'mode':'public_embed','timelines':timelines,'browse_url':os.getenv('X_WEB_URL','')},'linkedin':{'enabled':bool(os.getenv('LINKEDIN_API_BASE_URL') and os.getenv('LINKEDIN_ACCESS_TOKEN')),'mode':'approved_api_or_manual','browse_url':os.getenv('LINKEDIN_WEB_URL','')}}

def run_event_pipeline():
    from opportunity_engine.collectors.luma import Luma
    from opportunity_engine.normalize import normalize
    from opportunity_engine.dedupe import dedupe
    from opportunity_engine.db import upsert, all_opportunities, set_score
    from opportunity_engine.score import score
    for raw in Luma().fetch():
        o=normalize(raw)
        if o.type not in ('event','hackathon','competition','program','fellowship','other'): continue
        upsert(o)
    for o in all_opportunities():
        if o.type in ('event','hackathon','competition','program','fellowship','other'):
            o,tokens=score(o);set_score(o)

@app.post('/pipeline/run',status_code=202)
def pipeline_run(tasks:BackgroundTasks):
    job=str(uuid.uuid4());tasks.add_task(run_event_pipeline);return {'job_id':job,'status':'started'}


class NoteBody(BaseModel):
 body:str
 frontmatter:dict|None=None
class NoteRename(BaseModel):
 model_config=ConfigDict(populate_by_name=True)
 src:str=Field(alias='from')
 to:str
def note_call(fn,*a):
 try: return fn(*a)
 except ValueError as e: raise HTTPException(400,str(e))
 except FileNotFoundError: raise HTTPException(404,'Note not found')
 except FileExistsError: raise HTTPException(409,'A note already exists at that path')
@app.get('/notes/tree')
def notes_tree(): return vault.tree()
@app.get('/notes/search')
def notes_search(q:str='',limit:int=20): return vault.search(q,limit)
@app.get('/notes/for/{entity}/{eid}')
def notes_for(entity:Literal['opportunity','person','org'],eid:str):
 try: return vault.get(vault.note_for(entity,eid))
 except (KeyError,ValueError): raise HTTPException(404,f'No {entity} {eid}')
@app.post('/notes/rename')
def notes_rename(p:NoteRename): return note_call(vault.rename,p.src,p.to)
@app.get('/notes')
def get_note(path:str): return note_call(vault.get,path)
@app.put('/notes')
def put_note(path:str,p:NoteBody): return note_call(vault.save,path,p.body,p.frontmatter)
@app.get('/graph')
def graph(include:str|None=None,stages:str='saved,applied,going,attended'):
 return focus.mark_graph(vault.graph([x.strip() for x in include.split(',') if x.strip()] if include else None,[x.strip() for x in stages.split(',') if x.strip()]))
class TaskToggle(BaseModel):
 path:str
 hash:str
 line:int|None=None
 done:bool|None=None
@app.get('/tasks')
def tasks(status:Literal['open','done']|None=None,due_before:str|None=None): return vault.task_list(status,due_before)
@app.patch('/tasks')
def toggle_task(p:TaskToggle):
 try: return note_call(vault.toggle_task,p.path,p.hash,p.done,p.line)
 except LookupError as e: raise HTTPException(409,str(e))
@app.get('/focus')
def focus_view(): return focus.compute()
