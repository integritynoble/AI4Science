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
import re
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


#: Credential material in free text. Two shapes, both high-confidence:
#: a named assignment that actually carries a value, and the issuer prefixes
#: that are credentials by construction. Deliberately NOT "the word password
#: appears" — a lesson that says "the password prompt appeared" is a lesson
#: worth keeping, and a filter that refuses it teaches people to stop writing
#: lessons.
_SECRET_TEXT = re.compile(
    # An explicit assignment: `password: hunter2`. The colon or equals is
    # itself the evidence that a value follows.
    r"(?:\b(?:api[_-]?key|apikey|password|passwd|passphrase|secret|token|"
    r"bearer|credential)\b\s*[:=]\s*\S{6,})"
    # `the api_key is sk-live-…` — prose, so the VALUE has to carry the
    # evidence instead. It must look like a credential: one token, at least
    # eight characters, containing a digit. "the mail.read secret is needed"
    # must stay writable — naming which secret was involved is required of the
    # vault, and a filter that refuses it deletes the record it exists to keep.
    r"|(?:\b(?:api[_-]?key|apikey|password|passwd|passphrase|secret|token|"
    r"bearer|credential)\b\s+(?:is|was)\s+"
    r"(?=[A-Za-z0-9_-]*\d)[A-Za-z0-9_-]{8,})"
    r"|(?:\bsk-[A-Za-z0-9_-]{12,})"
    r"|(?:\bgh[pousr]_[A-Za-z0-9]{16,})"
    r"|(?:\bgithub_pat_[A-Za-z0-9_]{20,})"
    r"|(?:\bxox[baprs]-[A-Za-z0-9-]{10,})"
    r"|(?:\bAKIA[0-9A-Z]{16}\b)"
    r"|(?:\bAIza[0-9A-Za-z_-]{30,})"
    r"|(?:-----BEGIN [A-Z ]*PRIVATE KEY-----)",
    re.I)

_FLAT_SECRET_KEYS = {k.replace("_", "") for k in _SECRET_KEYS}


def _refuse_secrets(record: Any, _where: str = "") -> None:
    """Refuse a record that carries a credential — at any depth, in any value.

    This used to look at top-level keys only, which covered the ledgers that
    existed when it was written and covered neither of the paths the semantic
    and episode channels actually use. Measured: a lesson whose *statement*
    read `the deploy api_key is sk-live-…` was written verbatim, and
    `semantic.render()` puts statements straight into the model's context. So
    the docstring's "no secret ever enters a ledger" was a claim the code did
    not enforce.

    Nested structures are walked, and string values are scanned. Naming a
    secret is still allowed and still required — the vault has to record WHICH
    one was asked for — so the text patterns match a value being carried, not
    a secret being mentioned.
    """
    if isinstance(record, dict):
        for key, value in record.items():
            flat = str(key).lower().replace("-", "_").replace("_", "")
            if flat in _FLAT_SECRET_KEYS:
                raise SecretInLedger(
                    f"{key!r} carries a credential; a ledger records that a "
                    f"secret was needed, never what it is")
            _refuse_secrets(value, f"{_where}.{key}" if _where else str(key))
        return
    if isinstance(record, (list, tuple, set)):
        for i, item in enumerate(record):
            _refuse_secrets(item, f"{_where}[{i}]")
        return
    if isinstance(record, str):
        hit = _SECRET_TEXT.search(record)
        if hit:
            raise SecretInLedger(
                f"the text at {_where or 'this record'!r} carries what looks "
                f"like a credential ({hit.group(0)[:12]}…); say WHICH secret is "
                f"involved, never its value")


def _iso(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).isoformat(timespec="seconds")
