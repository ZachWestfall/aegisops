import json
import httpx

async def send_slack(webhook_url: str, text: str) -> dict:
    payload = {"text": text}
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(webhook_url, json=payload)
        return {"status_code": r.status_code, "body": r.text}
