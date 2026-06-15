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
import uuid
from pathlib import Path
from typing import List, Optional

from ai4science.harness.tools.base import Tool
from ai4science.compute.dispatch import dispatch_job, job_state
from ai4science.compute import lease as lease_mod
from ai4science.compute import billing
from ai4science.compute.founders import all_providers

_LOCAL_IDS = ("", "local", "none")
_RUNTIME_KEYS = ("wall_clock_s", "runtime_s", "elapsed_s", "seconds")


def _repo_of(prov):
    """The git repo the provider's inbox lives in, or None for a local inbox.

    Cross-machine founder providers (e.g. founder-gpu) keep their inbox in a
    git-synced dir, so the agent tools must push the request / pull the result —
    exactly what the CLI's --git-sync does. Same-machine inboxes return None and
    skip git entirely."""
    try:
        from ai4science.compute import gitsync
        return gitsync.find_repo_root(Path(prov.endpoint_path).expanduser())
    except Exception:
        return None


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


def _lease_sidecar(prov, job_id: str) -> Path:
    return Path(prov.endpoint_path).expanduser() / f"job_{job_id}.lease.json"


def _providers_tool() -> Tool:
    def _list(workspace) -> str:
        lines = ["[compute providers]",
                 "  local        your machine        free   (use your bash tool)"]
        for p in all_providers():
            avail = lease_mod.available_slots(p)
            lines.append(
                f"  {p.provider_id:<12} {p.kind:<3}  "
                f"{p.pwm_per_hour():>6.3f} PWM/hr  "
                f"slots {avail}/{p.max_concurrent}  "
                f"{p.trust_tier:<8} -> {p.wallet_address}")
        lines.append("Dispatch with compute_dispatch(provider=\"<id>\", "
                     "run_command=\"...\", confirm=true). Running a provider "
                     "costs PWM paid to its wallet; local is free.")
        return "\n".join(lines)

    return Tool(
        name="compute_providers",
        description=("List compute providers (local + founder CPU/GPU + community) "
                     "with price, free slots, and the wallet that earns PWM."),
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

        avail = lease_mod.available_slots(prov)
        est_pwm = billing.compute_pwm(prov.pwm_per_hour(), max_runtime_s)
        cmd = run_command or "python code/run_solver.py"
        if not confirm:
            full = "" if avail > 0 else " — FULL right now, dispatch will wait/refuse"
            return (f"[preview] would dispatch to {prov.provider_id} "
                    f"({prov.kind}, {prov.endpoint_path})\n"
                    f"  command:    {cmd}\n  solver:     {solver}\n"
                    f"  slots:      {avail}/{prov.max_concurrent} free{full}\n"
                    f"  est PWM:    up to {est_pwm} (at {prov.pwm_per_hour():g} PWM/hr "
                    f"× {max_runtime_s}s cap) -> {prov.wallet_address}\n"
                    "Pass confirm=true to dispatch (charged on completion at actual runtime).")

        ok, why = _confirm_paid_dispatch(prov, est_pwm, max_runtime_s)
        if not ok:
            return why

        # Cross-machine provider: pull first so lease/result state is current.
        repo = _repo_of(prov)
        if repo is not None:
            from ai4science.compute import gitsync
            gitsync.pull(repo)

        holder = uuid.uuid4().hex
        lease = lease_mod.acquire_lease(prov, holder=holder, ttl_s=max_runtime_s)
        if lease is None:
            return (f"[compute] The {prov.kind.upper()} on {prov.provider_id} is "
                    f"busy right now — all {prov.max_concurrent} slot"
                    f"{'s' if prov.max_concurrent != 1 else ''} in use (it serves "
                    "one job at a time). Please tell the user to wait a few "
                    "minutes; then retry compute_dispatch, run locally, or pick "
                    "another provider (compute_providers).")
        try:
            job = dispatch_job(provider=prov, workspace=Path(workspace).resolve(),
                               benchmark_id=benchmark, solver_code_path=solver,
                               run_command=cmd, max_runtime_s=max_runtime_s)
        except Exception as exc:
            lease_mod.release_lease(prov, lease)
            return f"[compute error] dispatch failed: {exc}"
        # Remember which slot this job holds so compute_result can release it.
        _lease_sidecar(prov, job.job_id).write_text(
            lease.model_dump_json(indent=2) + "\n", encoding="utf-8")

        # Cross-machine: publish the request so the remote box's serve loop pulls
        # it. Without this the request only exists locally and the GPU never sees
        # it ("dispatch succeeded" but the sub-GPU can't get the request).
        sync_note = ""
        if repo is not None:
            from ai4science.compute import gitsync
            req = Path(prov.endpoint_path).expanduser() / f"job_{job.job_id}.request.json"
            ok_p, msg_p = gitsync.commit_push(
                repo, [req], f"compute: dispatch job {job.job_id} ({prov.provider_id})")
            sync_note = (" Request pushed to the remote provider."
                         if ok_p else
                         f" [WARN: git push failed — the remote box won't receive it: {msg_p}]")
        return (f"Dispatched job {job.job_id} to {prov.provider_id} "
                f"(slot {lease.slot}, {lease_mod.available_slots(prov)}/"
                f"{prov.max_concurrent} free now).{sync_note} PWM is charged to "
                f"{prov.wallet_address} on completion. "
                f"Poll with compute_result(job_id=\"{job.job_id}\", "
                f"provider=\"{prov.provider_id}\").")

    return Tool(
        name="compute_dispatch",
        description=("Use a GPU/CPU compute provider. Pass confirm=true to run it: "
                     "if a slot is FREE the job dispatches AUTOMATICALLY (normal "
                     "jobs auto-approve; PWM is charged on completion, bounded by "
                     "max_runtime_s); if the server is BUSY it returns a 'please "
                     "wait' message — relay that to the user and retry shortly. "
                     "Without confirm=true you get a preview (free slots + est PWM). "
                     "provider=local (or omitted) runs locally (free). For GPU work "
                     "use provider=founder-gpu / founder-1-subgpu when available."),
        parameters={"type": "object", "properties": {
            "provider": {"type": "string"},
            "run_command": {"type": "string"},
            "solver": {"type": "string"},
            "benchmark": {"type": "string"},
            "max_runtime_s": {"type": "integer"},
            "confirm": {"type": "boolean"}}},
        func=_dispatch, mutating=False)


def _runtime_seconds(result: dict, max_runtime_s: int) -> float:
    for k in _RUNTIME_KEYS:
        v = result.get(k) if isinstance(result, dict) else None
        if isinstance(v, (int, float)) and v >= 0:
            return float(v)
    return 60.0  # unknown runtime → bill a 1-minute floor


def _result_tool() -> Tool:
    def _result(workspace, *, job_id: str, provider: str = "") -> str:
        prov = _resolve(provider)
        if prov is None:
            return ("[compute] no server provider given — local jobs have no result "
                    "to poll. Pass the provider you dispatched to.")
        ep = Path(prov.endpoint_path).expanduser()
        # Cross-machine: pull so the box's pushed ack/result/reconstruction arrive
        # (otherwise the job looks stuck even after the GPU finished it).
        repo = _repo_of(prov)
        if repo is not None:
            from ai4science.compute import gitsync
            gitsync.pull(repo)
        state = job_state(ep, job_id)
        if state.get("state") != "completed":
            return f"[compute] job {job_id} state={state.get('state')} (not done yet)."

        result = state.get("result") or {}
        sidecar = _lease_sidecar(prov, job_id)
        charge_note = ""
        seconds = _runtime_seconds(result, prov.max_concurrent)
        if sidecar.exists():
            charged, msg, pwm = billing.charge_compute(
                prov, seconds=seconds, purpose=f"compute:{prov.provider_id}:{job_id}",
                idempotency_key=f"compute:{job_id}")
            try:
                lease = lease_mod.Lease.model_validate_json(
                    sidecar.read_text(encoding="utf-8"))
                lease_mod.release_lease(prov, lease)
            except (OSError, ValueError):
                pass
            sidecar.unlink(missing_ok=True)
            charge_note = (f"\nPWM: {msg}" if not charged
                           else f"\nPWM: charged {pwm} to {prov.wallet_address}")
        summary = json.dumps(result)[:400] if result else "(no result manifest)"
        return f"[compute] job {job_id} complete on {prov.provider_id}.{charge_note}\n{summary}"

    return Tool(
        name="compute_result",
        description=("Poll a dispatched compute job. When complete, charges PWM for "
                     "the actual runtime to the provider's wallet and frees its slot."),
        parameters={"type": "object", "properties": {
            "job_id": {"type": "string"}, "provider": {"type": "string"}},
            "required": ["job_id"]},
        func=_result, mutating=False)


def compute_tools() -> List[Tool]:
    return [_providers_tool(), _dispatch_tool(), _result_tool()]
