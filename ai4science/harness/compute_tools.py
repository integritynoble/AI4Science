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


def _resolve(provider_id: str):
    pid = (provider_id or "").strip()
    if pid.lower() in _LOCAL_IDS:
        return None  # local
    for p in all_providers():
        if p.provider_id == pid:
            return p
    return None


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
                f"${p.price_usd_per_hour:>5.2f}/hr  "
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
        est_pwm = billing.compute_pwm(prov.price_usd_per_hour, max_runtime_s)
        cmd = run_command or "python code/run_solver.py"
        if not confirm:
            full = "" if avail > 0 else " — FULL right now, dispatch will wait/refuse"
            return (f"[preview] would dispatch to {prov.provider_id} "
                    f"({prov.kind}, {prov.endpoint_path})\n"
                    f"  command:    {cmd}\n  solver:     {solver}\n"
                    f"  slots:      {avail}/{prov.max_concurrent} free{full}\n"
                    f"  est PWM:    up to {est_pwm} (at ${prov.price_usd_per_hour}/hr "
                    f"× {max_runtime_s}s cap) -> {prov.wallet_address}\n"
                    "Pass confirm=true to dispatch (charged on completion at actual runtime).")

        holder = uuid.uuid4().hex
        lease = lease_mod.acquire_lease(prov, holder=holder, ttl_s=max_runtime_s)
        if lease is None:
            return (f"[compute] {prov.provider_id} is full "
                    f"({prov.max_concurrent}/{prov.max_concurrent} users). "
                    "Wait for a slot or pick another provider (compute_providers).")
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
        return (f"Dispatched job {job.job_id} to {prov.provider_id} "
                f"(slot {lease.slot}, {lease_mod.available_slots(prov)}/"
                f"{prov.max_concurrent} free now). PWM is charged to "
                f"{prov.wallet_address} on completion. "
                f"Poll with compute_result(job_id=\"{job.job_id}\", "
                f"provider=\"{prov.provider_id}\").")

    return Tool(
        name="compute_dispatch",
        description=("Dispatch a command to a compute provider. Without confirm=true "
                     "returns a PREVIEW (free slots + estimated PWM + recipient); "
                     "confirm=true acquires a slot (refused if the server is full) "
                     "and dispatches. provider=local (or omitted) means run locally."),
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
