import pytest
from fastapi.testclient import TestClient
from api.main import app
from opportunity_engine.db import connect, upsert
from opportunity_engine.models import Opportunity

@pytest.fixture
def client(tmp_path):
 for i,(title,status) in enumerate([('AI Night','saved'),('Robotics Demo','new'),('Untracked','new')],1):
  upsert(Opportunity(source='luma',source_id=f'evt-{i}',url=f'https://lu.ma/{i}',title=title,org='Acme' if i<3 else 'Other',type='event',score=40+i*10,status=status))
 c=connect();c.execute("INSERT INTO people(name,role,organization,event_id,why,links,state) VALUES('Jane Doe','Founder','Acme',2,'Hosts it','{}','want_to_meet')");c.commit();c.close()
 (tmp_path/'notes').mkdir();(tmp_path/'notes/Goals.md').write_text('# Goals\n\n## Ship Omen\n\n## Meet founders\n')
 return TestClient(app)

def test_notes_endpoints(client):
 assert client.put('/notes',params={'path':'Ideas/Plan.md'},json={'body':'# Plan\nTalk to [[Jane Doe]] about [[Goals#Ship Omen]] and [[Someday]].\n'}).status_code==200
 tree=client.get('/notes/tree').json();names=[x['name'] for x in tree['children']]
 assert {'Goals','Ideas','People','Opportunities','Orgs'}<=set(names)
 note=client.get('/notes',params={'path':'Ideas/Plan.md'}).json()
 assert note['title']=='Plan' and note['resolved']=={'Jane Doe':None,'Goals':'Goals.md','Someday':None}
 person=client.get('/notes/for/person/1').json();assert person['path']=='People/Jane Doe.md' and person['frontmatter']['omen_type']=='person'
 assert client.get('/notes',params={'path':'Ideas/Plan.md'}).json()['resolved']['Jane Doe']=='People/Jane Doe.md'
 assert [b['path'] for b in client.get('/notes',params={'path':person['path']}).json()['backlinks']]==['Ideas/Plan.md']
 goals=client.get('/notes',params={'path':'Goals.md'}).json();assert goals['backlinks'][0]['snippet'].startswith('Talk to [[Jane Doe]]')
 hits=client.get('/notes/search',params={'q':'jane'}).json();assert hits[0]['path']==person['path'] and hits[0]['link']=='Jane Doe'
 assert client.get('/notes/search',params={'q':'someday'}).json()[0]['path']=='Ideas/Plan.md'
 moved=client.post('/notes/rename',json={'from':'Ideas/Plan.md','to':'Ideas/Roadmap.md'}).json();assert moved['path']=='Ideas/Roadmap.md'
 assert client.get('/notes',params={'path':'../x.md'}).status_code==400 and client.get('/notes',params={'path':'Nope.md'}).status_code==404
 assert client.get('/notes/for/opportunity/999').status_code==404 and client.post('/notes/rename',json={'from':'Goals.md','to':'Ideas/Roadmap.md'}).status_code==409

def test_patch_writes_through_and_notes_section_mirrors(client):
 note=client.get('/notes/for/opportunity/1').json()
 client.patch('/opportunities/1',json={'stage':'going','notes':'from tracker'})
 again=client.get('/notes',params={'path':note['path']}).json()
 assert again['frontmatter']['stage']=='going' and '## Notes\nfrom tracker\n' in again['body']
 client.put('/notes',params={'path':note['path']},json={'body':again['body'].replace('from tracker','from editor')})
 assert client.get('/opportunities/1').json()['notes']=='from editor'

def test_today_and_profile_read_vault_goals(client):
 assert client.get('/today').json()['goals']==['Ship Omen','Meet founders'] and '## Ship Omen' in client.get('/profile').json()['goals']

def test_graph_nodes_and_link_kinds(client):
 client.put('/notes',params={'path':'Plan.md'},json={'body':'[[Goals#Ship Omen]] [[AI Night]] [[Missing note]] [[Orgs/Acme]]\n'})
 client.get('/notes/for/opportunity/1')
 g=client.get('/graph').json();by={n['id']:n for n in g['nodes']};kinds={l['kind'] for l in g['links']}
 types={n['type'] for n in g['nodes']}
 assert {'goal','person','org','opportunity','note','unresolved'}<=types and {'wikilink','attended','org','goal'}<=kinds
 titles={n['label'] for n in g['nodes'] if n['type']=='opportunity'}
 assert titles=={'AI Night','Robotics Demo'}  # saved one, plus the one Jane attended; never the whole table
 assert by['Goals.md']['type']=='goal' and 'Goals.md#Ship Omen' in by and by['Orgs/Acme.md']['path'] is None
 assert any(l['kind']=='goal' and l['source']=='Plan.md' and l['target']=='Goals.md#Ship Omen' for l in g['links'])
 assert any(l['kind']=='wikilink' and l['source']=='Plan.md' and l['target']=='Orgs/Acme.md' for l in g['links'])
 assert any(l.get('unresolved') and l['target']=='Missing note.md' for l in g['links'])
 opp=next(n for n in g['nodes'] if n['label']=='AI Night');assert opp['score']==50 and opp['stage']=='saved' and opp['path']
 robo=next(n for n in g['nodes'] if n['label']=='Robotics Demo');assert robo['path'] is None and robo['entity_id']==2
 only=client.get('/graph',params={'include':'goals,notes'}).json()
 assert {n['type'] for n in only['nodes']}<={'goal','note','unresolved'}
