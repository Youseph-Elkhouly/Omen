import os,time,httpx
from .base import Collector
from ..models import RawItem
class Luma:
    ENDPOINT='https://api.lu.ma/discover/get-paginated-events'
    def __init__(self,queries=None,client=None,sleep=time.sleep):
        configured=queries if queries is not None else os.getenv('LUMA_QUERIES','')
        self.queries=[q.strip() for q in (configured.split(',') if isinstance(configured,str) else configured) if q.strip()] or ['']
        self.client=client or httpx.Client(timeout=30,headers={'User-Agent':os.getenv('COLLECTOR_USER_AGENT','Omen/0.1')})
        self.sleep=sleep
    def fetch(self):
        out=[];seen=set()
        for query in self.queries:
            cursor=None
            while True:
                params={'limit':50}
                if query: params['query']=query
                if cursor:params['pagination_cursor']=cursor
                for attempt in range(4):
                    try:
                        r=self.client.get(self.ENDPOINT,params=params);r.raise_for_status();data=r.json();break
                    except httpx.HTTPError:
                        if attempt==3: raise
                        self.sleep(2**attempt)
                for row in data.get('entries',[]):
                    e=row.get('event',{}); sid=e.get('api_id') or row.get('api_id')
                    if not sid or sid in seen:continue
                    seen.add(sid);url='https://lu.ma/'+(e.get('url') or sid)
                    out.append(RawItem(source='luma',source_id=sid,url=url,title=e.get('name','Untitled event'),org=(row.get('calendar') or {}).get('name',''),description=e.get('description',''),location=(e.get('geo_address_info') or {}).get('city',''),raw=row))
                cursor=data.get('next_cursor') or data.get('pagination_cursor')
                if not cursor or not data.get('entries'):break
                self.sleep(1)
        return out
