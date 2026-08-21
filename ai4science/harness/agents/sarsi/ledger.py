"""Append-only ledgers — the durable record of what was asked, decided, refused.

Four of them, all under `~/.sarsi/ledger/`:

| file | holds |
|---|---|
| `inbound.jsonl` | every turn admitted or dropped, and why |
| `directives.jsonl` | every directive issued |
| `reports.jsonl` | every report returned |
| `outward.jsonl` | every act that asked to leave the machine, and its outcome |
| `vault.jsonl` | every vault question and its ALLOW/DENY — **never** the secret |

Two properties, both enforced here rather than trusted to callers:

  * **append-only.** Nothing rewrites a line; a reader that meets a corrupt line
    skips it rather than losing the records after it.
  * **no secret ever enters a ledger.** Naming a secret is allowed and required
    (`VLT` must record *which* one was asked for, so the owner can grant it);
    carrying its value is refused at the write, which is the only place the rule
    is cheap to enforce.
"""
from __future__ import annotations

import fcntl
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List

from ai4science.harness.agents.sarsi.registry import Config

# Keys whose *value* is a credential. `secret` is deliberately absent: the vault
# ledger records the NAME of the secret it was asked for.
_SECRET_KEYS = {"bottoken", "token", "password", "apikey", "api_key",
                "credential", "credentials", "secretvalue", "secret_value",
                "access_token", "refresh_token"}


class SecretInLedger(Exception):
    """A record carried a credential. Refused — a ledger is not a store."""


def append(config: Config, name: str, record: Dict[str, Any], *,
           now: Callable[[], float] = time.time) -> Dict[str, Any]:
    _refuse_secrets(record)
    stamped = dict(record)
    stamped["at"] = _iso(now())
    path = _path(config, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX)
            fh.write(json.dumps(stamped, sort_keys=True) + "\n")
            fh.flush()
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)
    try:
        path.chmod(0o600)
    except Exception:
        pass
    return stamped


def read(config: Config, name: str) -> List[Dict[str, Any]]:
    path = _path(config, name)
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue          # a damaged line loses itself, never the rest
    return out


def count(config: Config, name: str, **match: Any) -> int:
    return sum(1 for r in read(config, name)
               if all(r.get(k) == v for k, v in match.items()))


def _path(config: Config, name: str) -> Path:
    return config.ledger_dir / f"{name}.jsonl"


def _refuse_secrets(record: Dict[str, Any]) -> None:
    for key in record:
        if str(key).lower().replace("-", "_").replace("_", "") in {
                k.replace("_", "") for k in _SECRET_KEYS}:
            raise SecretInLedger(
                f"{key!r} carries a credential; a ledger records that a secret "
                f"was needed, never what it is")


def _iso(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).isoformat(timespec="seconds")
