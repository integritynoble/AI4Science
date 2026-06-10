from __future__ import annotations

import os
from pathlib import Path
from typing import List

from ai4science.harness import transport
from ai4science.harness.tools.base import Tool
from ai4science.compute.dispatch import dispatch_job, job_state, read_result
from ai4science.judge.cassi.judge_cassi import judge_cassi

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


_IMAGING_KEYWORDS = ("cassi", "cacti", "spectral", "imaging", "hyperspectral",
                     "snapshot", "tomograph", " ct ", "mri")


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
            # explorer genesis rows key on artifact_id (L3-003, …)
            bid = b.get("benchmark_id") or b.get("artifact_id") or b.get("id")
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


def _resolve_provider(provider_id: str):
    from ai4science.compute.registry import get_provider, load_registry
    if provider_id:
        return get_provider(provider_id)
    regs = load_registry()
    return regs[0] if regs else None


def _solution_cost(solution_ref: str):
    """STUB economics seam -> (cost_str, recipient_addr, solution_provider).
    Cost is DEFINED BY THE SOLUTION PROVIDER; users pay PWM to that address. For the
    genesis CASSI solutions the provider is the third founder. The economics layer
    replaces this with a real price lookup + debit + routing."""
    if not solution_ref:
        return ("none (your own solver - compute settled in the economics layer)",
                "you", "you")
    return ("(set by the solution provider - deferred to the economics layer)",
            GENESIS_SOLUTION_PROVIDER, f"of {solution_ref}")


def _dispatch_tool() -> Tool:
    def _dispatch(workspace, *, benchmark: str, solver: str = "code/",
                  provider: str = "", solution_ref: str = "", confirm: bool = False) -> str:
        confirm = confirm is True   # reject truthy strings like "false"/"yes"/"1" from the model
        try:
            prov = _resolve_provider(provider)
            if prov is None:
                return ("[cassi error] no compute provider configured "
                        "(add one with: ai4science compute providers add ...)")
            _contained(Path(workspace), solver)
            cost, recipient, sol_provider = _solution_cost(solution_ref)
            sol_label = solution_ref or "your own solver code"
            if not confirm:
                return ("[preview] would dispatch to sub-GPU compute provider "
                        f"{prov.provider_id} ({prov.endpoint_path})\n"
                        f"  benchmark: {benchmark}\n  solver:    {solver}\n"
                        f"  solution:  {sol_label}\n"
                        f"  PWM cost:  {cost} - pay to {recipient} "
                        f"(solution provider {sol_provider})\n"
                        "Pass confirm=true to dispatch.")
            job = dispatch_job(provider=prov, workspace=Path(workspace).resolve(),
                               benchmark_id=benchmark, solver_code_path=solver)
            # Agent-mining usage logging: record that this paid run used the
            # solution contribution → its author earns a share of the agent pool.
            # Off by default (PwmGate disabled); fire-and-forget; idempotent per
            # (contribution, turn) on the backend (turn = this job).
            if solution_ref:
                try:
                    from ai4science.harness.pwm_gate import PwmGate
                    PwmGate.from_env().post_usage(
                        contribution_id=solution_ref,
                        agent_name="computational-imaging",
                        turn_id=job.job_id,
                    )
                except Exception:
                    pass
            return (f"Dispatched job {job.job_id} to sub-GPU provider {prov.provider_id}. "
                    f"PWM cost {cost} -> {recipient}. "
                    f"Poll with cassi_result(job_id=\"{job.job_id}\").")
        except CassiError as exc:
            return f"[cassi error] {exc}"
        except Exception as exc:
            return f"[cassi error] {exc}"

    return Tool(
        name="cassi_dispatch",
        description=("Dispatch a reconstruction solver to the sub-GPU compute "
                     "provider for a benchmark. Without confirm=true returns a "
                     "PREVIEW with the PWM cost + recipient (set by the solution "
                     "provider); confirm=true dispatches the job. Running a solution "
                     "costs PWM paid to its provider."),
        parameters={"type": "object", "properties": {
            "benchmark": {"type": "string"}, "solver": {"type": "string"},
            "provider": {"type": "string"}, "solution_ref": {"type": "string"},
            "confirm": {"type": "boolean"}},
            "required": ["benchmark"]},
        func=_dispatch, mutating=False)


def _judge_summary(report: dict) -> str:
    if not isinstance(report, dict):
        return str(report)
    keys = ("final", "status", "score_q", "psnr_db", "ssim")
    parts = [f"{k}={report[k]}" for k in keys if k in report]
    return ", ".join(parts) or str(report)[:300]


def _result_tool() -> Tool:
    def _result(workspace, *, job_id: str, provider: str = "") -> str:
        try:
            prov = _resolve_provider(provider)
            if prov is None:
                return "[cassi error] no compute provider configured"
            ep = Path(prov.endpoint_path)
            st = job_state(ep, job_id)
            state = st.get("state", "unknown")
            if state != "completed":
                return f"job {job_id}: state={state} (not finished yet)"
            res = read_result(ep, job_id)
            if not res:
                return f"[cassi error] job {job_id} completed but no result file found"
            ws = res.get("workspace") or str(workspace)
            bench = res.get("benchmark_id") or None
            report = judge_cassi(Path(ws), benchmark=bench)
            return f"job {job_id}: completed. judge: {_judge_summary(report)}"
        except Exception as exc:
            return f"[cassi error] {exc}"

    return Tool(
        name="cassi_result",
        description=("Poll a dispatched CASSI job; when completed, judge the result "
                     "and return the physics-judge status + PSNR / score_q."),
        parameters={"type": "object", "properties": {
            "job_id": {"type": "string"}, "provider": {"type": "string"}},
            "required": ["job_id"]},
        func=_result, mutating=False)


def cassi_tools() -> List[Tool]:
    return [_solutions_tool(), _forward_check_tool(), _dispatch_tool(), _result_tool()]
