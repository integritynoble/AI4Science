"""`MKT` — §11, the half a single machine can have.

The market has two halves, and this page's governing property splits them:
*everything here works with nothing else installed*. Uploading, the governor's
acceptance and the PWM earning need a server, and the design assigns those to
the app. What one machine has is the rest, and it is the half that matters for
safety — **the package format, and installing one here** — because an agent is
a thing you install on your own machine and run with your own keys.

So the acceptance questions are asked **at install, by the machine doing the
installing**, not taken on trust from a listing. A listing's own claims are
what the market needs; they are not what the runtime trusts.

Four refusals carry it, and each one closes a way a package could take
something the owner did not give it:

  * **it may not ship a workspace or a task list.** One arriving with tasks in
    it files work the owner never asked for — past `CAP`, past the plan, past
    the grant — and the install screen is the consent step that pre-filled work
    walks straight through. One arriving with a workspace is an author writing
    standing instructions into a place the agent reads at plan time.
  * **the four reserved classes are refused at any ceiling.** `money`,
    `consent`, `publishing`, `legal` — refused, not stripped: an author who
    asked should be told no rather than quietly installed without it.
  * **an agent does not set its own ceiling**, or its own standing grants, or
    its own retirement. Those are the owner's, and a manifest that could set
    one would make installing an agent a way to grant one.
  * **trust is not transitive.** A package may bring its own tools; the install
    names every author whose code comes with it and what each part touches.
"""
from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from ai4science.harness.agents.sarsi.registry import (Agent, Config,
                                                      EVERYDAY_CEILING,
                                                      WORKER_ROLE, config_path)

MANIFEST = "agent.json"
SPEC = "spec.md"
ROSTER = "roster.json"

#: Created by the installer, for every agent, and never shipped.
_NEVER_SHIPPED = ("workspace", "tasks")

#: Refused at any ceiling, by any agent, market or not.
RESERVED = ("money", "consent", "publishing", "legal")

#: Fields that are the OWNER's to set. A manifest naming one is refused rather
#: than having it ignored: an author who wrote `"ceiling": "A3"` asked for
#: something, and installing them without it and without a word is how a
#: request becomes a surprise later.
_OWNERS_ALONE = ("ceiling", "standing_grants", "retired", "digest", "role",
                 "max_concurrent_tasks")

#: An id keys every directory and session store on this machine, so it is
#: checked as a directory name and not as a label.
_ID = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")


class Refused(Exception):
    """The package was not installed, and this says exactly why."""


@dataclass
class Report:
    agent_id: str
    version: str = ""
    purpose: str = ""
    #: every author whose code comes with it — the agent's, and each tool's
    authors: List[Dict[str, Any]] = field(default_factory=list)
    source: str = ""


def _read_json(path: Path, what: str) -> Dict[str, Any]:
    try:
        raw = json.loads(path.read_text())
    except FileNotFoundError:
        raise Refused(f"this package has no {what} — without it there is "
                      f"nothing saying what it is or what it may do")
    except json.JSONDecodeError as e:
        raise Refused(f"{what} is not valid JSON: {e}")
    if not isinstance(raw, dict):
        raise Refused(f"{what} is not an object")
    return raw


def _check_id(value: Any, config: Config) -> str:
    agent_id = str(value or "").strip()
    if not _ID.match(agent_id):
        raise Refused(
            f"{agent_id!r} is not a usable id — it keys this agent's directory "
            f"and its session store, so it must be lowercase letters, digits "
            f"and hyphens, 2-64 characters, and nothing that could point "
            f"somewhere else")
    if agent_id in config.agents:
        raise Refused(f"{agent_id!r} is already installed here — every "
                      f"directory and session store is keyed by id, so a "
                      f"collision would hand this package another agent's "
                      f"history")
    return agent_id


