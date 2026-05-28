"""Judge-verified reward attribution.

The provider's claimed metrics are advisory. Before any credit accrues,
the deterministic Physics Judge re-verifies the result on the workspace.
A verified pass yields a unit-less "credit" (1) bound to the provider's
wallet; the PWM-per-credit conversion is a later governance decision and
is intentionally NOT encoded here. The CLI never moves tokens.

Attribution records are appended to an off-chain log:
  <workspace>/reports/compute_attributions.jsonl
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, Optional


def _utcnow() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def verify_and_attribute(*, workspace: Path, job: Dict[str, Any],
                         result_manifest: Optional[Dict[str, Any]] = None,
                         benchmark: Optional[str] = None) -> Dict[str, Any]:
    """Run the judge on the workspace and write an attribution record.

    Returns the attribution dict. ``credit`` is 1 iff the judge's
    final_decision is 'pass'. needs_review / fail → credit 0.
    """
    from ai4science.judge.cassi import judge_cassi

    workspace = Path(workspace).resolve()
    report = judge_cassi(workspace, benchmark=benchmark)
    decision = report.get("final_decision", "unknown")
    credit = 1 if decision == "pass" else 0

    attribution = {
        "job_id": job.get("job_id"),
        "provider_id": job.get("provider_id"),
        "wallet_address": job.get("wallet_address"),
        "benchmark_id": job.get("benchmark_id") or (
            report.get("benchmark_file")),
        "certificate_hash": (result_manifest or {}).get("certificate_hash"),
        "judge_decision": decision,
        "silent_failure": report.get("silent_failure"),
        "credit": credit,
        "verified_at": _utcnow(),
        "note": ("verified-job credit (unit-less; PWM conversion deferred to "
                 "governance). On-chain settlement is platform-owned; the CLI "
                 "moves no tokens."),
    }

    log = workspace / "reports" / "compute_attributions.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as f:
        f.write(json.dumps(attribution) + "\n")

    return attribution


def read_attributions(workspace: Path) -> list[Dict[str, Any]]:
    log = Path(workspace).resolve() / "reports" / "compute_attributions.jsonl"
    if not log.exists():
        return []
    out = []
    for line in log.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def credit_summary(workspace: Path) -> Dict[str, int]:
    """Total verified-job credits per wallet."""
    totals: Dict[str, int] = {}
    for a in read_attributions(workspace):
        w = a.get("wallet_address") or "unknown"
        totals[w] = totals.get(w, 0) + int(a.get("credit", 0))
    return totals
