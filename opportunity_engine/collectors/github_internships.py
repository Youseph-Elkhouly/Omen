import httpx, re
from .base import Collector
from ..models import RawItem
REPOS=["SimplifyJobs/Summer2027-Internships","SimplifyJobs/New-Grad-Positions"]
class GitHubInternships:
    def __init__(self, repos=REPOS, client=None): self.repos=repos; self.client=client or httpx.Client(timeout=30,headers={"User-Agent":"OpportunityEngine/0.1 (personal student tool)"})
    def fetch(self):
        out=[]
        for repo in self.repos:
            url=f"https://raw.githubusercontent.com/{repo}/dev/README.md"
            r=self.client.get(url)
            if r.status_code==404: r=self.client.get(url.replace('/dev/','/main/'))
            r.raise_for_status()
            # Parse markdown tables conservatively, preserving links and closed marker.
            for line in r.text.splitlines():
                if not line.startswith('|') or '---' in line or '🔒' in line: continue
                cells=[x.strip() for x in line.strip('|').split('|')]
                if len(cells)<4 or not re.search(r'\[([^]]+)\]\((https?://[^)]+)\)',line): continue
                links=re.findall(r'\[([^]]+)\]\((https?://[^)]+)\)',line)
                company=cells[0]; title=cells[1] if len(cells)>1 else 'Internship'
                name=re.search(r'\[([^]]+)\]\(https?://[^)]+\)',company) or re.search(r'\*\*([^*]+)\*\*',company)
                org=name.group(1) if name else re.sub(r'[*🎓🔥🛂🇺🇸]','',company).strip()
                title=re.sub(r'\[([^]]+)\]\([^)]+\)',r'\1',title).replace('**','').strip()
                loc=cells[2] if len(cells)>2 else ''
                apply=next((u for _,u in links if 'simplify.jobs' not in u), links[-1][1])
                sid=apply.rstrip('/').split('/')[-1]
                out.append(RawItem(source='github_internships',source_id=sid,url=apply,title=title,org=org,location=loc,raw={'repo':repo,'row':line}))
        return out
