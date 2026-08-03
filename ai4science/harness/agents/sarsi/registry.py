"""The agent registry — seven agents, isolated directories, and a router that
never guesses.

Shaped after openclaw's `agents.list` / `channels.*.accounts` / `bindings`
triple, because that shape already solves this problem and the owner already
runs it on this host.

Two rules here are refusals rather than behaviours, and both are startup errors:

  * a binding naming an unknown agent, or an account that is not configured,
    **refuses to start** — an agent silently unreachable is worse than a daemon
    that will not come up;
  * an unmatched account resolves to **nothing**, never to a default agent —
    delivering a personal message to the work agent because a binding was
    missing is exactly what the bindings table exists to prevent.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from ai4science.harness.agents.sarsi.state import state_dir

CONFIG_NAME = "sarsi.json"
MANAGER_ROLE = "manager"
WORKER_ROLE = "worker"


class ConfigError(Exception):
    """The registry is unusable as written. Raised at load, never deferred."""


@dataclass
class Agent:
    id: str
    role: str
    model: Optional[str] = None
    ceiling: str = "A1"
    self_aware: bool = True
    rsi: bool = True
    tools: List[str] = field(default_factory=list)
    digest: bool = False
    standing_grants: bool = True
    max_concurrent_tasks: int = 3
    #: The ai4science agent spec this one is BUILT ON. The registry already
    #: holds `manager`, `machine`, `social`, `pocket`, `research` and the domain
    #: agents; the seven are an orchestration layer over those, not a second
    #: stack beside them.
    spec: str = "claude-code"
    root: Path = field(default_factory=state_dir)

    @property
    def is_worker(self) -> bool:
        """The agent you talk to does not execute — only a worker does."""
        return self.role == WORKER_ROLE

    # per-agent isolation: every path below is keyed by agent id
    @property
    def agent_dir(self) -> Path:
        return self.root / "agents" / self.id

    @property
    def workspace(self) -> Path:
        """W_name — mission, plan, decisions. Append-only log plus a fold."""
        return self.agent_dir / "workspace"

    @property
    def host(self) -> Path:
        """W_host — tools, paths, resources. Never leaves this machine."""
        return self.agent_dir / "host"

    @property
    def tasks(self) -> Path:
        return self.agent_dir / "tasks"

    @property
    def sessions(self) -> Path:
        return self.agent_dir / "sessions"

    @property
    def selfmodel(self) -> Path:
        return self.agent_dir / "selfmodel"

    @property
    def playbook(self) -> Path:
        return self.agent_dir / "playbook.json"


@dataclass
class Config:
    agents: Dict[str, Agent]
    bindings: List[Dict[str, Any]]
    owner_id: str
    root: Path
    path: Optional[Path] = None

    def resolve(self, channel: str, account_id: str) -> Optional[str]:
        """{channel, accountId} -> agentId, or None. Never a fallback."""
        for b in self.bindings:
            m = b.get("match") or {}
            if m.get("channel") == channel and m.get("accountId") == account_id:
                return b.get("agentId")
        return None

    @property
    def user_workspace(self) -> Path:
        """W_user — read by every agent."""
        return self.root / "workspace"

    @property
    def vault_dir(self) -> Path:
        """W_secret — read by nobody. The only interface is the question."""
        return self.root / "vault"

    @property
    def ledger_dir(self) -> Path:
        return self.root / "ledger"

    def workers(self) -> List[Agent]:
        return [a for a in self.agents.values() if a.is_worker]

    def ensure_dirs(self) -> None:
        for d in (self.user_workspace, self.vault_dir, self.ledger_dir):
            d.mkdir(parents=True, exist_ok=True)
        self.vault_dir.chmod(0o700)
        for agent in self.agents.values():
            for d in (agent.workspace, agent.host, agent.tasks,
                      agent.sessions, agent.selfmodel):
                d.mkdir(parents=True, exist_ok=True)


def config_path(root: Optional[Path] = None) -> Path:
    return (root or state_dir()) / CONFIG_NAME


def load(path: Optional[Path] = None) -> Config:
    root = state_dir()
    path = Path(path) if path else config_path(root)
    try:
        raw = json.loads(Path(path).read_text())
    except FileNotFoundError:
        raise ConfigError(f"no registry at {path}; run `sarsi init` to write one")
    except json.JSONDecodeError as e:
        raise ConfigError(f"{path} is not valid JSON: {e}")
    return parse(raw, root=root, path=Path(path))


def parse(raw: Dict[str, Any], *, root: Optional[Path] = None,
          path: Optional[Path] = None) -> Config:
    root = root or state_dir()
    agents_block = raw.get("agents") or {}
    defaults = agents_block.get("defaults") or {}
    entries = agents_block.get("list") or []
    if not entries:
        raise ConfigError("agents.list is empty — there is nothing to route to")

    agents: Dict[str, Agent] = {}
    for entry in entries:
        agent = _agent_from(entry, defaults, root)
        if agent.id in agents:
            raise ConfigError(f"duplicate agent id {agent.id!r} — ids key every "
                              f"directory and session store, so they must be unique")
        agents[agent.id] = agent

    channels = raw.get("channels") or {}
    telegram = channels.get("telegram") or {}
    owner_id = str(telegram.get("ownerId") or "").strip()
    if not owner_id:
        raise ConfigError("channels.telegram.ownerId is required — without it "
                          "every inbound message is from a stranger")
    accounts = telegram.get("accounts") or {}
    cli_enabled = bool((channels.get("cli") or {}).get("enabled", True))

    bindings = raw.get("bindings") or []
    for b in bindings:
        _validate_binding(b, agents, accounts, cli_enabled)

    return Config(agents=agents, bindings=list(bindings), owner_id=owner_id,
                  root=root, path=path)


def _agent_from(entry: Dict[str, Any], defaults: Dict[str, Any], root: Path) -> Agent:
    def pick(key: str, fallback):
        if key in entry:
            return entry[key]
        return defaults.get(key, fallback)

    agent_id = str(entry.get("id") or "").strip()
    if not agent_id:
        raise ConfigError("an agent entry has no id")
    role = str(pick("role", WORKER_ROLE))
    if role not in (MANAGER_ROLE, WORKER_ROLE):
        raise ConfigError(f"agent {agent_id!r} has unknown role {role!r}")
    return Agent(
        id=agent_id,
        role=role,
        model=pick("model", None),
        ceiling=str(pick("ceiling", "A1")),
        self_aware=bool(pick("selfAware", True)),
        rsi=bool(pick("rsi", True)),
        tools=list(pick("tools", []) or []),
        digest=bool(pick("digest", False)),
        standing_grants=bool(pick("standingGrants", True)),
        max_concurrent_tasks=int(pick("maxConcurrentTasks", 3)),
        spec=str(pick("spec", "claude-code")),
        root=root,
    )


def _validate_binding(b: Dict[str, Any], agents: Dict[str, Agent],
                      accounts: Dict[str, Any], cli_enabled: bool) -> None:
    agent_id = b.get("agentId")
    if agent_id not in agents:
        raise ConfigError(f"binding names unknown agent {agent_id!r}; known: "
                          f"{sorted(agents)}")
    match = b.get("match") or {}
    channel, account_id = match.get("channel"), match.get("accountId")
    if not channel or not account_id:
        raise ConfigError(f"binding for {agent_id!r} needs both a channel and an accountId")
    if channel == "telegram" and account_id not in accounts:
        raise ConfigError(f"binding for {agent_id!r} names telegram account "
                          f"{account_id!r}, which has no botToken configured")
    if channel == "cli" and not cli_enabled:
        raise ConfigError(f"binding for {agent_id!r} uses the cli channel, "
                          f"which is disabled")


# ── the default roster ────────────────────────────────────────────────

#: Each entry names the ai4science spec it is built on. These are the specs the
#: registry already ships for exactly these roles — `manager` is the owner
#: console, `social` is the social-media agent, `pocket` is the closed
#: permission-tight one, which is why abraham runs on it.
_ROSTER = [
    {"id": "sarsi-machine", "role": MANAGER_ROLE, "spec": "manager"},
    {"id": "sarsi-worker", "role": WORKER_ROLE, "spec": "claude-code",
     "tools": ["shell", "editor", "browser"]},
    {"id": "work", "role": WORKER_ROLE, "spec": "claude-code",
     "tools": ["qupath", "matlab", "mail"]},
    {"id": "social", "role": WORKER_ROLE, "spec": "social",
     "tools": ["browser"], "digest": True},
    {"id": "funding", "role": WORKER_ROLE, "spec": "research",
     "tools": ["browser", "documents"]},
    {"id": "jobs", "role": WORKER_ROLE, "spec": "unified-LLM",
     "tools": ["browser", "documents"]},
    # abraham: broadest scope, narrowest authority — no standing grants at all,
    # and built on `pocket`, the closed permission-tight spec.
    {"id": "abraham", "role": WORKER_ROLE, "spec": "pocket", "digest": True,
     "standingGrants": False,
     "tools": ["browser", "calendar", "documents", "payment"]},
]


def default_config(owner_id: str = "", bot_tokens: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """The seven-agent roster, with one telegram account and two bindings each."""
    tokens = bot_tokens or {}
    accounts = {a["id"]: {"botToken": tokens.get(a["id"], "")} for a in _ROSTER}
    bindings: List[Dict[str, Any]] = []
    for a in _ROSTER:
        for channel in ("telegram", "cli"):
            bindings.append({"agentId": a["id"],
                             "match": {"channel": channel, "accountId": a["id"]}})
    return {
        "agents": {
            "defaults": {"model": "anthropic/claude-haiku-4-5", "ceiling": "A1",
                         "selfAware": True, "rsi": True, "maxConcurrentTasks": 3},
            "list": [dict(a) for a in _ROSTER],
        },
        "channels": {
            "telegram": {"ownerId": owner_id, "accounts": accounts},
            "cli": {"enabled": True, "approvals": "telegram"},
        },
        "bindings": bindings,
    }
