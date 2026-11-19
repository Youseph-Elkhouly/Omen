from opportunity_engine.collectors.github_internships import GitHubInternships
class Resp:
 status_code=200
 text='| Company | Role | Location | Application | Age |\n|---|---|---|---|---|\n| **[Acme](https://acme.com)** | Software Intern | Toronto | [Apply](https://jobs.acme.com/123) | 2d |\n| **[Closed](https://closed.com)** | SWE Intern 🔒 | US | Apply | 2d |'
 def raise_for_status(self): pass
class Client:
 def get(self,*a,**k): return Resp()
def test_github_fixture_parser():
 items=GitHubInternships(repos=['demo/repo'],client=Client()).fetch()
 assert len(items)==1
 assert items[0].org=='Acme' and items[0].title=='Software Intern'
