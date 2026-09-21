# Placeholder for S3/DuckDB/Parquet helpers. Implement when ready.
from pathlib import Path

def save_parquet_like(path: str, rows: list[dict]):  # pragma: no cover
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    # demo write as JSONL for now
    with open(p, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(str(r)+"\n")
