"""`CAP` — is the tool actually here?

One rule, and everything below is it: **do not assume.** A tool nobody wrote a
probe for is **absent**, not present; a tool that needs an account is absent
until the account exists, because "a mail client is installed" is not a claim
about the mailbox; and a cached answer past its age is re-probed rather than
trusted, because software gets uninstalled.

What this learns is written to `W_host` and stays there. A tool inventory is
about a host and means nothing off it — copying it upward is how a fleet
convinces itself it can do something it cannot.
"""
from __future__ import annotations

import json
import shutil
import time
from dataclasses import asdict, dataclass
from typing import Callable, Dict, Iterable, List, Optional

from ai4science.harness.agents.sarsi.registry import Agent, Config

INVENTORY_NAME = "tools.json"
MAX_AGE_S = 900.0            # 15 minutes: long enough to be cheap, short enough to notice an uninstall

# Tools whose presence is a binary on the PATH. A tuple means any one will do.
_BINARIES: Dict[str, tuple] = {
    "matlab": ("matlab",),
    "qupath": ("QuPath", "qupath"),
    "browser": ("chromium", "chromium-browser", "google-chrome", "firefox"),
    "claude": ("claude",),
    "codex": ("codex",),
    "tmux": ("tmux",),
    "git": ("git",),
}

# Always here: the worker runs in a shell and edits files through the session.
_INHERENT = {"shell", "editor", "documents"}

# Not a binary — these need an account or an instrument the owner has to supply,
# and until the vault holds one the honest answer is "not configured".
_NEEDS_CONFIG = {"mail", "calendar", "payment"}


@dataclass
class Probe:
    name: str
    present: bool
    how: Optional[str] = None       # where it was found, or why it was not
    checked_at: float = 0.0


def probe(tool: str, *, which: Callable[[str], Optional[str]] = shutil.which,
          now: Callable[[], float] = time.time,
          configured: Optional[Callable[[str], bool]] = None) -> Probe:
    name = (tool or "").strip()
    stamp = now()
    if name in _INHERENT:
        return Probe(name, True, "always present on this machine", stamp)
    if name in _NEEDS_CONFIG:
        ok = bool(configured(name)) if configured else False
        return Probe(name, ok,
                     "configured" if ok else "not configured — no account for it yet",
                     stamp)
    candidates = _BINARIES.get(name)
    if not candidates:
        # Silence here would read as "no problem". Say why instead.
        return Probe(name, False, f"no probe for {name!r} — unknown tool", stamp)
    for candidate in candidates:
        found = which(candidate)
        if found:
            return Probe(name, True, found, stamp)
    return Probe(name, False, f"not on PATH ({', '.join(candidates)})", stamp)


def inventory(config: Config, agent: Agent, tools: Optional[Iterable[str]] = None, *,
              which: Callable[[str], Optional[str]] = shutil.which,
              now: Callable[[], float] = time.time,
              max_age: float = MAX_AGE_S,
              configured: Optional[Callable[[str], bool]] = None) -> Dict[str, Probe]:
    """This agent's view of what this machine has. Cached in W_host, re-probed
    when an entry is older than `max_age`."""
    wanted = list(tools) if tools is not None else list(agent.tools)
    cached = _load(agent)
    stamp = now()
    out: Dict[str, Probe] = {}
    changed = False
    for name in wanted:
        hit = cached.get(name)
        # Asymmetric on purpose: a cached PRESENT is reused until it ages out, a
        # cached ABSENT is always re-probed. Being stale about presence costs
        # nothing — you find out when you use it. Being stale about absence
        # blocks work that could run: the owner installs the tool because the
        # agent said it was missing, asks again, and hears the same refusal.
        if hit is not None and hit.present and (stamp - float(hit.checked_at or 0)) <= max_age:
            out[name] = hit
            continue
        out[name] = probe(name, which=which, now=now, configured=configured)
        changed = True
    if changed:
        cached.update(out)
        _save(agent, cached)
    return out


def missing(config: Config, agent: Agent, required: Iterable[str], **kw) -> List[str]:
    """Exactly what is absent, in the order asked. The answer `NOM` names."""
    required = list(required)
    inv = inventory(config, agent, required, **kw)
    return [name for name in required if not inv[name].present]


def _path(agent: Agent):
    return agent.host / INVENTORY_NAME


def _load(agent: Agent) -> Dict[str, Probe]:
    path = _path(agent)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text())
    except Exception:
        return {}
    out: Dict[str, Probe] = {}
    for name, rec in (raw or {}).items():
        try:
            out[name] = Probe(**rec)
        except Exception:
            continue
    return out


def _save(agent: Agent, probes: Dict[str, Probe]) -> None:
    path = _path(agent)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({n: asdict(p) for n, p in probes.items()},
                               indent=2, sort_keys=True))
