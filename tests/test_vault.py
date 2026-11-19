import pytest
from opportunity_engine import vault
from opportunity_engine.db import connect, upsert
from opportunity_engine.models import Opportunity

@pytest.fixture
def seeded(tmp_path):
 upsert(Opportunity(source='luma',source_id='evt-1',url='https://lu.ma/ai',title='AI Night: Toronto',org='Acme Labs',type='hackathon',starts_at='2026-12-01T18:00:00Z',score=82))
 c=connect();c.execute("UPDATE opportunities SET notes='Bring laptop',status='saved' WHERE id=1")
 c.execute("INSERT INTO people(name,role,organization,event_id,why,links,state) VALUES('Jane Doe','Founder','Acme Labs',1,'Runs the event','{}','want_to_meet')");c.commit();c.close()
 return tmp_path/'notes'
def db(sql): c=connect();r=c.execute(sql).fetchone();c.close();return r[0]
def write(root,rel,text): p=root/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text);return p

def test_wikilink_parsing():
 ls=vault.links('See [[Alpha]], [[Beta|the beta]], [[Gamma#Plan]] and [[Delta#H|d]]. `[[code]]`\n```\n[[fenced]]\n```\n[[#Local]]')
 assert [(l['target'],l['heading'],l['alias']) for l in ls]==[('Alpha',None,None),('Beta',None,'the beta'),('Gamma','Plan',None),('Delta','H','d'),('','Local',None)]

def test_resolution_rules():
 res=vault.Resolver(['People/Jane Doe.md','x/Foo.md','y/Foo.md','Goals.md','Orgs/Acme.md'])
 assert res('People/Jane Doe')=='People/Jane Doe.md' and res('jane doe')=='People/Jane Doe.md' and res('GOALS')=='Goals.md'
 assert res('x/Foo')=='x/Foo.md' and res('Foo') is None and res('Missing') is None and res('orgs/acme.md')=='Orgs/Acme.md'

def test_unresolved_links_are_reported(seeded):
 vault.save('Ideas.md','# Ideas\n[[Nowhere]] and [[Goals]]\n')
 assert vault.get('Ideas.md')['resolved']=={'Nowhere':None,'Goals':'Goals.md'}

@pytest.mark.parametrize('bad',['../x.md','/etc/x.md','a/../../x.md','notes.txt','.obsidian/a.md','a//b.md','C:/x.md','we:ird.md','x/[y].md',''])
def test_path_traversal_rejected(bad):
 with pytest.raises(ValueError):vault.safe(bad)

def test_symlink_escape_rejected(tmp_path):
 vault.ensure();(tmp_path/'outside').mkdir();(tmp_path/'notes/link').symlink_to(tmp_path/'outside')
 with pytest.raises(ValueError):vault.save('link/evil.md','x')
 assert not list((tmp_path/'outside').iterdir())

def test_goals_seeded_once_and_used(seeded,monkeypatch):
 assert vault.goals_path()==seeded/'Goals.md' and vault.goals()==[]
 write(seeded,'Goals.md','# Goals\n## Ship Omen\ntext\n## Meet founders #\n')
 assert vault.goals()==['Ship Omen','Meet founders'] and vault.goals_path().read_text().startswith('# Goals')

def test_stub_creation_is_idempotent(seeded):
 a=vault.note_for('opportunity',1);b=vault.note_for('opportunity','1')
 assert a==b=='Opportunities/AI Night Toronto.md' and len(list((seeded/'Opportunities').glob('*.md')))==1
 text=(seeded/a).read_text();note=vault.get(a)
 assert note['frontmatter']['omen_type']=='opportunity' and note['frontmatter']['omen_id']==1 and note['frontmatter']['score']==82
 assert '[[Orgs/Acme Labs]] · Tue Dec 1, 2026 · [Event page](https://lu.ma/ai)' in text and '## Notes\nBring laptop\n\n## Prep\n\n## Retro\n' in text
 person=vault.note_for('person',1);ptext=(seeded/person).read_text()
 assert person=='People/Jane Doe.md' and 'Founder at [[Orgs/Acme Labs]] · met at [[AI Night Toronto]]' in ptext and '## Why\nRuns the event\n\n## Notes\n\n## Follow-ups\n' in ptext
 assert vault.note_for('org','Acme Labs')=='Orgs/Acme Labs.md' and vault.note_for('org','Acme Labs')=='Orgs/Acme Labs.md'

