"""Persistence for which sarsi-roster agents the owner has installed.

The roster ships more agents than most owners need.  This module tracks
which ones they have added to their /agent picker.  The state lives in
~/.ai4science/installed_agents.json.

sarsi-worker is a protected default — it is always installed and cannot
be removed.
"""
from __future__ import annotations

import json
from pathlib import Path

_DEFAULT_INSTALLED: frozenset[str] = frozenset({"sarsi-worker"})


def _path() -> Path:
    return Path.home() / ".ai4science" / "installed_agents.json"


def load() -> set:
    """Return the set of installed sarsi agent ids (always includes defaults)."""
    p = _path()
    if not p.exists():
        return set(_DEFAULT_INSTALLED)
    try:
        data = json.loads(p.read_text())
        agents = data.get("agents")
        if not isinstance(agents, list):
            return set(_DEFAULT_INSTALLED)
        return set(agents) | _DEFAULT_INSTALLED
    except Exception:
        return set(_DEFAULT_INSTALLED)


def save(agents: set) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"agents": sorted(agents)}, indent=2) + "\n")


def install(agent_id: str) -> None:
    agents = load()
    agents.add(agent_id)
    save(agents)


def uninstall(agent_id: str) -> bool:
    """Remove agent_id.  Returns False if it is a protected default."""
    if agent_id in _DEFAULT_INSTALLED:
        return False
    agents = load()
    agents.discard(agent_id)
    save(agents)
    return True


def is_installed(agent_id: str) -> bool:
    return agent_id in load()
