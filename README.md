# AegisOps

A policy-gated control plane for automated financial operations. Business events go in; every proposed action is checked against spend policy, its cost impact is estimated, and the decision is written to an immutable audit ledger before anything executes.

---

## The problem

Most "automate your back office" tooling is built the wrong way round. It optimises for the action firing, and treats governance as logging you bolt on afterwards. That is backwards for anything touching money. In accounts payable, procurement, or expense management, the interesting question is never *can the system send the invoice* — it is **who authorised this, against which threshold, what did it cost, and can you prove it six months from now.**

I wanted to build the opposite: a system where the *gate* is the product and the connectors are the replaceable part. An action that cannot be explained and attributed should not execute, and a system that cannot show its reasoning after the fact is not auditable no matter how good its outcomes are.

## What it does

Every event enters through one endpoint and passes through four stages:

1. **Policy evaluation** — checked against configurable spend thresholds. A violation short-circuits immediately; no plan is built, no action runs, nothing is written to the ledger.
2. **Planning** — an allowed event produces an explicit five-step plan (retrieve → analyze → decide → act → verify) so the intended sequence is inspectable *before* execution rather than reconstructed from logs afterwards.
3. **Impact estimation** — each event type carries a savings heuristic with an attached confidence score and a written explanation of where the number came from.
4. **Ledger write** — the event, payload, action, estimated impact, confidence, and explanation are persisted to SQLite as an append-only audit record.

Supported events: `ap_invoice_created`, `expense_report_submitted`, `po_submitted`.

### Verified behaviour

