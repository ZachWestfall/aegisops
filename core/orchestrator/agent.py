import os
import asyncio
from typing import Any, Dict, Tuple
from datetime import datetime
from core.cost.ledger import CostLedger
from core.orchestrator.planner import llm_plan

# ---- Impact/Confidence heuristics ----

def _get_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except Exception:
        return default

# Invoices
INV_DISCOUNT_RATE = _get_float("INV_DISCOUNT_RATE", 0.015)
INV_CONF_BASE     = _get_float("INV_CONF_BASE", 0.55)
INV_CONF_BIGAMT   = _get_float("INV_CONF_BIGAMT", 0.15)
INV_CONF_VENDOR   = _get_float("INV_CONF_VENDOR", 0.10)
INV_CONF_ZERO     = _get_float("INV_CONF_ZERO", -0.20)

# Expense reports
EXP_REVIEW_RATE   = _get_float("EXP_REVIEW_RATE", 0.05)
EXP_REVIEW_CAP    = _get_float("EXP_REVIEW_CAP", 50.0)
EXP_RECEIPT_BONUS = _get_float("EXP_RECEIPT_BONUS", 1.0)
EXP_CONF_BASE     = _get_float("EXP_CONF_BASE", 0.50)
EXP_CONF_3REC     = _get_float("EXP_CONF_3REC", 0.10)
EXP_CONF_200TOT   = _get_float("EXP_CONF_200TOT", 0.10)

# POs
PO_BASE_RATE      = _get_float("PO_BASE_RATE", 0.005)
PO_OVERB_RATE     = _get_float("PO_OVERB_RATE", 0.015)
PO_CONF_BASE      = _get_float("PO_CONF_BASE", 0.55)
PO_CONF_RISK_DEPT = _get_float("PO_CONF_RISK_DEPT", 0.10)
PO_CONF_OVERB     = _get_float("PO_CONF_OVERB", 0.15)
PO_CONF_BIGAMT    = _get_float("PO_CONF_BIGAMT", 0.10)
PO_CONF_ZERO      = _get_float("PO_CONF_ZERO", -0.20)


def _clip(v: float, lo: float, hi: float) -> float:
    return max(lo, min(v, hi))


def _estimate_impact(event_type: str, payload: Dict[str, Any]) -> Tuple[float, float, str]:
    """Returns (impact_usd, confidence, explanation)."""
    try:
        et = (event_type or "").strip().lower()

        if et == "ap_invoice_created":
            amt = float(payload.get("amount", 0) or 0)
            vendor = payload.get("vendor")
            rate = float(payload.get("assumed_discount_rate", INV_DISCOUNT_RATE) or INV_DISCOUNT_RATE)
            impact = round(amt * rate, 2)
            conf = INV_CONF_BASE
            if amt > 5000: conf += INV_CONF_BIGAMT
            if vendor:     conf += INV_CONF_VENDOR
            if amt == 0:   conf += INV_CONF_ZERO
            conf = _clip(conf, 0.05, 0.95)
            explanation = (
                f"Invoice: impact = amount × rate = {amt:.2f} × {rate:.4f} = ${impact:.2f}. "
                f"Confidence base {INV_CONF_BASE:.2f}"
                f"{' + big-amount' if amt > 5000 else ''}"
                f"{' + vendor' if vendor else ''}"
                f"{' - zero-amount' if amt == 0 else ''} → {conf:.2f}."
            )
            return max(0.0, impact), conf, explanation

        if et == "expense_report_submitted":
            total = float(payload.get("total", 0) or 0)
            receipts = int(payload.get("receipts_count", 0) or 0)
            base = min(total * EXP_REVIEW_RATE, EXP_REVIEW_CAP)
            impact = round(base + receipts * EXP_RECEIPT_BONUS, 2)
            conf = EXP_CONF_BASE
            if receipts >= 3: conf += EXP_CONF_3REC
            if total > 200:   conf += EXP_CONF_200TOT
            conf = _clip(conf, 0.05, 0.90)
            explanation = (
                f"Expense: impact = min({EXP_REVIEW_RATE:.2%}×total, ${EXP_REVIEW_CAP:.2f}) + "
                f"${EXP_RECEIPT_BONUS:.2f}×receipts = min({total:.2f}×{EXP_REVIEW_RATE:.2f}, "
                f"{EXP_REVIEW_CAP:.2f}) + {EXP_RECEIPT_BONUS:.2f}×{receipts} = ${impact:.2f}. "
                f"Confidence base {EXP_CONF_BASE:.2f}"
                f"{' + >=3 receipts' if receipts >= 3 else ''}"
                f"{' + total>200' if total > 200 else ''} → {conf:.2f}."
            )
            return max(0.0, impact), conf, explanation

        if et == "po_submitted":
            amt = float(payload.get("amount", 0) or 0)
            dept = (payload.get("department") or "").lower()
            over_budget_flag = bool(payload.get("over_budget", False))
            rate = PO_OVERB_RATE if over_budget_flag else PO_BASE_RATE
            impact = round(amt * rate, 2)
            conf = PO_CONF_BASE
            if dept in {"marketing","it","sales"}: conf += PO_CONF_RISK_DEPT
            if over_budget_flag: conf += PO_CONF_OVERB
            if amt > 20000: conf += PO_CONF_BIGAMT
            if amt == 0:    conf += PO_CONF_ZERO
            conf = _clip(conf, 0.05, 0.95)
            explanation = (
                f"PO: impact = amount × rate = {amt:.2f} × {rate:.4f} = ${impact:.2f}. "
                f"Confidence base {PO_CONF_BASE:.2f}"
                f"{' + risk-dept' if dept in {'marketing','it','sales'} else ''}"
                f"{' + over-budget' if over_budget_flag else ''}"
                f"{' + big-amount' if amt > 20000 else ''}"
                f"{' - zero-amount' if amt == 0 else ''} → {conf:.2f}."
            )
            return max(0.0, impact), conf, explanation

        fields = len(payload or {})
        impact = round(10.0 + 2.0 * fields, 2)
        conf = _clip(0.40 + 0.05 * fields, 0.05, 0.80)
        explanation = (
            f"Default: impact = 10 + 2×fields = 10 + 2×{fields} = ${impact:.2f}. "
            f"Confidence grows with fields count → {conf:.2f}."
        )
        return max(0.0, impact), conf, explanation

    except Exception as e:
        return 15.00, 0.35, f"Fallback due to error: {e!r}"


class AgentOrchestrator:
    def __init__(self):
        self.cost = CostLedger()

    async def plan(self, event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        plan_obj = await llm_plan(event_type, payload)
        steps = [
            (s.model_dump() if hasattr(s, "model_dump") else s.dict())
            for s in plan_obj.steps
        ]
        return {
            "created_at": datetime.utcnow().isoformat(),
            "steps": steps,
            "event_type": event_type,
            "payload": payload,
        }

    async def execute(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        await asyncio.sleep(0.05)
        event_type = plan.get("event_type") if isinstance(plan, dict) else None
        payload = plan.get("payload", {}) if isinstance(plan, dict) else {}
        delta_usd, confidence, explanation = _estimate_impact(event_type or "", payload or {})
        action = {
            "action_type": "notify",
            "channel": "log",
            "message": "Stub action executed (replace with real connector call)"
        }
        result = {
            "executed": True,
            "action": action,
            "impact": {
                "delta_usd": float(delta_usd),
                "confidence": float(round(confidence, 2)),
                "explanation": explanation
            }
        }
        self.cost.record_action(result)
        return result
