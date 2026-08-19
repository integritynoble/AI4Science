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
#: What the seven run at unless the owner raises one. Named once: two places
#: that both decide what "ordinary" means will disagree, and the one that
#: disagrees quietly is the one that grants too much.
EVERYDAY_CEILING = "A1"
MANAGER_ROLE = "manager"
#: The exchange node. Its OWN role, deliberately — it is neither a manager nor
#: a worker, and every refusal that keeps it away from the owner's work keys on
#: this. Sharing the worker role would leave it one rename from being handed a
#: task.
EXCHANGE_ROLE = "exchange"
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
    #: Out of routing, still readable. A roster entry OWNS its task folder,
    #: so deleting one to simplify the roster makes its history unreachable
    #: from every command that reads it. Retiring keeps the record and stops
    #: new work — the owner asked for one general worker, not for the other
    #: one's 32 archived tasks to disappear.
    retired: bool = False
    digest: bool = False
    standing_grants: bool = True
    max_concurrent_tasks: int = 3
    #: What this agent is FOR, in the words a demand would use. The guide
    #: documented this and the registry did not, so routing had only tool
    #: names to go on — and `social` scored zero on "post the thread".
    about: List[str] = field(default_factory=list)
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
        """Workers that may be given NEW work. A retired one is still in
        `agents` — its history is read through it — and is not offered here."""
        return [a for a in self.agents.values()
                if a.is_worker and not a.retired]

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
    if role not in (MANAGER_ROLE, WORKER_ROLE, EXCHANGE_ROLE):
        raise ConfigError(f"agent {agent_id!r} has unknown role {role!r}")
    return Agent(
        id=agent_id,
        role=role,
        model=pick("model", None),
        ceiling=str(pick("ceiling", "A1")),
        self_aware=bool(pick("selfAware", True)),
        rsi=bool(pick("rsi", True)),
        tools=list(pick("tools", []) or []),
        # Roster fallback, like `spec` and `about`: an older registry file on
        # disk has no `retired` key, and reading that as "not retired" would
        # quietly route work to an agent this machine has retired. The same
        # hole was shipped twice before — once for `spec`, once for `about`.
        retired=bool(pick("retired", _ROSTER_RETIRED.get(agent_id, False))),
        digest=bool(pick("digest", False)),
        standing_grants=bool(pick("standingGrants", True)),
        max_concurrent_tasks=int(pick("maxConcurrentTasks", 3)),
        # A registry written before `spec` existed carries none. Falling back
        # to a flat default would silently unbind every agent — and the table
        # would print `claude-code` seven times and look like it was working.
        # A registry written before `about` existed carries none, and every
        # purpose match is then lost — `spec` had this same gap, and this is
        # the same fix: consult the roster rather than defaulting to empty.
        about=list(pick("about", _ROSTER_ABOUT.get(agent_id, [])) or []),
        spec=str(pick("spec", _ROSTER_SPECS.get(agent_id, "claude-code"))),
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
    # The one general worker. It took over the general-work vocabulary from
    # `work` when that retired — without it, "fix the failing test in the repo"
    # matches nobody and routing answers "I cannot tell", which is worse than
    # the answer it replaced. `email` and `mailbox` deliberately did NOT come
    # across: the vocabulary follows the capability, and this agent has no
    # mailbox to clear.
    {"id": "sarsi-worker", "role": WORKER_ROLE, "spec": "claude-code",
     "tools": ["shell", "editor", "browser"],
     "about": ["code", "data", "analysis", "script", "repo", "benchmark",
               "experiment"]},
    # The ai4science worker: same general-work role, driven through the
    # ai4science ACP server (qwen_local backend via nothink proxy). Uses
    # `ai4science acp --pure --mode general-purpose` over JSON-RPC stdio,
    # the same transport as opencode — fully drivable, not attended-only.
    {"id": "sarsi-ai4sci", "role": WORKER_ROLE, "spec": "general-purpose",
     "tools": ["shell", "editor", "browser"],
     "about": ["code", "data", "analysis", "script", "repo", "benchmark",
               "experiment"]},
    # The OpenCode worker: the same general-work role, driven through the
    # opencode TUI instead of Claude Code. Its spec launches `opencode`, which
    # the supervision loop reads the same way (busy/idle/prompt markers).
    {"id": "sarsi-open", "role": WORKER_ROLE, "spec": "opencode",
     "tools": ["shell", "editor", "browser"],
     "about": ["code", "data", "analysis", "script", "repo", "benchmark",
               "experiment"]},
    # RETIRED 2026-08-05: the owner asked for one general worker to begin
    # with. `sarsi-worker` is it. This entry stays so its 32 archived tasks
    # remain readable, and `mail` deliberately did NOT move across — a single
    # do-everything agent that also reads the mailbox is the concentration
    # the split exists to prevent.
    {"id": "work", "role": WORKER_ROLE, "spec": "claude-code", "retired": True,
     "tools": ["qupath", "matlab", "mail"],
     "about": ["code", "data", "analysis", "script", "repo", "email",
               "mailbox", "benchmark", "experiment"]},
    {"id": "social", "role": WORKER_ROLE, "spec": "social",
     "tools": ["browser"], "digest": True,
     "about": ["post", "thread", "timeline", "tweet", "linkedin", "substack",
               "mastodon", "followers"]},
    {"id": "funding", "role": WORKER_ROLE, "spec": "research",
     "tools": ["browser", "documents"],
     "about": ["grant", "fellowship", "funding", "programme", "proposal",
               "award"]},
    {"id": "jobs", "role": WORKER_ROLE, "spec": "unified-LLM",
     "tools": ["browser", "documents"],
     "about": ["cv", "resume", "job", "vacancy", "interview", "recruiter"]},
    # The first research agent the owner can address. Everything else about it
    # already existed — the page, the scope object, the roster of nine
    # sub-agents, the ordered problem list, the charter and a benchmark reading
    # real CAVE scenes — and none of it was reachable from here, so
    # `sarsi run computational-imaging` started nothing.
    #
    # It is `computational-imaging` and not `imaging` because that is what its
    # page, its scope object and its roster object say. `imaging` remains the
    # charter's name inside research_agents (it had a runner before that package
    # existed), declared once in tools/check_design_docs.py — an alias with a
    # stated reason is history; the same alias undeclared is one field with two
    # names, and the roster is the worst place to introduce the second.
    #
    # Its spec launches `ai4science chat --mode computational-imaging`, which
    # the supervision loop cannot read — its gate detection is Claude Code's.
    # So it is ATTENDED: started, and reported as not drivable rather than
    # quietly mis-driven.
    #
    # `about` is deliberately the field's own vocabulary and nothing wider. The
    # general words — benchmark, experiment, data, analysis — stay with
    # `sarsi-worker`: an agent for one field that answered to all of them would
    # capture every ordinary request, and the failure would read as the router
    # being clever rather than as a roster mistake.
    {"id": "computational-imaging", "role": WORKER_ROLE,
     "spec": "computational-imaging",
     # `tools` feeds routing too, and the same argument applies to it as to
     # `about`: `shell` and `editor` are `sarsi-worker`'s by convention because
     # every worker has them, so declaring them here does not describe this
     # agent — it ties with the general worker on every request that mentions
     # one, and a tie makes the router answer "I cannot tell". Only what
     # distinguishes the field: matlab, for its optics and legacy
     # reconstruction code.
     "tools": ["matlab"],
     "about": ["cassi", "hyperspectral", "spectral", "reconstruction", "psnr",
               "mask", "optic", "aperture", "snapshot", "forward model",
               "imaging"]},
    # abraham: broadest scope, narrowest authority — no standing grants at all,
    # and built on `pocket`, the closed permission-tight spec.
    {"id": "abraham", "role": WORKER_ROLE, "spec": "pocket", "digest": True,
     "standingGrants": False,
     "tools": ["browser", "calendar", "documents", "payment"],
     "about": ["personal", "appointment", "booking", "bill", "invoice",
               "family", "household", "birthday"]},
]


