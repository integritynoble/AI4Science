from __future__ import annotations
import json
import re
from ai4science.harness.agents.work.extract import parse_work_action  # reuse step protocol

_FENCED = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)

__all__ = ["parse_work_action", "parse_coverage_proposal"]


def parse_coverage_proposal(text) -> list | None:
    """Parse the first valid fenced propose_coverage block -> list[str], else None."""
    for m in _FENCED.finditer(text or ""):
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict) or data.get("action") != "propose_coverage":
            continue
        pts = data.get("coverage_points")
        if isinstance(pts, list) and pts and all(isinstance(p, str) and p for p in pts):
            return pts
    return None
