import re
from .models import RawItem, Opportunity
from .llm import complete_json

def normalize(item: RawItem) -> Opportunity:
    raw=item.raw; event=raw.get('event',{})
    description=event.get('description') or item.description
    place=event.get('geo_address_info') or event.get('location') or {}
    loc=item.location or (place.get('city') or place.get('address') or '') if isinstance(place,dict) else item.location
    typ='internship' if 'intern' in item.title.lower() else 'event'
    starts=event.get('start_at'); ends=event.get('end_at')
    extracted,tokens=complete_json(f"Extract missing opportunity fields as JSON with type, description, location, eligibility, compensation, tags. Use only evidence; empty values if unknown.\nTitle: {item.title}\nOrg: {item.org}\n{description[:1000]}") if not description or not loc else (None,0)
    if extracted:
        typ=extracted.get('type',typ); description=description or extracted.get('description',''); loc=loc or extracted.get('location','')
    return Opportunity(source=item.source,source_id=item.source_id,url=item.url,title=item.title,org=item.org,type=typ if typ in {'event','hackathon','internship','job','program','fellowship','competition','other'} else 'other',description=description,location=loc,is_remote='remote' in loc.lower(),starts_at=starts,ends_at=ends,deadline=raw.get('deadline'),eligibility=(extracted or {}).get('eligibility',''),compensation=(extracted or {}).get('compensation',''),tags=(extracted or {}).get('tags',[]),raw=raw)
