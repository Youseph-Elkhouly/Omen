import os, time
from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient
from api.main import app
from opportunity_engine import focus, vault
from opportunity_engine.db import connect, upsert
from opportunity_engine.models import Opportunity

NOW=datetime.now(timezone.utc)
def iso(days): return (NOW+timedelta(days=days)).strftime('%Y-%m-%dT%H:%M:%SZ')
def day(days): return (NOW+timedelta(days=days)).date().isoformat()
def opp(sid,title,**kw): upsert(Opportunity(**{'source':'luma','source_id':sid,'url':f'https://lu.ma/{sid}','title':title,'org':'Acme','type':'event'}|kw))
def sql(q,*a): c=connect();cur=c.execute(q,a);c.commit();r=cur.lastrowid;c.close();return r
def person(name,state,event): return sql("INSERT INTO people(name,role,organization,event_id,why,links,state) VALUES(?,'','',?,'','{}',?)",name,event,state)
def write(rel,text,age_days=None):
 p=vault.root()/rel;p.parent.mkdir(parents=True,exist_ok=True);open(p,'w',encoding='utf-8',newline='').write(text)
 if age_days is not None: t=(NOW-timedelta(days=age_days)).timestamp();os.utime(p,(t,t))
 return p

def test_task_parsing():
 ts=vault.tasks(f'## Prep\n- [ ] Book train 📅 2026-11-20\n  - [x] nested [due:: 2026-11-19]\n\t* [ ] tabbed\n```md\n- [ ] in a fence\n```\n~~~\n- [ ] tilde fence\n~~~\n`- [ ] inline code`\n1. [X] numbered\n- [] not a task\n- [ ] after [[Jane Doe]] [[Goals#Ship]]\n')
 assert [(t['text'][:12],t['done'],t['due'],t['indent']) for t in ts]==[('Book train 📅',False,'2026-11-20',0),('nested [due:',True,'2026-11-19',2),('tabbed',False,None,4),('numbered',True,None,0),('after [[Jane',False,None,0)]
 assert {t['section'] for t in ts}=={'Prep'} and [l['target'] for l in ts[-1]['links']]==['Jane Doe','Goals']
 vault.ensure();write('Plan.md','- [ ] a 📅 2026-01-02\n- [x] b\n')
 assert [t['text'] for t in vault.task_list('open')]==['a 📅 2026-01-02'] and [t['text'] for t in vault.task_list('done')]==['b']
 assert vault.task_list(due_before='2026-01-03')[0]['path']=='Plan.md' and vault.task_list(due_before='2026-01-02')==[]

def test_toggle_rewrites_exactly_one_line():
 vault.ensure();text='---\ntags: [x]\n---\n# Plan\n- [ ] same\r\nkeep [ ] this\n- [ ] same\n- [x] done\n'
 p=write('Plan.md',text);second=[t for t in vault.tasks(vault.split(text)[1]) if t['text']=='same'][1]
 t=vault.toggle_task('Plan.md',second['hash'],line=second['line'])
 after=open(p,encoding='utf-8',newline='').read()
 assert t['done'] and after==text.replace('- [ ] same\n- [x] done','- [x] same\n- [x] done')
 assert sum(a!=b for a,b in zip(after.split('\n'),text.split('\n')))==1
 vault.toggle_task('Plan.md',t['hash'],done=False,line=t['line']);assert open(p,encoding='utf-8',newline='').read()==text
 with pytest.raises(LookupError):vault.toggle_task('Plan.md','nope')

def test_follow_up_rule():
 opp('old','Old meetup',starts_at=iso(-6),ends_at=iso(-5));opp('new','Yesterday meetup',starts_at=iso(-2),ends_at=iso(-1))
 quiet=person('Quiet Met','met',1);person('Too Soon','met',2);person('Never Met','want_to_meet',1)
 edited=person('Wrote Since','met',1);planned=person('Has Plan','met',1);due=person('Due Now','want_to_meet',2)
 vault.ensure()
 write('People/Wrote Since.md',f'---\nomen_type: person\nomen_id: {edited}\n---\n# Wrote Since\nGreat chat.\n',age_days=1)
 write('People/Has Plan.md',f'---\nomen_type: person\nomen_id: {planned}\n---\n# Has Plan\n## Follow-ups\n- [ ] Send deck 📅 {day(4)}\n',age_days=10)
 write('People/Due Now.md',f'---\nomen_type: person\nomen_id: {due}\n---\n# Due Now\n## Follow-ups\n- [ ] Email 📅 {day(-1)}\n',age_days=10)
 f=focus.compute()['follow_ups'];by={x['title']:x for x in f}
 assert set(by)=={'Quiet Met','Due Now'}
 assert by['Quiet Met']['path']=='People/Quiet Met.md' and not by['Quiet Met']['exists'] and by['Quiet Met']['reason']=='Met at Old meetup; nothing since'
 assert by['Due Now']['exists'] and by['Due Now']['due']==day(-1) and by['Due Now']['hash']

