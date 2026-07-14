"""Per-agent input-staging layer.

Turns a demand + owner-provided sources into the validated runner kwargs an
agent needs, fail-closed when a required input is absent. Advisory agents need
only the demand; input agents (imaging/work/research/learning/process-learning)
need a workspace. Also provides the canonical confined-staging helper
(`stage_workspace`) over the control-plane path-confined `stage_input`.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple


def _advisory_kwargs(demand, sources) -> Dict[str, Any]:
    return {"demand": {"intent": demand} if isinstance(demand, str) else demand}


# owner-providable run parameters passed through to the runner when present
_PASSTHROUGH = ("interaction_mode", "seed", "max_repairs", "governed")


def _workspace_kwargs(demand, sources) -> Dict[str, Any]:
    kw = {"workspace": sources["workspace"]}
    for k in _PASSTHROUGH:
        if k in sources:
            kw[k] = sources[k]
    return kw


@dataclass(frozen=True)
class InputSpec:
    agent: str
    required: Tuple[str, ...]                 # owner source keys that MUST be present
    build_kwargs: Callable[[Any, dict], Dict[str, Any]]


INPUT_SPECS: Dict[str, InputSpec] = {
    # advisory / read-only agents — need only the demand
    "manager": InputSpec("manager", (), _advisory_kwargs),
    "pocket": InputSpec("pocket", (), _advisory_kwargs),
    "machine": InputSpec("machine", (), _advisory_kwargs),
    # input agents — need a workspace of seed files (the runner stages it)
    "imaging": InputSpec("imaging", ("workspace",), _workspace_kwargs),
    "work": InputSpec("work", ("workspace",), _workspace_kwargs),
    "research2": InputSpec("research2", ("workspace",), _workspace_kwargs),
    "learning": InputSpec("learning", ("workspace",), _workspace_kwargs),
    "process-learning": InputSpec("process-learning", ("workspace",), _workspace_kwargs),
}

_DEFAULT = InputSpec("_default", (), _advisory_kwargs)


def input_spec(agent_name: str) -> InputSpec:
    return INPUT_SPECS.get(agent_name, _DEFAULT)


def prepare_run_kwargs(agent_name: str, demand, sources: Optional[dict] = None) -> Dict[str, Any]:
    """Build the runner kwargs for `agent_name`. Fail-closed: if a required source
    key is missing/empty, returns {ok: False, missing, reason} and NO kwargs."""
    spec = input_spec(agent_name)
    sources = sources or {}
    missing = [k for k in spec.required if not sources.get(k)]
    if missing:
        return {"ok": False, "missing": missing,
                "reason": f"agent {agent_name!r} needs input(s): {', '.join(missing)} "
                          f"— provide them via sources"}
    return {"ok": True, "kwargs": spec.build_kwargs(demand, sources)}


def stage_workspace(workspace_dir: str, *, client=None, run_id: str,
                    stage: Optional[Callable[[str, str, bytes], Any]] = None) -> Dict[str, Any]:
    """Stage every file under a host workspace dir into the run's confined ws via
    the path-confined control-plane stage_input primitive. Fail-closed on error."""
    stage = stage or (client.stage_input if client is not None else None)
    if stage is None:
        return {"ok": False, "reason": "no control plane to stage into"}
    root = os.path.abspath(workspace_dir)
    if not os.path.isdir(root):
        return {"ok": False, "reason": f"workspace {workspace_dir!r} is not a directory"}
    staged: List[str] = []
    for dirpath, _dirs, files in os.walk(root):
        for fn in sorted(files):
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root)
            try:
                with open(full, "rb") as f:
                    stage(run_id, rel, f.read())
            except Exception as e:
                return {"ok": False, "reason": f"staging {rel!r} failed: {type(e).__name__}"}
            staged.append(rel)
    return {"ok": True, "staged": staged}