def _check_shipped_state(root: Path) -> None:
    for name in _NEVER_SHIPPED:
        if (root / name).exists():
            raise Refused(
                f"this package ships a {name}/ directory. The installer creates "
                f"that, empty, for every agent — a package that brought its own "
                f"would be "
                + ("filing work the owner never asked for, past CAP, past the "
                   "plan and past the grant" if name == "tasks" else
                   "writing standing instructions into a place the agent reads "
                   "at plan time")
                + ", and this install is the step where the owner consents")


def _check_outward(claims, where: str) -> List[str]:
    out = []
    for klass in (claims or []):
        name = str(klass).strip().lower()
        if name in RESERVED:
            raise Refused(
                f"{where} claims the reserved class {name!r}. No agent "
                f"completes {', '.join(RESERVED)} at any ceiling — refused "
                f"rather than quietly installed without it, because the "
                f"author asked for something and should be told no")
        if name:
            out.append(name)
    return out


def _check_requires(manifest: Dict[str, Any]) -> None:
    want = str(((manifest.get("requires") or {}).get("ai4science") or "")).strip()
    if not want:
        return
    m = re.match(r"^>=\s*([0-9][0-9.]*)$", want)
    if not m:
        raise Refused(f"requires.ai4science {want!r} is not a form this "
                      f"understands (>=X.Y)")
    try:
        from ai4science import __version__ as have
    except Exception:
        have = "0"
    def parts(v):
        return tuple(int(x) for x in re.findall(r"\d+", str(v))[:3] or [0])
    if parts(have) < parts(m.group(1)):
        raise Refused(f"this package needs ai4science >= {m.group(1)} and this "
                      f"machine has {have}")