def test_renamed_file_found_by_omen_id(seeded):
 a=vault.note_for('opportunity',1);(seeded/a).rename(seeded/'Opportunities/Renamed.md')
 assert vault.note_for('opportunity',1)=='Opportunities/Renamed.md' and len(list((seeded/'Opportunities').glob('*.md')))==1
 assert db("SELECT path FROM vault_notes WHERE entity='opportunity'")=='Opportunities/Renamed.md'

def test_rename_rewrites_links(seeded):
 vault.save('Old Name.md','# Old\n')
 vault.save('Ref.md','[[Old Name]] [[Old Name#Part|alias]] [[old name]] [[Other]] `[[Old Name]]`\n')
 vault.save('Deep/Ref2.md','---\ntags: [x]\n---\nsee [[Old Name.md]]\n')
 note=vault.rename('Old Name.md','Archive/New Name.md')
 assert note['path']=='Archive/New Name.md' and not (seeded/'Old Name.md').exists()
 assert (seeded/'Ref.md').read_text()=='[[New Name]] [[New Name#Part|alias]] [[New Name]] [[Other]] `[[Old Name]]`\n'
 assert (seeded/'Deep/Ref2.md').read_text()=='---\ntags: [x]\n---\nsee [[New Name]]\n'
 assert [b['path'] for b in note['backlinks']]==['Ref.md','Deep/Ref2.md'] or sorted(b['path'] for b in note['backlinks'])==['Deep/Ref2.md','Ref.md']
 vault.save('x/New Name.md','dup');vault.save('Ref3.md','[[Archive/New Name]]\n')
 vault.rename('Archive/New Name.md','Archive/Newer.md');assert (seeded/'Ref3.md').read_text()=='[[Archive/Newer]]\n'  # path-style links keep their form
 with pytest.raises(FileExistsError):vault.rename('Ref.md','Ref3.md')

def test_saving_opportunity_note_mirrors_notes(seeded):
 a=vault.note_for('opportunity',1);body=vault.get(a)['body']
 vault.save(a,body.replace('Bring laptop','Bring laptop and CV\n- ask about grants'))
 assert db('SELECT notes FROM opportunities WHERE id=1')=='Bring laptop and CV\n- ask about grants'
 assert vault.get(a)['frontmatter']['omen_id']==1  # frontmatter kept when only the body is saved
 p=seeded/a;p.write_text(p.read_text().replace('ask about grants','edited in Obsidian'));vault.index()
 assert db('SELECT notes FROM opportunities WHERE id=1').endswith('edited in Obsidian')

def test_db_changes_reach_existing_notes(seeded):
 a=vault.note_for('opportunity',1)
 c=connect();c.execute("UPDATE opportunities SET stage='registered',notes='from web' WHERE id=1");c.commit();c.close()
 vault.sync_entity('opportunity',1,'from web');text=(seeded/a).read_text()
 assert 'stage: registered' in text and '## Notes\nfrom web\n\n## Prep' in text
 assert vault.sync_entity('person',1) is None and not list((seeded/'People').glob('*.md'))  # never creates notes

def person(name,org,event=None):
 c=connect();cur=c.execute("INSERT INTO people(name,role,organization,event_id,why,links,state) VALUES(?,?,?,?,'','{}','met')",(name,'Engineer',org,event));c.commit();pid=cur.lastrowid;c.close();return pid

