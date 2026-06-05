from __future__ import annotations

import os
from pathlib import Path
from typing import List

from ai4science.harness import transport
from ai4science.harness.tools.base import Tool

# Genesis CASSI solutions are authored by the third founder; users' PWM for using
# them is paid to this address (charging itself is deferred to the economics layer).
GENESIS_SOLUTION_PROVIDER = "0xde81b29E42F95C92c9A4Dc78882d0F05D2C81A29"


class CassiError(Exception):
    pass


def _contained(workspace: Path, rel: str) -> Path:
    target = (Path(workspace) / rel).resolve()
    try:
        target.relative_to(Path(workspace).resolve())
    except ValueError:
        raise CassiError(f"path escapes the workspace: {rel}")
    return target


_IMAGING_KEYWORDS = ("cassi", "spectral", "imaging", "hyperspectral", "snapshot")


def _chain_bases():
    """[(label, base_url)] for each configured chain + whether mainnet is set."""
    mn = os.environ.get("PWM_EXPLORER_BASE_MAINNET", "").rstrip("/")
    tn = os.environ.get("PWM_EXPLORER_BASE_TESTNET",
                        os.environ.get("PWM_EXPLORER_BASE",
                                       "https://explorer.physicsworldmodel.org/api")).rstrip("/")
    bases = []
    if mn:
        bases.append(("mainnet", mn))
    bases.append(("testnet", tn))
    return bases, bool(mn)


def _flatten_solutions(ld) -> list:
    out = []
    if isinstance(ld, dict):
        for key in ("reference", "reference_advanced"):
            s = ld.get(key)
            if isinstance(s, dict):
                out.append({**s, "_kind": key})
        for k in ("solutions", "submissions", "entries", "ranks"):
            v = ld.get(k)
            if isinstance(v, list):
                out.extend(x for x in v if isinstance(x, dict))
    return out


def _imaging_benchmark_ids(bdata) -> list:
    items = bdata.get("genesis") or bdata.get("benchmarks") or [] if isinstance(bdata, dict) else bdata
    ids = []
    for b in (items or []):
        if not isinstance(b, dict):
            continue
        hay = " ".join(str(b.get(k, "")) for k in ("benchmark_id", "title", "category")).lower()
        if any(kw in hay for kw in _IMAGING_KEYWORDS):
            bid = b.get("benchmark_id") or b.get("id")
            if bid:
                ids.append(bid)
    return ids


def cassi_solutions_multichain(benchmark: str = ""):
    """(solutions, notes). Each solution dict is tagged chain="mainnet"|"testnet"."""
    bases, has_mainnet = _chain_bases()
    sols, notes = [], []
    for label, base in bases:
        try:
            bids = [benchmark] if benchmark else _imaging_benchmark_ids(
                transport.get_json(f"{base}/benchmarks"))
            for bid in bids:
                ld = transport.get_json(f"{base}/leaderboard/{bid}")
                for s in _flatten_solutions(ld):
                    sols.append({**s, "benchmark_id": bid, "chain": label})
        except Exception as exc:
            notes.append(f"{label}: unavailable ({exc})")
    if not has_mainnet:
        notes.append("mainnet: not configured (set PWM_EXPLORER_BASE_MAINNET)")
    return sols, notes


def _solutions_tool() -> Tool:
    def _list(workspace, *, benchmark: str = "") -> str:
        try:
            sols, notes = cassi_solutions_multichain(benchmark)
            lines = []
            for s in sols:
                label = s.get("label") or s.get("name") or s.get("_kind") or "?"
                lines.append(f"[{s['chain']}] {s.get('benchmark_id','?')} {label} "
                             f"score_q={s.get('score_q')} psnr={s.get('psnr_db')}")
            body = "\n".join(lines) if lines else "(no registered imaging solutions found)"
            if notes:
                body += "\n" + "\n".join(notes)
            return body[:20000]
        except Exception as exc:
            return f"[cassi error] {exc}"

    return Tool(
        name="cassi_solutions",
        description=("List ALL registered computational-imaging solutions across "
                     "mainnet and testnet, each marked by chain. Optional benchmark "
                     "id narrows to one leaderboard; empty lists all imaging benchmarks."),
        parameters={"type": "object", "properties": {
            "benchmark": {"type": "string"}}, "required": []},
        func=_list, mutating=False)


def _forward_check_tool() -> Tool:
    def _check(workspace, *, recon: str, mask: str, measurement: str) -> str:
        try:
            import numpy as np
            from ai4science.judge.cassi.forward import cassi_forward
            x = np.load(_contained(Path(workspace), recon))
            m = np.load(_contained(Path(workspace), mask))
            y = np.load(_contained(Path(workspace), measurement))
            y_hat = cassi_forward(x, m)
            if y_hat.shape != y.shape:
                return (f"[cassi error] measurement shape {y.shape} != forward output "
                        f"{y_hat.shape}")
            r = float(np.linalg.norm(y_hat - y) / (np.linalg.norm(y) + 1e-12))
            hint = "consistent" if r < 0.05 else ("marginal" if r < 0.2 else "inconsistent")
            return f"forward residual ||Phi x - y|| / ||y|| = {r:.4f} ({hint})"
        except CassiError as exc:
            return f"[cassi error] {exc}"
        except Exception as exc:
            return f"[cassi error] {exc}"

    return Tool(
        name="cassi_forward_check",
        description=("Local CASSI physics sanity check: relative forward residual "
                     "||Phi x - y|| / ||y|| for a reconstruction. Args are workspace "
                     ".npy paths: recon (H,W,C), mask (H,W), measurement (H,W+C-1)."),
        parameters={"type": "object", "properties": {
            "recon": {"type": "string"}, "mask": {"type": "string"},
            "measurement": {"type": "string"}},
            "required": ["recon", "mask", "measurement"]},
        func=_check, mutating=False)


def cassi_tools() -> List[Tool]:
    return [_solutions_tool(), _forward_check_tool()]
