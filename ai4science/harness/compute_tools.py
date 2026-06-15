"""Universal compute-provider tools, available to every mode.

Every session can offload heavy work (training, solvers, GPU jobs) to a chosen
compute provider instead of the local machine:

  - local            — your own machine (free; just use your bash tool)
  - founder-cpu      — main CPU server, 2 users at once, pays the founder
  - founder-gpu      — sub-GPU server, 2 users at once, pays the founder
  - <community>      — anyone who registered as a provider (pays that provider)

Dispatch is lease-gated: a provider serves at most max_concurrent users at
once; a third request is refused until a slot frees. Running on a wallet-bound
provider costs PWM (USD/hour ÷ PWM_USD), paid to that provider's wallet on
completion; local compute is free.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List

from ai4science.harness.tools.base import Tool
from ai4science.compute import billing
from ai4science.compute.founders import all_providers

_LOCAL_IDS = ("", "local", "none")


def _resolve(provider_id: str):
    pid = (provider_id or "").strip()
    if pid.lower() in _LOCAL_IDS:
        return None  # local
    # Prefer a REGISTERED entry (incl. founder-gpu→founder-1-subgpu alias): a user
    # who types `founder-gpu` should reach the served git-synced inbox, not the
    # built-in default's local inbox. get_provider() does exact + alias-to-registered.
    from ai4science.compute.registry import get_provider, PROVIDER_ALIASES
    p = get_provider(pid)
    if p is not None:
        return p
    # Fresh machine with no registry: fall back to the founder defaults (+ alias).
    provs = {x.provider_id: x for x in all_providers()}
    if pid in provs:
        return provs[pid]
    alias = PROVIDER_ALIASES.get(pid)
    return provs.get(alias) if alias else None


def _providers_tool() -> Tool:
    def _list(workspace) -> str:
        lines = ["[compute providers]",
                 "  local        your machine        free   (use your bash tool)"]
        for p in all_providers():
            lines.append(
                f"  {p.provider_id:<16} {p.kind:<3}  "
                f"{p.pwm_per_hour():>6.3f} PWM/hr  "
                f"{p.trust_tier:<8} -> {p.wallet_address}")
        lines.append("Dispatch with compute_dispatch(provider=\"<id>\", "
                     "run_command=\"...\", confirm=true) — runs over the HTTPS relay "
                     "(needs `ai4science login`). The relay manages the queue/slots "
                     "and billing; running a provider costs PWM paid to its wallet; "
                     "local is free.")
        return "\n".join(lines)

    return Tool(
        name="compute_providers",
        description=("List compute providers (local + founder CPU/GPU + community) "
                     "with price and the wallet that earns PWM."),
        parameters={"type": "object", "properties": {}},
        func=_list, mutating=False)


def _auto_max_pwm() -> float:
    import os
    try:
        return float(os.environ.get("AI4SCIENCE_COMPUTE_AUTO_MAX_PWM", "1.0") or 1.0)
    except ValueError:
        return 1.0


def _confirm_paid_dispatch(prov, est_pwm, max_runtime_s) -> tuple:
    """Decide whether a PAID dispatch may proceed.

    By default users can use the GPU AUTOMATICALLY: a dispatch whose worst-case
    cost is within the auto-approve ceiling (AI4SCIENCE_COMPUTE_AUTO_MAX_PWM,
    default 1.0 PWM — bounded by max_runtime_s) runs WITHOUT asking. Larger jobs,
    or AI4SCIENCE_COMPUTE_AUTO=0, fall back to a human y/N (the 2026-06-10 guard;
    non-interactive → refused unless AI4SCIENCE_COMPUTE_AUTOCONFIRM=1).
    Returns (ok, refusal_message)."""
    import os
    import sys

    def _on(name, default="0"):
        return str(os.environ.get(name, default)).strip().lower() in (
            "1", "true", "yes", "on")

    if _on("AI4SCIENCE_COMPUTE_AUTOCONFIRM"):
        return True, ""
    if _on("AI4SCIENCE_COMPUTE_AUTO", "1") and est_pwm <= _auto_max_pwm():
        return True, ""                       # auto-use the GPU for normal jobs
    if not sys.stdin.isatty():
        return False, (f"[compute] PAID dispatch blocked: worst-case cost "
                       f"{est_pwm} PWM exceeds the auto-approve ceiling "
                       f"({_auto_max_pwm():g} PWM) and this session is "
                       "non-interactive. Lower max_runtime_s, re-run "
                       "interactively, or set AI4SCIENCE_COMPUTE_AUTOCONFIRM=1.")
    try:
        ans = input(f"[compute] PAID GPU dispatch to {prov.provider_id} "
                    f"(up to {est_pwm} PWM at {prov.pwm_per_hour():g} PWM/hr, "
                    f"{max_runtime_s}s cap) — proceed? [y/N] ")
    except (EOFError, KeyboardInterrupt):
        return False, "[compute] dispatch cancelled."
    if ans.strip().lower() not in ("y", "yes"):
        return False, "[compute] dispatch declined by the user."
    return True, ""


def _dispatch_tool() -> Tool:
    def _dispatch(workspace, *, provider: str = "", run_command: str = "",
                  solver: str = "code/", benchmark: str = "",
                  max_runtime_s: int = 3600, confirm: bool = False) -> str:
        confirm = confirm is True
        prov = _resolve(provider)
        if prov is None:
            return ("[compute] local compute selected — run it with your bash tool "
                    "(no PWM cost). To use a server, pass provider=founder-cpu / "
                    "founder-gpu / <community id> (see compute_providers).")

        est_pwm = billing.compute_pwm(prov.pwm_per_hour(), max_runtime_s)
        cmd = run_command or "python code/run_solver.py"
        if not confirm:
            return (f"[preview] would dispatch to {prov.provider_id} "
                    f"({prov.kind}) over the HTTPS relay\n"
                    f"  command:    {cmd}\n  solver:     {solver}\n"
                    f"  est PWM:    up to {est_pwm} (at {prov.pwm_per_hour():g} PWM/hr "
                    f"× {max_runtime_s}s cap) -> {prov.wallet_address}\n"
                    "Pass confirm=true to dispatch (the relay queues it, the provider "
                    "runs it, and PWM is charged on completion at actual runtime — "
                    "only on a verified pass).")

        ok, why = _confirm_paid_dispatch(prov, est_pwm, max_runtime_s)
        if not ok:
            return why

        # Dispatch over the HTTP relay (the server enforces the queue/slot + PWM
        # preauth + billing — no git, no repo needed).
        from ai4science.compute.transport import select
        _mode, tx = select(prov)
        if not getattr(tx, "token", ""):
            return ("[compute] not logged in — run `ai4science login` to use a remote "
                    "provider (the relay needs your PWM account to charge usage).")
        try:
            job = tx.dispatch(provider_id=prov.provider_id, run_command=cmd,
                              workspace=Path(workspace).resolve(),
                              max_runtime_s=max_runtime_s)
        except Exception as exc:
            # Includes 402 (insufficient PWM) and 'provider busy' from the relay.
            return f"[compute error] dispatch failed: {exc}"
        return (f"Dispatched job {job['job_id']} to {prov.provider_id} "
                f"(state {job.get('state')}). PWM is charged to {prov.wallet_address} "
                f"on a verified pass. Poll with "
                f"compute_result(job_id=\"{job['job_id']}\", "
                f"provider=\"{prov.provider_id}\").")

    return Tool(
        name="compute_dispatch",
        description=("Use a GPU/CPU compute provider over the HTTPS relay (needs "
                     "`ai4science login`). Pass confirm=true to run it: normal jobs "
                     "auto-approve; the relay queues it, the provider runs it, and "
                     "PWM is charged on completion (bounded by max_runtime_s), only "
                     "on a verified pass. Without confirm=true you get a preview "
                     "(est PWM). provider=local (or omitted) runs locally (free). "
                     "For GPU work use provider=founder-gpu / founder-1-subgpu."),
        parameters={"type": "object", "properties": {
            "provider": {"type": "string"},
            "run_command": {"type": "string"},
            "solver": {"type": "string"},
            "benchmark": {"type": "string"},
            "max_runtime_s": {"type": "integer"},
            "confirm": {"type": "boolean"}}},
        func=_dispatch, mutating=False)


def _result_tool() -> Tool:
    def _result(workspace, *, job_id: str, provider: str = "") -> str:
        prov = _resolve(provider)
        if prov is None:
            return ("[compute] no server provider given — local jobs have no result "
                    "to poll. Pass the provider you dispatched to.")
        from ai4science.compute.transport import select
        _mode, tx = select(prov)
        if not getattr(tx, "token", ""):
            return ("[compute] not logged in — run `ai4science login` to poll a "
                    "remote job.")
        try:
            job = tx.poll(job_id)
        except Exception as exc:
            return f"[compute error] poll failed: {exc}"
        if job.get("state") != "completed":
            return f"[compute] job {job_id} state={job.get('state')} (not done yet)."

        # Pull the reconstruction back into the workspace (via the relay proxy).
        try:
            out = tx.download_reconstruction(job, Path(workspace).resolve())
        except Exception:
            out = None
        result = job.get("result") or {}
        recon = f"\nreconstruction: {out}" if out else ""
        summary = json.dumps(result)[:400] if result else "(no result manifest)"
        return (f"[compute] job {job_id} complete on {prov.provider_id} "
                f"(PWM charged on the relay on a verified pass).{recon}\n{summary}")

    return Tool(
        name="compute_result",
        description=("Poll a dispatched compute job over the relay. When complete, "
                     "downloads the reconstruction; the relay charges PWM for the "
                     "actual runtime to the provider's wallet on a verified pass."),
        parameters={"type": "object", "properties": {
            "job_id": {"type": "string"}, "provider": {"type": "string"}},
            "required": ["job_id"]},
        func=_result, mutating=False)


def compute_tools() -> List[Tool]:
    return [_providers_tool(), _dispatch_tool(), _result_tool()]
