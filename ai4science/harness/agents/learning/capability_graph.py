from __future__ import annotations
import json
from pathlib import Path


def record_measurement(store_path, topic: str, score: float, n: int, timestamp) -> dict:
    """Append one capability measurement (JSONL). timestamp is explicit
    (caller stamps real time; tests pass a fixed value)."""
    measurement = {"topic": topic, "score": float(score), "n": int(n),
                   "timestamp": timestamp}
    path = Path(store_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(measurement) + "\n")
    return measurement


def history(store_path, topic: str) -> list:
    """A topic's measurements in recorded order."""
    path = Path(store_path)
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("topic") == topic:
            out.append(rec)
    return out
