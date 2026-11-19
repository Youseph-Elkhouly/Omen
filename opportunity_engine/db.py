import json, sqlite3, os
from pathlib import Path
from .models import Opportunity
DB_PATH = Path(os.getenv('OE_DB_PATH', 'opportunities.sqlite3')).expanduser()

def connect():
    c=sqlite3.connect(DB_PATH); c.row_factory=sqlite3.Row
    c.execute('''CREATE TABLE IF NOT EXISTS opportunities (
    id INTEGER PRIMARY KEY, source TEXT NOT NULL, source_id TEXT NOT NULL, url TEXT NOT NULL,
    title TEXT NOT NULL, org TEXT, type TEXT, description TEXT, location TEXT, is_remote INTEGER,
    starts_at TEXT, ends_at TEXT, deadline TEXT, eligibility TEXT, compensation TEXT, tags TEXT,
    raw TEXT, first_seen TEXT, last_seen TEXT, score INTEGER, score_reason TEXT, status TEXT DEFAULT 'new',
    UNIQUE(source, source_id))''')
    c.commit(); return c

def upsert(o: Opportunity):
    c=connect(); data=o.model_dump(mode="json"); keys=list(data); keys.remove("id")
    updates=", ".join(f"{k}=excluded.{k}" for k in keys if k not in ("source","source_id","first_seen"))
    c.execute(f"INSERT INTO opportunities ({','.join(keys)}) VALUES ({','.join('?' for _ in keys)}) ON CONFLICT(source,source_id) DO UPDATE SET {updates}", [json.dumps(data[k]) if isinstance(data[k],(dict,list)) else data[k] for k in keys]); c.commit(); c.close()

def all_opportunities(new_only=False):
    c=connect(); rows=c.execute("SELECT * FROM opportunities" + (" WHERE status='new'" if new_only else "")).fetchall(); c.close()
    out=[]
    for r in rows:
        d=dict(r); d['tags']=json.loads(d['tags'] or '[]'); d['raw']=json.loads(d['raw'] or '{}'); d['is_remote']=bool(d['is_remote'])
        out.append(Opportunity.model_validate(d))
    return out

def set_score(o: Opportunity):
    c=connect(); c.execute("UPDATE opportunities SET score=?, score_reason=? WHERE source=? AND source_id=?",(o.score,o.score_reason,o.source,o.source_id)); c.commit(); c.close()
