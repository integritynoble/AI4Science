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
#: The owner's standing word about tools this module has no probe for. Kept
#: APART from the inventory, which is a cache: an absent entry there is
#: re-probed every pass and a present one ages out in fifteen minutes, so a
#: declaration living inside it would be one `_save` away from gone.
DECLARED_NAME = "tools-declared.json"
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
          configured: Optional[Callable[[str], bool]] = None,
          declared: Optional[Dict[str, str]] = None) -> Probe:
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
        # Nothing here can check this one. The owner may say it is here, and
        # that is worth having — an in-house CLI or a GUI app off `PATH` was
        # otherwise absent forever and `NOM` refused the work needing it.
        # Reported AS a declaration: the owner's word is legitimate and is not
        # evidence, and a line that read like somebody looked would be exactly
        # the assumption this module exists to refuse.
        note = (declared or {}).get(name)
        if note is not None:
            how = "declared by the owner — not probed"
            return Probe(name, True, f"{how}: {note}" if note else how, stamp)
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
    cached = _load(agent)
    declared = _load_declared(agent)
    if tools is not None:
        wanted = list(tools)
    else:
        # The roster's tools AND anything the owner declared. Asking only the
        # roster meant a declaration was accepted, stored and honoured by
        # `missing`, yet absent from the listing the owner was reading — and a
        # declaration you cannot see is one you cannot check or withdraw.
        wanted = list(agent.tools) + [n for n in sorted(declared)
                                      if n not in agent.tools]
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
        if name in declared and name not in _BINARIES \
                and name not in _INHERENT and name not in _NEEDS_CONFIG:
            # A declaration is not a probe and does not expire: software gets
            # uninstalled, but the owner's standing word does not go stale on
            # a timer, and re-declaring every fifteen minutes is not a thing
            # anyone would do.
            out[name] = probe(name, which=which, now=now,
                              configured=configured, declared=declared)
            continue
        if hit is not None and hit.present and (stamp - float(hit.checked_at or 0)) <= max_age:
            out[name] = hit
            continue
        out[name] = probe(name, which=which, now=now, configured=configured,
                          declared=declared)
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


def declare(config: Config, agent: Agent, tool: str, *, note: str = "") -> None:
    """The owner says this tool is here. Only for tools nothing can check.

    Where `CAP` CAN check, checking wins — declaring `matlab` present on a
    machine without it is a claim the probe falsifies, and letting a
    declaration win there would switch off the one check that catches it.
    """
    current = _load_declared(agent)
    current[str(tool).strip()] = str(note or "")
    _save_declared(agent, current)


def undeclare(config: Config, agent: Agent, tool: str) -> None:
    current = _load_declared(agent)
    current.pop(str(tool).strip(), None)
    _save_declared(agent, current)


def declared_tools(agent: Agent) -> Dict[str, str]:
    """What the owner has said is here, for this agent."""
    return _load_declared(agent)


def _declared_path(agent: Agent):
    return agent.host / DECLARED_NAME


def _load_declared(agent: Agent) -> Dict[str, str]:
    path = _declared_path(agent)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text())
    except Exception:
        # A damaged declaration file is not a declaration. Absent is the safe
        # reading: it refuses work rather than authorising it.
        return {}
    return {str(k): str(v or "") for k, v in (raw or {}).items()}


def _save_declared(agent: Agent, values: Dict[str, str]) -> None:
    path = _declared_path(agent)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(values, indent=2, sort_keys=True) + "\n")


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
