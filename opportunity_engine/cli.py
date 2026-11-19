import typer
from .collectors.github_internships import GitHubInternships
from .collectors.luma import Luma
from .normalize import normalize
from .dedupe import dedupe
from .db import upsert,all_opportunities,set_score
from .score import score
from .digest import send
app=typer.Typer(no_args_is_help=True)
def collect_sources(sources):
 raw=[]
 for source in sources: raw.extend(source.fetch())
 normalized=dedupe([normalize(x) for x in raw])
 for o in normalized:upsert(o)
 typer.echo(f'Collected/upserted {len(normalized)} opportunities')
@app.command()
def collect(): collect_sources([GitHubInternships()])
@app.command("score")
def score_cmd():
 total=0
 for o in all_opportunities():
  o,t=score(o);total+=t;set_score(o)
 typer.echo(f'Scored opportunities; LLM tokens this run: {total}')
@app.command()
def digest(limit:int=15):
 path=send(limit)
 typer.echo(f'Wrote {path}' if path else 'Sent digest via SMTP')
@app.command()
def run():
 collect_sources([GitHubInternships(),Luma()]);score_cmd();digest()
if __name__=='__main__':app()
