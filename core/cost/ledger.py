import json
from datetime import datetime
from pathlib import Path
from typing import Optional

LEDGER_PATH = Path(".aegisops_cost_ledger.jsonl")

class CostLedger:
    def __init__(self, path: Optional[Path] = None):
        self.path = path or LEDGER_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record_action(self, result: dict):
        entry = {
            "ts": datetime.utcnow().isoformat(),
            "result": result,
        }
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")