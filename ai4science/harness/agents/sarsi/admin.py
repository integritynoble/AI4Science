"""`sarsi init` and `sarsi agents list` — writing the registry, and reporting it.

Two properties this module owes the owner:

  * **init never clobbers.** A second `init` over a live installation would
    silently discard whatever the agents had already recorded, so it refuses and
    says what is already there.
  * **a report never prints a secret.** Bot tokens are reported as *configured*
    or *no token* — the state matters, the value never does.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from ai4science.harness.agents.sarsi import registry as reg
from ai4science.harness.agents.sarsi.state import state_dir


class AlreadyInitialised(Exception):
    """A registry already exists here. Refusing rather than overwriting it."""


def init(*, owner_id: str, bot_tokens: Optional[Dict[str, str]] = None,
         root: Optional[Path] = None) -> reg.Config:
    """Write the seven-agent roster and create every agent's directories."""
    owner_id = (owner_id or "").strip()
    if not owner_id:
        raise ValueError("an owner id is required — the telegram user whose "
                         "messages are honored, and nobody else's")
    root = Path(root) if root else state_dir()
    path = reg.config_path(root)
    if path.exists():
        raise AlreadyInitialised(f"{path} already exists; edit it, or remove it "
                                 f"first if you really mean to start over")
    raw = reg.default_config(owner_id=owner_id, bot_tokens=bot_tokens)
    root.mkdir(parents=True, exist_ok=True)
    _write_raw(raw, path)
    config = reg.parse(raw, root=root, path=path)
    config.ensure_dirs()
    return config


def set_bot_token(agent_id: str, token: str, *, root: Optional[Path] = None) -> None:
    """Set one agent's Telegram token in place, leaving the rest untouched."""
    root = Path(root) if root else state_dir()
    path = reg.config_path(root)
    raw = json.loads(path.read_text())
    accounts = raw.setdefault("channels", {}).setdefault("telegram", {}).setdefault("accounts", {})
    if agent_id not in accounts:
        raise KeyError(f"no telegram account for {agent_id!r}")
    accounts[agent_id]["botToken"] = token
    _write_raw(raw, path)


def agent_rows(config: reg.Config) -> List[Dict[str, Any]]:
    """One row per agent, for `sarsi agents list --bindings`. Never a token."""
    accounts = _accounts(config)
    rows: List[Dict[str, Any]] = []
    for agent in config.agents.values():
        bindings = [f"{b['match']['channel']}:{b['match']['accountId']}"
                    for b in config.bindings if b.get("agentId") == agent.id]
        token = ((accounts.get(agent.id) or {}).get("botToken") or "").strip()
        rows.append({
            "id": agent.id,
            "role": agent.role,
            # the invariant, reported as a fact: the manager may not execute
            "drives_sessions": agent.is_worker,
            "ceiling": agent.ceiling,
            # A3 is earned, not set: show what the ledger would actually grant
            "ceiling_effective": _effective(agent.ceiling),
            "self_aware": agent.self_aware,
            "tools": list(agent.tools),
            "bindings": bindings,
            "telegram": "configured" if token else "no token",
            "dir": str(agent.agent_dir),
        })
    return rows


def _effective(requested: str) -> str:
    from ai4science.harness.agents.sarsi.session import _effective_ceiling
    return _effective_ceiling(requested)


def _accounts(config: reg.Config) -> Dict[str, Any]:
    if not config.path or not Path(config.path).exists():
        return {}
    raw = json.loads(Path(config.path).read_text())
    return ((raw.get("channels") or {}).get("telegram") or {}).get("accounts") or {}


def _write_raw(raw: Dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(raw, indent=2) + "\n")
    try:
        path.chmod(0o600)          # it holds bot tokens
    except Exception:
        pass
