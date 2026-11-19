import os,smtplib
from datetime import date
from email.mime.text import MIMEText
from pathlib import Path
from .db import all_opportunities

def render(items):
 grouped={}
 for o in sorted(items,key=lambda x:(-(x.score or 0),x.deadline.isoformat() if x.deadline else '9999')):grouped.setdefault(o.type,[]).append(o)
 chunks=['<!doctype html><meta charset="utf-8"><title>Omen Digest</title><h1>Omen — '+date.today().isoformat()+'</h1>']
 for typ,ops in grouped.items():
  chunks.append(f'<h2>{typ.title()}</h2><ul>')
  for o in ops: chunks.append(f'<li><b><a href="{o.url}">{o.title}</a></b> — {o.org} | {o.starts_at or o.deadline or "Date unknown"} | {o.location or "Location unknown"} | {o.score or 0}/100<br>{o.score_reason}</li>')
  chunks.append('</ul>')
 return '\n'.join(chunks)
def send(limit=15):
 items=all_opportunities(new_only=True);items=sorted(items,key=lambda o:-(o.score or 0))[:limit];html=render(items)
 host=os.getenv('SMTP_HOST')
 if host:
  msg=MIMEText(html,'html');msg['Subject']='Omen daily digest';msg['From']=os.environ['SMTP_FROM'];msg['To']=os.environ['SMTP_TO']
  with smtplib.SMTP(host,int(os.getenv('SMTP_PORT','587'))) as s:
   if os.getenv('SMTP_USER'):s.starttls();s.login(os.getenv('SMTP_USER'),os.getenv('SMTP_PASSWORD',''))
   s.send_message(msg)
 else:
  p=Path('digests')/f'{date.today().isoformat()}.html';p.parent.mkdir(exist_ok=True);p.write_text(html);return p
 return None