def _authors(root: Path, manifest: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Every author whose code comes with this package.

    Trust is not transitive: an agent that brings a tool brings its author, and
    the owner deciding whether to install sees both, with what each touches.
    """
    out = [dict(manifest.get("author") or {}, part="agent",
                touches=list(manifest.get("tools") or []))]
    tools = root / "tools"
    if tools.is_dir():
        for f in sorted(tools.glob("*.json")):
            try:
                spec = json.loads(f.read_text())
            except Exception:
                raise Refused(f"tools/{f.name} could not be read, so who wrote "
                              f"it and what it touches are unknown — and an "
                              f"unknown author is not one the owner can weigh")
            out.append(dict(spec.get("author") or {}, part=f"tool:{spec.get('name') or f.stem}",
                            touches=list(spec.get("touches") or [])))
    for entry in out:
        entry.setdefault("handle", "unknown")
    return out


def install(config: Config, path) -> Report:
    """Accept a package onto this machine, or refuse it with a reason."""
    root = Path(path).expanduser().resolve()
    if not root.is_dir():
        raise Refused(f"{root} is not a package directory")

    manifest = _read_json(root / MANIFEST, MANIFEST)
    _check_shipped_state(root)

    for field_name in _OWNERS_ALONE:
        if field_name in manifest:
            raise Refused(
                f"{MANIFEST} sets {field_name!r}, which is the owner's to set. "
                f"Installing an agent is not a way to grant one")

    agent_id = _check_id(manifest.get("id"), config)
    _check_requires(manifest)

    share = manifest.get("price_share", 1.0)
    try:
        share = float(share)
    except (TypeError, ValueError):
        raise Refused(f"price_share {share!r} is not a number")
    if not 0.0 <= share <= 1.0:
        raise Refused(f"price_share {share} is outside 0-1 — it is a fraction "
                      f"of one slice, not a multiplier on it")

    outward = _check_outward(manifest.get("outward"), MANIFEST)
    tools = [str(t) for t in (manifest.get("tools") or [])]
    roster_path = root / ROSTER
    if roster_path.exists():
        roster = _read_json(roster_path, ROSTER)
        # Both files declare outward classes. Checking one is checking neither.
        _check_outward(roster.get("outward"), ROSTER)
        tools = [str(t) for t in (roster.get("tools") or tools)]

    authors = _authors(root, manifest)
    spec_text = ""
    if (root / SPEC).exists():
        spec_text = (root / SPEC).read_text()[:4000]

    entry = {"id": agent_id, "role": WORKER_ROLE, "spec": "claude-code",
             "tools": tools, "ceiling": EVERYDAY_CEILING,
             "about": [w for w in re.findall(r"[a-z]{4,}",
                                             str(manifest.get("purpose") or "").lower())][:8],
             "market": {"version": str(manifest.get("version") or ""),
                        "purpose": str(manifest.get("purpose") or ""),
                        "authors": authors, "source": str(root),
                        "outward": outward, "price_share": share}}
    _write_entry(config, entry)
    _installed_dirs(config, agent_id)
    (config.root / "market").mkdir(parents=True, exist_ok=True)
    (config.root / "market" / f"{agent_id}.md").write_text(spec_text)

    return Report(agent_id=agent_id, version=entry["market"]["version"],
                  purpose=entry["market"]["purpose"], authors=authors,
                  source=str(root))


def installed(config: Config) -> List[Report]:
    """What was installed from the market, as opposed to what shipped."""
    raw = _raw(config)
    out = []
    for entry in raw.get("agents", {}).get("list", []):
        block = entry.get("market")
        if not block:
            continue
        out.append(Report(agent_id=entry["id"],
                          version=str(block.get("version") or ""),
                          purpose=str(block.get("purpose") or ""),
                          authors=list(block.get("authors") or []),
                          source=str(block.get("source") or "")))
    return out


def remove(config: Config, agent_id: str) -> Report:
    """Take an installed package out of the roster. Its folder stays.

    Same reasoning as retiring: a folder is the record of what an agent did,
    and an uninstall that deleted it would make the record of the work depend
    on still wanting the tool.
    """
    raw = _raw(config)
    entries = raw.get("agents", {}).get("list", [])
    found = [e for e in entries if e.get("id") == agent_id]
    if not found:
        raise Refused(f"{agent_id!r} is not installed here")
    if not found[0].get("market"):
        raise Refused(f"{agent_id!r} shipped with this machine — it is not a "
                      f"market listing, and removing one is not an uninstall. "
                      f"To take it out of routing: sarsi ceiling / retire")
    block = found[0]["market"]
    raw["agents"]["list"] = [e for e in entries if e.get("id") != agent_id]
    raw["bindings"] = [b for b in (raw.get("bindings") or [])
                       if b.get("agentId") != agent_id]
    _save(config, raw)
    return Report(agent_id=agent_id, version=str(block.get("version") or ""),
                  purpose=str(block.get("purpose") or ""),
                  authors=list(block.get("authors") or []))


# ── the registry file ─────────────────────────────────────────────────

def _path(config: Config) -> Path:
    return Path(config.path) if config.path else config_path(config.root)


def _raw(config: Config) -> Dict[str, Any]:
    try:
        return json.loads(_path(config).read_text())
    except FileNotFoundError:
        raise Refused(f"no registry at {_path(config)}; run `sarsi init` first")


def _save(config: Config, raw: Dict[str, Any]) -> None:
    _path(config).write_text(json.dumps(raw, indent=2, sort_keys=True))


def _write_entry(config: Config, entry: Dict[str, Any]) -> None:
    raw = _raw(config)
    raw.setdefault("agents", {}).setdefault("list", []).append(entry)
    # A binding per door, like every shipped agent, so the CLI can reach it.
    raw.setdefault("bindings", []).append(
        {"agentId": entry["id"],
         "match": {"channel": "cli", "accountId": entry["id"]}})
    _save(config, raw)


def _installed_dirs(config: Config, agent_id: str) -> None:
    """Empty, and made here rather than shipped. See `_check_shipped_state`."""
    agent = Agent(id=agent_id, role=WORKER_ROLE, root=config.root)
    for d in (agent.workspace, agent.host, agent.tasks, agent.sessions,
              agent.selfmodel):
        d.mkdir(parents=True, exist_ok=True)