#: id -> spec, so an entry that names no spec still binds to the agent it was
#: designed on rather than to a flat default.
_ROSTER_SPECS = {a["id"]: a["spec"] for a in _ROSTER}
_ROSTER_RETIRED = {a["id"]: bool(a.get("retired")) for a in _ROSTER}
#: id -> what it is for, for the same reason: an older registry must not lose
#: the routing evidence just because it was written before the field existed.
_ROSTER_ABOUT = {a["id"]: list(a.get("about") or []) for a in _ROSTER}


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
            # A1 is the everyday ceiling: in-project writes, network, running
            # and testing — the work a task was released to do. It is a
            # CEILING, not a floor: planning still drops to A0, the outward
            # acts still stop at the owner, and A3 stays capped until the trust
            # ledger has earned it.
            #
            # This used to be A2, so that "the loop answers the ordinary gates
            # itself". The cost was that A2 became the ceiling of every
            # ordinary released task — so "A2 may do consequential things"
            # meant every run could, and A2 stopped being an elevated tier
            # while still being described as one. A consequential command
            # (`git push`, `pip install`, `sudo`) now stops for the owner,
            # which is what consequential means.
            "defaults": {"model": "anthropic/claude-haiku-4-5",
                         "ceiling": EVERYDAY_CEILING,
                         "selfAware": True, "rsi": True, "maxConcurrentTasks": 3},
            "list": [dict(a) for a in _ROSTER],
        },
        "channels": {
            "telegram": {"ownerId": owner_id, "accounts": accounts},
            "cli": {"enabled": True, "approvals": "telegram"},
        },
        "bindings": bindings,
    }
