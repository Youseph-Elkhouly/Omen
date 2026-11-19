"""Minimal OpenAI-compatible JSON interface. No network calls without an API key."""
import json, os, httpx
BASE=os.getenv('LLM_BASE_URL','https://api.openai.com/v1')
MODEL=os.getenv('LLM_MODEL','gpt-4o-mini')
def complete_json(prompt: str) -> tuple[dict|None,int]:
    key=os.getenv('LLM_API_KEY')
    if not key: return None,0
    r=httpx.post(BASE+'/chat/completions',headers={'Authorization':f'Bearer {key}'},json={'model':MODEL,'messages':[{'role':'user','content':prompt}],'response_format':{'type':'json_object'}},timeout=60); r.raise_for_status()
    d=r.json(); return json.loads(d['choices'][0]['message']['content']),d.get('usage',{}).get('total_tokens',0)