def test_plain_names_and_collisions(seeded):
 assert vault.note_for('person',1)=='People/Jane Doe.md' and vault.get('People/Jane Doe.md')['title']=='Jane Doe'
 assert vault.note_for('person',person('Jane Doe','Beta Corp'))=='People/Jane Doe (Beta Corp).md'
 vault.save('Ideas/Sam Lee.md','# Sam Lee, the musician\n')
 assert vault.note_for('person',person('Sam Lee','Acme Labs'))=='People/Sam Lee (Acme Labs).md'  # names stay unique vault-wide
 upsert(opp:=Opportunity(source='luma',source_id='evt-2',url='https://lu.ma/ai2',title='AI Night: Toronto',org='Acme Labs',type='event',starts_at='2026-12-08T18:00:00Z'))
 upsert(Opportunity(source='luma',source_id='evt-3',url='https://lu.ma/ai3',title='AI Night: Toronto',org='Other Org',type='event',starts_at='2026-12-15T18:00:00Z'))
 assert vault.note_for('opportunity',1)=='Opportunities/AI Night Toronto.md'
 assert vault.note_for('opportunity',2)=='Opportunities/AI Night Toronto 2026-12-08.md'  # same org repeating: date
 assert vault.note_for('opportunity',3)=='Opportunities/AI Night Toronto (Other Org).md'
 vault.save('Plan.md','[[Jane Doe]] [[Jane Doe (Beta Corp)]] [[AI Night Toronto 2026-12-08]]\n')
 assert vault.get('Plan.md')['resolved']=={'Jane Doe':'People/Jane Doe.md','Jane Doe (Beta Corp)':'People/Jane Doe (Beta Corp).md','AI Night Toronto 2026-12-08':'Opportunities/AI Night Toronto 2026-12-08.md'}
 assert not any(vault.HASHED.match(p.stem) for p in seeded.rglob('*.md'))
 assert [h['link'] for h in vault.search('jane doe')][:2]==['Jane Doe','Jane Doe (Beta Corp)']

def test_hashed_stubs_are_migrated(seeded):
 old='Opportunities/AI Night Toronto 3f2a1c.md'
 write(seeded,old,'---\nomen_type: opportunity\nomen_id: 1\n---\n# AI Night: Toronto\n\n## Notes\nkept\n')
 write(seeded,'People/Jane Doe 9be0c1.md','---\nomen_type: person\nomen_id: 1\n---\n# Jane Doe\nmet at [[AI Night Toronto 3f2a1c]]\n')
 write(seeded,'Ideas.md','[[AI Night Toronto 3f2a1c]] and [[Opportunities/AI Night Toronto 3f2a1c|the night]] with [[Jane Doe 9be0c1]]\n')
 write(seeded,'Opportunities/Renamed by me abc123.md','---\nomen_type: opportunity\nomen_id: 99\n---\n# Not in the DB\n')
 c=connect();c.execute("INSERT INTO vault_notes VALUES('opportunity','1',?)",(old,));c.commit();c.close()
 vault._migrated.clear();idx=vault.index()
 assert 'Opportunities/AI Night Toronto.md' in idx and 'People/Jane Doe.md' in idx and old not in idx and 'Opportunities/Renamed by me abc123.md' in idx
 assert (seeded/'Ideas.md').read_text()=='[[AI Night Toronto]] and [[Opportunities/AI Night Toronto|the night]] with [[Jane Doe]]\n'
 assert 'met at [[AI Night Toronto]]' in (seeded/'People/Jane Doe.md').read_text() and '## Notes\nkept' in (seeded/'Opportunities/AI Night Toronto.md').read_text()
 assert db("SELECT path FROM vault_notes WHERE entity='opportunity' AND entity_id='1'")=='Opportunities/AI Night Toronto.md'
 assert vault.note_for('opportunity',1)=='Opportunities/AI Night Toronto.md' and vault.note_for('person',1)=='People/Jane Doe.md'
