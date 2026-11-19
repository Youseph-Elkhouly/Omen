import hashlib,json,os,sqlite3
from datetime import datetime,timezone
from pathlib import Path
from .models import Opportunity
from .llm import complete_json
from .vault import goals_path
CACHE=Path('.score_cache.sqlite3')
def profile_text():
 p=Path('opportunity_engine/profile/resume.json'); g=goals_path()
 return (p.read_text() if p.exists() else '{}')+'\nGOALS\n'+(g.read_text() if g.exists() else '')
def hard_filter(o):
 now=datetime.now(timezone.utc)
 for d in [o.deadline,o.ends_at]:
  if d and d.replace(tzinfo=d.tzinfo or timezone.utc)<now:return 'Deadline or event has passed'
 text=(o.eligibility+' '+o.description).lower()
 if 'phd only' in text or 'us citizens only' in text:return 'Eligibility mismatch'
 return ''
def score(o):
 reason=hard_filter(o)
 if reason:o.score=0;o.score_reason=reason;return o,0
 prof=profile_text(); ph=hashlib.sha256(prof.encode()).hexdigest(); oh=hashlib.sha256(o.model_dump_json().encode()).hexdigest()
 c=sqlite3.connect(CACHE);c.execute('CREATE TABLE IF NOT EXISTS cache(k TEXT PRIMARY KEY, score INTEGER, reason TEXT)'); key=oh+ph
 row=c.execute('SELECT score,reason FROM cache WHERE k=?',(key,)).fetchone()
 if row:o.score,o.score_reason=row; c.close();return o,0
 result,tokens=complete_json(f"Judge fit 0-100 against this profile and goals. Return JSON score, reason (one sentence tied to a specific goal), urgency low/med/high.\nPROFILE:{prof[:3000]}\nOPPORTUNITY:{o.model_dump_json()[:2500]}")
 if result: o.score=max(0,min(100,int(result.get('score',0))));o.score_reason=result.get('reason','')
 else:
  
  try: skills=json.loads(prof.split('\nGOALS\n',1)[0]).get('skills',[])
  except (json.JSONDecodeError, AttributeError): skills=[]
  matched=sum(1 for s in skills if s.lower() in (o.title+' '+o.description).lower())
  o.score=min(55,25+matched*10);o.score_reason='Fallback keyword fit; add an LLM_API_KEY and complete profile goals for personalized ranking.'
 c.execute('INSERT OR REPLACE INTO cache VALUES(?,?,?)',(key,o.score,o.score_reason));c.commit();c.close();return o,tokens
