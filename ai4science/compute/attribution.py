"""Judge-verified reward attribution.

The provider's claimed metrics are advisory. Before any credit accrues,
the deterministic Physics Judge re-verifies the result on the workspace.
A verified pass yields a unit-less "credit" (1) bound to the provider's
wallet; the PWM-per-credit conversion is a later governance decision and
is intentionally NOT encoded here. The CLI never moves tokens.

Attribution records are appended to two places:
  - the **canonical aggregate ledger** (source of truth for ``credits``):
      ~/.config/ai4science/compute_attributions.jsonl
    (XDG_CONFIG_HOME-aware; override with AI4SCIENCE_COMPUTE_LEDGER)
  - a per-workspace local audit copy:
      <workspace>/reports/compute_attributions.jsonl

``credits`` reads the canonical ledger so it aggregates every verified job
regardless of which workspace each ran in. Reading with an explicit
workspace still returns just that workspace's local copy.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


def _utcnow() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def default_ledger_path() -> Path:
    """Canonical aggregate attribution ledger.

    ~/.config/ai4science/compute_attributions.jsonl, mirroring the provider
    registry's location. Override with AI4SCIENCE_COMPUTE_LEDGER; honors
    XDG_CONFIG_HOME.
    """
    override = os.environ.get("AI4SCIENCE_COMPUTE_LEDGER")
    if override:
        return Path(override)
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "ai4science" / "compute_attributions.jsonl"


def _append_jsonl(path: Path, record: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def _read_jsonl(path: Path) -> list[Dict[str, Any]]:
    if not path.exists():
        return []
    out: list[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _resolve_log(source: "Path | str | None") -> Path:
    """Map a read source to a JSONL path.

    None             → canonical aggregate ledger
    a directory      → that workspace's reports/compute_attributions.jsonl
    a file path      → that file directly
    """
    if source is None:
        return default_ledger_path()
    p = Path(source).resolve()
    if p.is_dir():
        return p / "reports" / "compute_attributions.jsonl"
    return p


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

    # Priced PWM: only a verified pass earns. Cost = wall-clock hours ×
    # the provider's USD/hour rate → PWM (points 12/13).
    from ai4science.compute.pricing import job_cost
    from ai4science.compute.registry import get_provider
    wall_s = (result_manifest or {}).get("provider", {}).get("wall_clock_s")
    prov = get_provider(job.get("provider_id") or "")
    rate = prov.price_usd_per_hour if prov else 0.0
    cost = job_cost(wall_s, rate) if credit else {"hours": 0.0, "usd": 0.0, "pwm": 0.0}

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
        "wall_clock_s": wall_s,
        "price_usd_per_hour": rate,
        "usd": cost["usd"],
        "pwm": cost["pwm"],
        "verified_at": _utcnow(),
        "note": ("verified-job credit + priced PWM (hours × provider rate ÷ $5). "
                 "On-chain settlement is platform-owned; the CLI moves no tokens."),
    }

    # Canonical aggregate ledger — source of truth for `credits`.
    _append_jsonl(default_ledger_path(), attribution)
    # Per-workspace local audit copy.
    _append_jsonl(workspace / "reports" / "compute_attributions.jsonl", attribution)

    return attribution


def read_attributions(source: "Path | str | None" = None) -> list[Dict[str, Any]]:
    """Read attribution records.

    ``source=None`` reads the canonical aggregate ledger (all jobs). Passing a
    workspace directory reads just that workspace's local copy (backward
    compatible with callers that pass a workspace path).
    """
    return _read_jsonl(_resolve_log(source))


def credit_summary(source: "Path | str | None" = None) -> Dict[str, int]:
    """Total verified-job credits per wallet.

    ``source=None`` aggregates the canonical ledger; a workspace path sums just
    that workspace's local copy.
    """
    totals: Dict[str, int] = {}
    for a in read_attributions(source):
        w = a.get("wallet_address") or "unknown"
        totals[w] = totals.get(w, 0) + int(a.get("credit", 0))
    return totals


def pwm_summary(source: "Path | str | None" = None) -> Dict[str, float]:
    """Total priced PWM earned per wallet from verified compute jobs."""
    totals: Dict[str, float] = {}
    for a in read_attributions(source):
        w = a.get("wallet_address") or "unknown"
        totals[w] = round(totals.get(w, 0.0) + (a.get("pwm") or 0.0), 6)
    return totals
