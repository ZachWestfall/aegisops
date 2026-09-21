import os, json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Any, Dict

from fastapi import FastAPI, Header, HTTPException, Depends, Response, Query
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# --- DB (SQLite via SQLAlchemy) ---
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, Text, text
from sqlalchemy.orm import sessionmaker, declarative_base, Session

APP_VERSION = "0.1.1"
ROOT_DIR = Path(__file__).resolve().parents[2]  # ~/Documents/aegisops
DB_URL = os.getenv("DB_URL", f"sqlite:///{ROOT_DIR / 'aegisops.db'}")

engine = create_engine(
    DB_URL,
    echo=False,
    future=True,
    connect_args={"check_same_thread": False} if DB_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()

class LedgerEntry(Base):
    __tablename__ = "ledger_entries"
    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    event_type = Column(String(120), index=True, nullable=False)
    user_id = Column(String(120), nullable=True)
    payload = Column(Text, nullable=True)             # JSON string
    action_type = Column(String(60), nullable=True)   # e.g., notify/ticket/adjustment
    channel = Column(String(60), nullable=True)       # log/slack/jira/...
    message = Column(Text, nullable=True)
    delta_usd = Column(Float, default=0.0)
    confidence = Column(Float, default=0.5)
    explanation = Column(Text, nullable=True)
    dry_run = Column(Boolean, default=False)

Base.metadata.create_all(engine)

def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Auth helper ---
def require_api_key(x_api_key: Optional[str] = Header(default=None)):
    expected = os.getenv("API_KEY")
    # If no API_KEY set, auth is OFF (dev mode)
    if not expected:
        return True
    if not x_api_key or x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return True

# --- Planner / Policy / Executor ---
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def build_plan(event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    steps = [
        {"name": "retrieve", "desc": "Load related records and thresholds"},
        {"name": "analyze",  "desc": "Assess risk/cost impact"},
        {"name": "decide",   "desc": "Select the safest and most cost-effective action"},
        {"name": "act",      "desc": "Draft connector call or message"},
        {"name": "verify",   "desc": "Log action and expected savings"},
    ]
    return {
        "created_at": now_iso(),
        "event_type": event_type,
        "steps": steps,
        "payload_preview": {k: payload.get(k) for k in (list(payload.keys())[:6])} if isinstance(payload, dict) else None,
    }

class _Decision:
    def __init__(self, allowed: bool, reason: Optional[str] = None):
        self.allowed = allowed
        self.reason = reason

def evaluate_policy(event_type: str, payload: Dict[str, Any]) -> _Decision:
    if event_type == "ap_invoice_created":
        amt = float(payload.get("amount", 0) or 0)
        if amt > float(os.getenv("POLICY_MAX_INVOICE", "100000")):
            return _Decision(False, f"Invoice amount {amt} exceeds policy limit")
    if event_type == "expense_report_submitted":
        total = float(payload.get("total", 0) or 0)
        if total < 0:
            return _Decision(False, "Negative total not allowed")
    return _Decision(True)

def estimate_impact(event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    delta, conf, expl = 0.0, 0.6, "No savings heuristic applied."
    if event_type == "expense_report_submitted":
        total = float(payload.get("total", 0) or 0)
        delta = round(max(0.0, total * 0.06), 2)
        conf = 0.70
        expl = f"6% policy enforcement & duplicate catch on ${total:.2f}."
    elif event_type == "ap_invoice_created":
        amt = float(payload.get("amount", 0) or 0)
        delta = round(max(0.0, amt * 0.015), 2)
        conf = 0.65
        expl = f"1.5% early-payment/price-check leverage on ${amt:.2f}."
    elif event_type == "po_submitted":
        amt = float(payload.get("amount", 0) or 0)
        delta = round(max(0.0, amt * 0.01), 2)
        conf = 0.55
        expl = f"1% vendor normalization opportunity on ${amt:.2f}."
    return {"delta_usd": delta, "confidence": conf, "explanation": expl}

def execute_plan(plan: Dict[str, Any], payload: Dict[str, Any], dry_run: bool) -> Dict[str, Any]:
    action = {"action_type": "notify", "channel": "log", "message": "Stub action executed (replace with real connector call)"}
    impact = estimate_impact(plan["event_type"], payload)
    return {"executed": (not dry_run), "action": action, "impact": impact, "dry_run": dry_run}

def write_ledger(db: Session, user_id: Optional[str], event_type: str, payload: Dict[str, Any], result: Dict[str, Any]):
    imp = result.get("impact", {}) if isinstance(result, dict) else {}
    action = result.get("action", {}) if isinstance(result, dict) else {}
    entry = LedgerEntry(
        event_type=event_type,
        user_id=user_id,
        payload=json.dumps(payload, ensure_ascii=False),
        action_type=action.get("action_type"),
        channel=action.get("channel"),
        message=action.get("message"),
        delta_usd=float(imp.get("delta_usd") or 0.0),
        confidence=float(imp.get("confidence") or 0.0),
        explanation=imp.get("explanation"),
        dry_run=bool(result.get("dry_run", False)),
    )
    db.add(entry)
    db.commit()

app = FastAPI(
    title="AegisOps API",
    version=APP_VERSION,
    swagger_ui_parameters={"tryItOutEnabled": True, "defaultModelsExpandDepth": -1},
)

from starlette.middleware.base import BaseHTTPMiddleware

class WellKnownSilencer(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.url.path.startswith("/.well-known"):
            return Response(status_code=204)
        return await call_next(request)

app.add_middleware(WellKnownSilencer)

# CORS (safe even if UI is same-origin)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static UI at /ui/
UI_DIR = Path(__file__).parent / "ui"
app.mount("/ui", StaticFiles(directory=UI_DIR, html=True), name="ui")

class Trigger(BaseModel):
    event_type: str = Field(..., examples=["ap_invoice_created", "expense_report_submitted", "po_submitted"])
    payload: Dict[str, Any] = Field(default_factory=dict)
    user_id: Optional[str] = Field(default=None, examples=["web-ui", "zac"])

@app.get("/")
def root():
    return {"ok": True, "ui": "/ui/", "docs": "/docs", "health": "/health", "version": APP_VERSION}

@app.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    return {"status": "ok", "db": db_ok, "version": APP_VERSION}

@app.post("/plan", dependencies=[Depends(require_api_key)])
def plan_only(t: Trigger):
    decision = evaluate_policy(t.event_type, t.payload)
    if not decision.allowed:
        return {"status": "blocked", "reason": decision.reason}
    plan = build_plan(t.event_type, t.payload)
    return {"status": "ok", "plan": plan}

@app.post("/trigger", dependencies=[Depends(require_api_key)])
def trigger_event(t: Trigger, db: Session = Depends(get_db)):
    decision = evaluate_policy(t.event_type, t.payload)
    if not decision.allowed:
        return {"status": "blocked", "reason": decision.reason}
    plan = build_plan(t.event_type, t.payload)
    result = execute_plan(plan, t.payload, dry_run=False)
    write_ledger(db, t.user_id, t.event_type, t.payload, result)
    return {"status": "ok", "plan": plan, "result": result}

@app.post("/trigger2", dependencies=[Depends(require_api_key)])
def trigger_event2(t: Trigger, dry_run: bool = Query(False), db: Session = Depends(get_db)):
    decision = evaluate_policy(t.event_type, t.payload)
    if not decision.allowed:
        return {"status": "blocked", "reason": decision.reason}
    plan = build_plan(t.event_type, t.payload)
    result = execute_plan(plan, t.payload, dry_run=dry_run)
    if not dry_run:
        write_ledger(db, t.user_id, t.event_type, t.payload, result)
    return {"status": "ok", "plan": plan, "result": result, "dry_run": dry_run}

@app.get("/ledger", dependencies=[Depends(require_api_key)])
def read_ledger(n: int = Query(50, ge=1, le=500), db: Session = Depends(get_db)):
    q = db.query(LedgerEntry).order_by(LedgerEntry.id.desc()).limit(n).all()
    def row(e: LedgerEntry):
        return {
            "id": e.id,
            "created_at": e.created_at.isoformat() if e.created_at else None,
            "event_type": e.event_type,
            "user_id": e.user_id,
            "delta_usd": e.delta_usd,
            "confidence": e.confidence,
            "explanation": e.explanation,
            "dry_run": e.dry_run,
            "action": {"action_type": e.action_type, "channel": e.channel, "message": e.message},
            "payload": json.loads(e.payload) if e.payload else None,
        }
    entries = [row(e) for e in q]
    return {"count": len(entries), "entries": entries}
from fastapi.responses import FileResponse
@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(UI_DIR / "logo.svg", media_type="image/svg+xml")

# --- Silence Chrome DevTools probe(s) under /.well-known ---
@app.get("/.well-known/appspecific/com.chrome.devtools.json", include_in_schema=False)
def _chrome_probe():
    # Return 204 No Content so the probe doesn't spam 404s in logs
    return Response(status_code=204)

@app.get("/.well-known/{rest:path}", include_in_schema=False)
def _well_known(rest: str):
    # Catch-all for any other .well-known requests
    return Response(status_code=204)
