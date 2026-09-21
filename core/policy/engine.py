from pydantic import BaseModel
from typing import Optional

class PolicyDecision(BaseModel):
    allowed: bool
    reason: Optional[str] = None
    required_approval: Optional[str] = None

class PolicyEngine:
    def evaluate(self, event_type: str, payload: dict) -> PolicyDecision:
        # Example: deny if amount exceeds threshold in demo mode
        amount = payload.get("amount", 0)
        if isinstance(amount, (int, float)) and amount > 1_000_000:
            return PolicyDecision(allowed=False, reason="Amount exceeds demo threshold; require CFO approval")
        return PolicyDecision(allowed=True)