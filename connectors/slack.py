python - <<'PY'
code = r'''
import json
import httpx

async def send_slack(webhook_url: str, text: str) -> dict:
    payload = {"text": text}
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(webhook_url, json=payload)
        return {"status_code": r.status_code, "body": r.text}
'''
import os
os.makedirs('core/connectors', exist_ok=True)
open('core/connectors/__init__.py','a').close()
with open('core/connectors/slack.py','w', encoding='utf-8') as f:
    f.write(code.strip()+'\n')
print('✅ core/connectors/slack.py created')
PY