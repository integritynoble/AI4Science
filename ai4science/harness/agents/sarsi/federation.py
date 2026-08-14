"""`FED` — which of these is the brain, and which is the motor.

The federation plan (`2026-08-09-openclaw-brainrsi-federation.md`, Phase W,
lines 69-78) is explicit that both halves are agent *identities*, not one agent
and one process it shells out to:

    sarsi-worker   (brain)     plans, verifies, holds the lesson index
        |
        +-- sarsi-claude   (executor) -> drives Claude Code
        +-- sarsi-<other>  (executor) -> drives something else

The layering is the safety property. An executor wired to a brain's mode would
be *"a brain driving a brain — recursion, not execution"* (trio plan, line 42).

Today that structure lives in one place — `openclaw.json` — which is mode 0600
and is not a thing a person reads to answer "who did what here". This module is
the board's answer, and it exists because a federation nobody can see is
indistinguishable from a federation that is not there.

**What it reads, and what it refuses to read.**

`openclaw.json` also holds `auth`. The board's contract is *no secret value*
(`board.py:20-22`), so this reads **only** the `agents` subtree and only the
five fields it names below. It is not a config viewer, and the difference
matters: a page that rendered whatever it found would be a credential leak one
config edit away.

**What it will not claim.** Whether a declared executor *can* run is not
answered here. This reports what the machine can show: what is declared, and
what actually left records. `sarsi-pi` being unable to spawn and `sarsi-pi`
never having been asked to look identical from disk, and saying which it is
would be a guess wearing an evidence badge.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

#: The only fields read out of an agent entry. Everything else in the file —
#: `auth`, `models`, `gateway`, `plugins` — is never touched.
FIELDS = ("id", "workspace", "agentDir", "model", "runtime")


def config_path() -> Path:
    """Where the federation is declared. Overridable for tests."""
    env = os.environ.get("OPENCLAW_CONFIG")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".openclaw" / "openclaw.json"


@dataclass(frozen=True)
class Identity:
    """One entry in `agents.list[]` — an identity, not a machine or a process."""
    id: str
    role: str                       # "brain" | "executor"
    drives: Optional[str]           # the harness an executor drives
    backend: Optional[str]
    mode: Optional[str]
    model: Optional[str]
    workspace: str
    agent_dir: str
    #: sessions this identity actually left on disk
    sessions: int
    #: whether its agentDir exists at all
    provisioned: bool

    @property
    def ran_here(self) -> bool:
        return self.sessions > 0

    @property
    def what_it_did(self) -> str:
        """The honest sentence. `never asked` and `could not` look alike here."""
        if self.sessions:
            return f"{self.sessions} sessions on this machine"
        if not self.provisioned:
            return "no agent directory — never started here"
        return "provisioned, but no session recorded here"


def _role_of(entry: dict) -> str:
    """An `acp` runtime means it drives a harness: an executor. Otherwise brain.

    Derived from the runtime rather than the name, because a name is a label
    and the runtime is the thing that decides what actually happens.
    """
    return "executor" if (entry.get("runtime") or {}).get("type") == "acp" else "brain"


def _sessions_dir(agent_dir: str) -> Optional[Path]:
    if not agent_dir:
        return None
    # agentDir is <root>/agents/<id>/agent; sessions sit beside it.
    return Path(agent_dir.rstrip("/")).parent / "sessions"


def load(path: Optional[Path] = None) -> List[Identity]:
    """Every declared identity, with what it actually did here.

    Returns `[]` — never raises — when the file is absent or unreadable. A
    board that 500s because a config moved is worse than one that says it
    cannot see the federation.
    """
    p = Path(path) if path else config_path()
    try:
        raw = json.loads(p.read_text())
    except Exception:
        return []

    out: List[Identity] = []
    for entry in (raw.get("agents") or {}).get("list") or []:
        entry = {k: entry.get(k) for k in FIELDS}     # nothing else, ever
        aid = entry.get("id")
        if not aid:
            continue
        acp = (entry.get("runtime") or {}).get("acp") or {}
        agent_dir = entry.get("agentDir") or ""
        sdir = _sessions_dir(agent_dir)
        try:
            n = len([f for f in os.listdir(sdir) if f.endswith(".jsonl")]) if sdir and sdir.is_dir() else 0
        except OSError:
            n = 0
        out.append(Identity(
            id=aid,
            role=_role_of(entry),
            drives=acp.get("agent"),
            backend=acp.get("backend"),
            mode=acp.get("mode"),
            model=entry.get("model"),
            workspace=entry.get("workspace") or "",
            agent_dir=agent_dir,
            sessions=n,
            provisioned=bool(agent_dir) and Path(agent_dir).parent.is_dir(),
        ))
    return out


def default_model(path: Optional[Path] = None) -> Optional[str]:
    """`agents.defaults.model` — the pin that can override an ACP runtime."""
    p = Path(path) if path else config_path()
    try:
        raw = json.loads(p.read_text())
    except Exception:
        return None
    return ((raw.get("agents") or {}).get("defaults") or {}).get("model")


def model_pin_warning(identities: List[Identity],
                      default: Optional[str]) -> Optional[str]:
    """The trio plan's trap #1, lines 201-205, checked against this config.

    *"a model that maps to `claude-cli` overrides the agent's ACP runtime — the
    runtime declaration loses to the model mapping."* An executor that names no
    model of its own inherits the default, so its ACP declaration is not
    self-proving. Naming it is the difference between a page that shows a
    federation and a page that claims one.
    """
    if not default:
        return None
    exposed = [i.id for i in identities if i.role == "executor" and not i.model]
    if not exposed:
        return None
    return (f"{', '.join(exposed)} declare an ACP runtime but name no model of "
            f"their own, so each inherits agents.defaults.model = {default}. A "
            f"model that maps to claude-cli overrides the ACP runtime — the "
            f"runtime declaration loses to the model mapping. So this table "
            f"shows what is DECLARED; it is not proof of what a spawn would "
            f"actually run.")
