from typing import List, Literal
from pydantic import BaseModel, ValidationError
import os, httpx, json, re

class Step(BaseModel):
    name: Literal["retrieve","analyze","decide","act","verify"]
    desc: str

class Plan(BaseModel):
    steps: List[Step]

def _extract_json(text: str) -> str:
    """Try to extract a JSON block from LLM output; fall back to raw text."""
    m = re.search(r"```json\s*(.*?)```", text, flags=re.DOTALL|re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m = re.search(r"```\s*(\{[\s\S]*?\})\s*```", text)
    if m:
        return m.group(1).strip()
    return text.strip()

async def llm_plan(event_type: str, payload: dict) -> Plan:
    """Call an LLM to propose a structured 5-step plan. Falls back to static plan."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return Plan(steps=[
            Step(name="retrieve", desc="Load related records and thresholds"),
            Step(name="analyze",  desc="Assess risk/cost impact"),
            Step(name="decide",   desc="Select the safest and most cost-effective action"),
            Step(name="act",      desc="Draft connector call or message"),
            Step(name="verify",   desc="Log action and expected savings"),
        ])

    prompt = f"""
You are an operations planning assistant.
Given an event_type and a payload (keys shown), produce a STRICT JSON object with this schema:

{{
  "steps": [
    {{ "name": "retrieve", "desc": "..." }},
    {{ "name": "analyze",  "desc": "..." }},
    {{ "name": "decide",   "desc": "..." }},
    {{ "name": "act",      "desc": "..." }},
    {{ "name": "verify",   "desc": "..." }}
  ]
}}

- Use exactly these 5 steps in this order.
- Keep descriptions concise but specific to the event.
- Do not include any text before or after the JSON.

event_type: {event_type}
payload_keys: {list(payload.keys())}
"""

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "gpt-4o-mini",
                    "temperature": 0,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"]
            candidate = _extract_json(content)
            try:
                return Plan.model_validate_json(candidate)
            except ValidationError:
                data = json.loads(candidate)
                return Plan(**data)
    except Exception:
        return Plan(steps=[
            Step(name="retrieve", desc="Load related records and thresholds"),
            Step(name="analyze",  desc="Assess risk/cost impact"),
            Step(name="decide",   desc="Select the safest and most cost-effective action"),
            Step(name="act",      desc="Draft connector call or message"),
            Step(name="verify",   desc="Log action and expected savings"),
        ])