Real output from the running service (see [Running it](#running-it) to reproduce):

**A $250,000 invoice against a $100,000 policy limit is refused outright.**
```json
{ "status": "blocked", "reason": "Invoice amount 250000.0 exceeds policy limit" }
```
Nothing reaches the ledger. The gate runs before the planner, not alongside it.

**An allowed $4,200 expense report is estimated, explained, and recorded.**
```json
{
  "id": 1,
  "event_type": "expense_report_submitted",
  "delta_usd": 252.0,
  "confidence": 0.7,
  "explanation": "6% policy enforcement & duplicate catch on $4200.00.",
  "dry_run": false
}
```

**Dry-run mode plans and estimates without recording.** `POST /trigger2?dry_run=true` returns the full plan and impact estimate but deliberately skips the ledger write, so a policy change can be tested against real payloads without polluting the audit trail.

## Architecture

```
POST /trigger
     │
     ▼
evaluate_policy()  ──── violation ───▶  { status: "blocked", reason }   (terminal)
     │ allowed
     ▼
build_plan()          five explicit steps, inspectable before execution
     │
     ▼
execute_plan()        ← connector boundary (currently stubbed)
     │
     ▼
estimate_impact()     delta_usd + confidence + written explanation
     │
     ▼
write_ledger()  ──▶  SQLite  ──▶  GET /ledger
```

**Stack:** FastAPI · SQLAlchemy 2.0 · Pydantic v2 · SQLite · Uvicorn, plus a dependency-free HTML/CSS/JS dashboard served at `/ui`.

| Endpoint | Purpose |
|---|---|
| `POST /plan` | Policy check and plan only — never executes, never records |
| `POST /trigger` | Full pipeline: gate → plan → execute → record |
| `POST /trigger2?dry_run=` | Same pipeline with the ledger write suppressed |
| `GET /ledger?n=` | Read back the audit trail, newest first |
| `GET /health` | Liveness plus a real database round-trip (`SELECT 1`) |

## What I built

- **The policy gate as a hard precondition.** `evaluate_policy()` returns a decision object that short-circuits the request. I deliberately did not implement this as middleware or a post-hoc check, because a gate you can forget to call is not a gate. There is exactly one path to execution and it runs through the evaluator.
- **Confidence and explanation as first-class ledger columns.** An estimate without a stated basis is a number someone will later treat as fact. Every `delta_usd` is stored beside the `confidence` and the sentence explaining the derivation, so a reviewer reading the ledger months later sees the reasoning, not just the figure.
- **Dry-run that suppresses persistence rather than execution.** Because the connector layer is stubbed, "don't execute" would have been meaningless. The useful thing to make optional was the *audit write*, letting you rehearse policy changes against production-shaped payloads without corrupting the record.
- **Auth that fails open in dev and closed in production.** If `API_KEY` is unset the service runs unauthenticated for local work; once set, every mutating endpoint requires a matching `X-API-Key`. One environment variable is the entire difference.
- **Health check that actually checks.** `/health` executes a real query rather than returning a hardcoded `ok`, so it fails when the database is unreachable — which is the only time the endpoint matters.

## What I learned

- **Designing the audit record first changed the whole architecture.** I initially wrote the executor first and treated the ledger as output. That produced entries I could not interpret a week later, because the *reasoning* had been discarded and only the outcome survived. Rebuilding around "what does the audit row need to contain" forced confidence and explanation to become things the estimator had to produce, not optional extras — and that reshaped the function signatures all the way up.
- **A stub is only honest if the seam is real.** `execute_plan()` returns a placeholder action, but it sits at a genuine interface boundary with the same shape a live connector would have. That distinction matters: the surrounding gate, estimator, and ledger are fully exercised by the stub, so swapping in a real Slack or Salesforce call changes one function and nothing else.
- **Heuristics must be labelled as heuristics.** The 6% / 1.5% / 1% savings rates are *assumptions I chose*, not measurements. Storing a confidence score beside each one was the mechanism that kept me honest — it made the uncertainty structural rather than something living in my head.
- **Where I was wrong:** I shipped a `/debug/headers` endpoint during development that echoed the submitted API key back to the caller. It was convenient for testing auth and it is exactly the kind of thing that survives into production. I removed it while preparing this repository. Debug affordances that handle credentials need an expiry date from the moment they are written.

## Why it mattered

I built this because the governance problem interested me more than the automation problem. Deciding whether an action is permitted, estimating what it costs, recording who authorised it against which threshold, and being able to defend that record afterwards is the same problem structure as program oversight and acquisition management — the domain I am pursuing as a Space Force acquisitions officer. Writing it as software forced a precision about thresholds, authority, and auditability that reading about the subject never did.

## Running it

Requires Python 3.9+ (developed and verified on 3.9.6).

```bash
git clone <this-repo> && cd aegisops
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

export PYTHONPATH=.
uvicorn apps.api.main:app --reload --port 8000
```

Then open <http://127.0.0.1:8000/ui/> for the dashboard, or <http://127.0.0.1:8000/docs> for the OpenAPI console.

Reproduce the blocked-invoice example above:
```bash
curl -X POST http://127.0.0.1:8000/trigger \
  -H "Content-Type: application/json" \
  -d '{"event_type":"ap_invoice_created","payload":{"vendor":"Acme","amount":250000},"user_id":"demo"}'
```

Run the tests:
```bash
PYTHONPATH=. pytest tests/ -q
```

### Configuration

| Variable | Default | Effect |
|---|---|---|
| `API_KEY` | unset | Unset disables auth (dev). Set to require `X-API-Key` on all mutating endpoints. |
| `POLICY_MAX_INVOICE` | `100000` | Invoice amount above which `ap_invoice_created` is blocked. |
| `DB_URL` | `sqlite:///aegisops.db` | SQLAlchemy connection string. |

## Status and limitations

This is a working control plane with a stubbed execution layer. Stated plainly, so nothing here is oversold:

- **Connectors are not implemented.** `execute_plan()` returns a placeholder. The `connectors/` directory contains Slack and Salesforce client scaffolding that is not yet wired into the pipeline.
- **The savings figures are heuristics, not measured outcomes.** `delta_usd` reflects the assumed rates documented above applied to the payload amount. No claim is made that these rates are empirically correct; the confidence scores exist precisely to mark that uncertainty.
- **The policy engine covers two rules.** An invoice ceiling and a negative-total rejection. It is a demonstrated pattern, not a complete policy language.
- **Single-node SQLite, no migrations.** Appropriate for the current scope; would need Postgres and Alembic before any real deployment.
- **Test coverage is thin** — one health-check test. The endpoint behaviour documented above was verified manually and is reproducible via the curl commands, but is not yet codified as a regression suite.

## License

MIT — see [LICENSE](LICENSE).
