"""The Machine Agent loop — governed, fixed-operation, owner-gated.

`run_machine` gate order is load-bearing:
  1. select a vetted operation (deterministic keyword match over the CLOSED
     registry). No match ⇒ refused — there is no arbitrary-command path.
  2. OS-support check ⇒ unsupported (not executed).
  3. consequential ⇒ require owner approve(); denied/absent ⇒ needs_approval,
     and the recipe NEVER runs.
  4. credential side-effect ⇒ route through the broker: the agent gets a scoped
     lease, NEVER the raw secret.
  5. execute the vetted recipe (via the injected `execute` seam) and audit.

All of approve/broker/audit/execute are injectable seams: real subprocess +
control-plane broker/audit in production; fakes in tests. Nothing here can run
outside the registry, autonomously, or with an ambient secret.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Sequence

from ai4science.harness.agents.machine.capabilities import detect_machine
from ai4science.harness.agents.machine.operations import Operation, default_operations


def _select_by_keyword(intent: str, registry: Sequence[Operation]) -> Optional[Operation]:
    low = (intent or "").lower()
    for op in registry:
        if op.match and any(kw in low for kw in op.match):
            return op
    return None


def _default_execute(op: Operation, caps: Dict) -> Dict:
    """Real executor: run the vetted recipe for this OS via subprocess.

    Imported lazily and only reached AFTER owner approval for consequential ops.
    Returns a structured result; never raises out of run_machine."""
    recipe = op.recipe_for(caps["os"])
    if recipe is None:
        return {"ran": False, "reason": f"no recipe for os={caps['os']!r}"}
    import subprocess
    try:
        proc = subprocess.run(list(recipe), capture_output=True, text=True, timeout=600)
        return {"ran": True, "argv": list(recipe), "exit_code": proc.returncode,
                "ok": proc.returncode == 0}
    except Exception as e:                       # never let a recipe failure escape
        return {"ran": False, "argv": list(recipe), "error": type(e).__name__}


def _audit(audit: Optional[Callable], event: Dict) -> None:
    if audit is not None:
        try:
            audit(event)
        except Exception:
            pass


def run_machine(*, intent: str,
                caps: Optional[Dict] = None,
                registry: Optional[Sequence[Operation]] = None,
                approve: Optional[Callable[[str, Dict], bool]] = None,
                broker: Optional[Any] = None,
                audit: Optional[Callable[[Dict], None]] = None,
                execute: Optional[Callable[[Operation, Dict], Dict]] = None,
                select: Optional[Callable[[str, Sequence[Operation]], Optional[Operation]]] = None,
                ) -> Dict:
    caps = caps if caps is not None else detect_machine()
    registry = tuple(registry) if registry is not None else default_operations()
    select = select or _select_by_keyword
    execute = execute or _default_execute

    # 1. vetted-operation selection (closed registry)
    op = select(intent, registry)
    if op is None:
        return {"status": "refused",
                "reason": "no vetted operation matches; the machine agent performs "
                          "only its fixed, reviewed operations (no arbitrary commands)"}

    # 2. OS support
    if caps.get("os") not in op.os_support:
        return {"status": "unsupported", "op": op.name, "os": caps.get("os"),
                "supported_on": list(op.os_support)}

    # read-only ops: run directly, audited
    if not op.consequential:
        result = _read_op(op, caps)
        _audit(audit, {"op": op.name, "side_effect": op.side_effect, "consequential": False})
        return {"status": "done", "op": op.name, "result": result}

    # 3. consequential ⇒ owner gate
    approved = bool(approve and approve(op.name, {"os": caps.get("os"), "summary": op.summary,
                                                  "recipe": list(op.recipe_for(caps["os"]) or ())}))
    if not approved:
        _audit(audit, {"op": op.name, "consequential": True, "outcome": "needs_approval"})
        return {"status": "needs_approval", "op": op.name, "proposal": op.summary,
                "recipe": list(op.recipe_for(caps["os"]) or ())}

    # 4. credential ops ⇒ broker (agent never sees the secret)
    if op.side_effect == "credential":
        if broker is None:
            return {"status": "blocked", "op": op.name,
                    "reason": "no credential broker; login requires brokered credentials"}
        lease = broker.lease(op.account_scope)          # scoped, time-boxed handle
        result = {"leased": True, "scope": op.account_scope,
                  "lease_id": (lease or {}).get("lease_id") if isinstance(lease, dict) else None}
        _audit(audit, {"op": op.name, "side_effect": "credential", "scope": op.account_scope,
                       "outcome": "leased"})
        return {"status": "done", "op": op.name, "result": result}

    # 5. execute the vetted recipe (install/config) + audit
    result = execute(op, caps)
    _audit(audit, {"op": op.name, "side_effect": op.side_effect, "consequential": True,
                   "outcome": "executed", "result": result})
    return {"status": "done", "op": op.name, "result": result}


def _read_op(op: Operation, caps: Dict) -> Dict:
    """Read-only operations resolve from already-detected capabilities (no host mutation)."""
    from ai4science.harness.agents.machine.operations import CLAUDE_PERMISSIONS
    if op.name == "detect":
        return dict(caps)
    if op.name == "is_installed":
        return {"claude": caps.get("installed", {}).get("claude", False),
                "installed": caps.get("installed", {})}
    if op.name == "required_permissions":
        return {"claude_permissions": list(CLAUDE_PERMISSIONS)}
    if op.name == "find_sessions":
        from ai4science.harness.agents.machine.sessions import find_claude_sessions
        return find_claude_sessions()
    return {}
