import re, hashlib
from urllib.parse import urlsplit,urlunsplit,parse_qsl,urlencode
from .models import Opportunity

def canonical_url(url):
 p=urlsplit(url); q=[(k,v) for k,v in parse_qsl(p.query) if not k.lower().startswith('utm_') and k.lower() not in {'ref','source'}]
 return urlunsplit((p.scheme.lower(),p.netloc.lower(),p.path.rstrip('/'),urlencode(q),'')).lower()
def fingerprint(o): return hashlib.sha256(f"{o.title.lower()}|{o.org.lower()}|{o.url}".encode()).hexdigest()
def similar(a,b):
 norm=lambda s: re.sub(r'[^a-z0-9]','',s.lower())
 return norm(a.title)==norm(b.title) and norm(a.org)==norm(b.org)
def dedupe(items):
 seen=set(); out=[]
 for o in items:
  o.url=canonical_url(o.url)
  if o.url in seen or any(similar(o,x) for x in out): continue
  seen.add(o.url); out.append(o)
 return out