def test_retro_and_deadline_flags():
 opp('a','Went already',starts_at=iso(-3));opp('b','Wrote retro',starts_at=iso(-3));opp('c','Still ahead',starts_at=iso(5));opp('d','No note',starts_at=iso(-2))
 opp('e','Apply soon',deadline=iso(3));opp('f','Applied already',deadline=iso(3));opp('g','Far deadline',deadline=iso(10));opp('h','Never saved',deadline=iso(2))
 for i,stage in [(1,'going'),(2,'attended'),(3,'going'),(4,'attended')]: sql("UPDATE opportunities SET stage=?,status='applied' WHERE id=?",stage,i)
 for i in (5,7): sql("UPDATE opportunities SET stage='saved',status='saved' WHERE id=?",i)
 sql("UPDATE opportunities SET stage='applied',status='applied' WHERE id=6")
 vault.ensure()
 write('Opportunities/Went already.md','---\nomen_type: opportunity\nomen_id: 1\n---\n# Went already\n## Notes\n## Retro\n\n')
 write('Opportunities/Wrote retro.md','---\nomen_type: opportunity\nomen_id: 2\n---\n# Wrote retro\n## Retro\nGood food, weak talks.\n')
 f=focus.compute()
 assert [(x['title'],x['exists']) for x in f['needs_retro']]==[('Went already',True),('No note',False)] and f['needs_retro'][1]['path']=='Opportunities/No note.md'
 assert [x['title'] for x in f['deadlines']]==['Apply soon']

def test_goal_progress_stale_and_empty():
 opp('a','Hack night',starts_at=iso(-3));sql("UPDATE opportunities SET stage='going',status='applied' WHERE id=1");person('Ana','met',1)
 vault.ensure();write('Goals.md','# Goals\n## Ship Omen\n## Meet founders\n## Learn Rust\n')
 write('Opportunities/Hack night.md','---\nomen_type: opportunity\nomen_id: 1\n---\n# Hack night\nFor [[Goals#Ship Omen]].\n- [ ] Demo\n- [x] Register\n',age_days=2)
 write('Plan.md','- [ ] Write post [[Goals#ship omen]]\n',age_days=1)
 write('Old.md','Coffee with founders for [[Goals#Meet founders]]\n',age_days=20)
 g={x['heading']:x for x in focus.compute()['goals']}
 assert g['Ship Omen']['flag'] is None and g['Ship Omen']['counts']=={'opportunities':{'going':1},'people_met':1,'tasks_open':2,'tasks_done':1,'notes':2}
 assert g['Meet founders']['flag']=='stale' and g['Learn Rust']['flag']=='empty' and g['Learn Rust']['last_activity'] is None
 assert g['Ship Omen']['last_activity'][:10]==day(-1)

def test_new_stub_templates():
 opp('a','Hack night',starts_at=iso(10),ends_at=iso(10),deadline='2026-12-20T00:00:00Z');person('Ana','met',1)
 c=connect();c.execute("INSERT INTO people(name,role,organization,event_id,why,links,state) VALUES('Bo','','',NULL,'','{}','met')");c.commit();c.close()
 assert '## Prep\n- [ ] Apply 📅 2026-12-20\n' in (vault.root()/vault.note_for('opportunity',1)).read_text()
 assert f'## Follow-ups\n- [ ] Follow up with Ana 📅 {day(13)}\n' in (vault.root()/vault.note_for('person',1)).read_text()
 assert (vault.root()/vault.note_for('person',2)).read_text().endswith('## Follow-ups\n- [ ] Follow up with Bo\n')

def test_focus_endpoint_shape_timing_and_stage_validation():
 for i in range(450): opp(f'e{i}',f'Event {i}',starts_at=iso(i%30-15),deadline=iso(i%9))
 sql("UPDATE opportunities SET status='saved' WHERE id%7=0");sql("UPDATE opportunities SET stage='going',status='applied' WHERE id%11=0")
 for i in range(30): person(f'Person {i}','met' if i%2 else 'want_to_meet',i+1)
 vault.ensure();write('Goals.md','# Goals\n'+''.join(f'## Goal {i}\n' for i in range(6)))
 for i in range(80): write(f'Notes/n{i}.md',f'# Note {i}\nSee [[Goals#Goal {i%6}]] and [[Person {i%30}]]\n'+''.join(f'- [ ] task {j} 📅 {day(j-5)}\n' for j in range(6)))
 client=TestClient(app);client.get('/focus')
 started=time.perf_counter();r=client.get('/focus');ms=(time.perf_counter()-started)*1000
 body=r.json();assert set(body)=={'overdue_tasks','due_soon','deadlines','needs_retro','follow_ups','goals'}
 assert all('path' in x for k,v in body.items() for x in v) and body['overdue_tasks'][0]['kind']=='task' and len(body['goals'])==6
 assert ms<50,f'/focus took {ms:.1f} ms'
 assert client.patch('/opportunities/1',json={'stage':'registered'}).status_code==422
 assert client.patch('/opportunities/1',json={'stage':'going'}).json()['status']=='applied'
 t=body['overdue_tasks'][0];done=client.patch('/tasks',json={'path':t['path'],'hash':t['hash'],'line':t['line']}).json()
 assert done['done'] and client.patch('/tasks',json={'path':t['path'],'hash':'missing'}).status_code==409
 assert len(client.get('/tasks',params={'status':'open','due_before':day(0)}).json())==80*5-1

def test_graph_marks_stale_goals_and_overdue_notes():
 vault.ensure();write('Goals.md','# Goals\n## Fresh\n## Old\n');write('a.md','[[Goals#Fresh]]\n- [ ] late 📅 2020-01-01\n');write('b.md','[[Goals#Old]]\n',age_days=30)
 g=TestClient(app).get('/graph').json();by={n['id']:n for n in g['nodes']}
 assert by['Goals.md#Old']['flag']=='stale' and 'flag' not in by['Goals.md#Fresh'] and by['a.md']['warn'] and 'warn' not in by['b.md']
