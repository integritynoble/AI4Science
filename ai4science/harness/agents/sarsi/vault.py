"""`VLT` — the vault: policy first, then ask.

Local only. It answers **ALLOW** or **DENY**, and on allow hands the secret to
the caller on this machine. Nothing else here is negotiable:

| It may not | Because |
|---|---|
| put a secret in a directive, report, workspace, plan, prompt or ledger | the record says *which* secret was needed, never what it is |
| let an agent read the store | **the only interface is the question** |
| treat a per-use approval as a standing one | an agent approved five times would have granted itself authority by persistence |

Two stages:

1. **standing policy** — rules the owner wrote once. Answers alone when one
   matches, allow or deny, with no interruption.
2. **per-use prompt** — the owner is asked, for this one use, and told which
   secret and what for. Reached when no rule matches, **or** when the rule
   allows but the act is outward.

## The grammar that refuses the broad form

The dangerous policy is the one a tired owner writes to stop being interrupted:
*"abraham may use the card."* That must not be **expressible**, which is
stronger than discouraged. So for a money act, `limit`, `counterparty` and
`rate` are required fields and there is no wildcard counterparty. *"Up to £40 at
the grocery, twice a week"* is expressible; the broad form fails validation and
is never written.

Only permitting is constrained. Refusing is always expressible.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ai4science.harness.agents.sarsi import ledger
from ai4science.harness.agents.sarsi.registry import Config

SECRETS_NAME = "secrets.json"
POLICIES_NAME = "policies.json"

ALLOW = "ALLOW"
DENY = "DENY"

#: acts that move money. Their policies must name a limit, a payee class, and a rate.
MONEY_ACTS = {"pay", "charge", "transfer", "subscribe"}
#: counterparty classes that are not classes at all
_WILDCARDS = {"", "*", "any", "all", "anyone", "anything"}


class PolicyRefused(Exception):
    """The policy is broader than the grammar allows. Never written."""


@dataclass(frozen=True)
class Decision:
    allowed: bool
    stage: int                       # 1 = standing policy, 2 = the owner was asked
    secret: str
    reason: str = ""
    value: Optional[str] = None      # only ever set on an allow


# ── the store ─────────────────────────────────────────────────────────

def put(config: Config, name: str, value: str) -> None:
    """Owner-only. Adds or replaces one secret."""
    store = _read(config, SECRETS_NAME)
    store[name] = value
    _write(config, SECRETS_NAME, store)


def names(config: Config) -> List[str]:
    """The names, sorted. **Never the values** — the only interface is the
    question, and the owner still needs to know what they have."""
    return sorted(_read(config, SECRETS_NAME))


def forget(config: Config, name: str) -> bool:
    store = _read(config, SECRETS_NAME)
    existed = store.pop(name, None) is not None
    _write(config, SECRETS_NAME, store)
    return existed


# ── stage 1: the standing policy ──────────────────────────────────────

def write_policy(config: Config, *, agent_id: str, secret: str, act: str,
                 decision: str, limit: Optional[Dict[str, Any]] = None,
                 counterparty: Optional[Dict[str, Any]] = None,
                 rate: Optional[Dict[str, Any]] = None,
                 expires: Optional[str] = None) -> Dict[str, Any]:
    decision = (decision or "").upper()
    if decision not in (ALLOW, DENY):
        raise PolicyRefused(f"a policy decides {ALLOW} or {DENY}, not {decision!r}")
    if decision == ALLOW and act in MONEY_ACTS:
        _require_money_grammar(limit, counterparty, rate)
    policy = {"agent": agent_id, "secret": secret, "act": act,
              "decision": decision, "limit": limit, "counterparty": counterparty,
              "rate": rate, "expires": expires}
    policies = policies_raw(config)
    policies.append(policy)
    _write(config, POLICIES_NAME, policies)
    return policy


def _require_money_grammar(limit, counterparty, rate) -> None:
    """The three fields that turn *"may use the card"* into *"up to £40 at the
    grocery, twice a week."* All required; the counterparty may not be a
    wildcard, because a wildcard payee class **is** the broad form wearing the
    narrow form's clothes."""
    if not limit or "amount" not in limit:
        raise PolicyRefused("a money policy must name a limit (amount + currency)")
    if not counterparty or "class" not in counterparty:
        raise PolicyRefused("a money policy must name a counterparty class")
    if str(counterparty.get("class", "")).strip().lower() in _WILDCARDS:
        raise PolicyRefused(
            f"{counterparty.get('class')!r} is not a counterparty class — a "
            f"policy that names any payee is 'may use the card' with extra steps")
    if not rate or "uses" not in rate:
        raise PolicyRefused("a money policy must name a rate (uses + per)")


def policies_raw(config: Config) -> List[Dict[str, Any]]:
    data = _read(config, POLICIES_NAME)
    return data if isinstance(data, list) else []


def policies(config: Config) -> List[Dict[str, Any]]:
    return policies_raw(config)


def _match(config: Config, agent_id: str, secret: str, act: str) -> Optional[Dict[str, Any]]:
    for policy in policies_raw(config):
        if (policy.get("agent") == agent_id and policy.get("secret") == secret
                and policy.get("act") == act):
            return policy
    return None


# ── the question ──────────────────────────────────────────────────────

def ask(config: Config, *, agent_id: str, secret: str, act: str, purpose: str,
        prompt: Callable[..., Any], outward: bool = False,
        standing_grants: bool = True, now=time.time) -> Decision:
    """The only way to reach a secret. Returns ALLOW/DENY, and on allow the value.

    `standing_grants=False` (abraham) means stage 1 never answers: that agent's
    authority starts at nothing and every use is the owner's call.
    """
    store = _read(config, SECRETS_NAME)
    known = secret in store

    policy = _match(config, agent_id, secret, act) if standing_grants else None
    if policy is not None and not (outward and policy.get("decision") == ALLOW):
        # An outward act is never settled by a standing allow: leaving the
        # machine stops at the owner even when the read was pre-approved.
        allowed = policy.get("decision") == ALLOW and known
        reason = (f"standing policy: {policy.get('decision')} {act} on {secret}"
                  if known else f"no secret named {secret} is held")
        return _record(config, Decision(allowed=allowed, stage=1, secret=secret,
                                        reason=reason,
                                        value=store.get(secret) if allowed else None),
                       agent_id=agent_id, act=act, now=now)

    if not known:
        # Deny before asking: the owner cannot usefully approve a secret that is
        # not there, and the denial names it so they can add it.
        return _record(config, Decision(False, 2, secret,
                                        f"no secret named {secret} is held; add "
                                        f"it and ask again"),
                       agent_id=agent_id, act=act, now=now)

    answer = None
    try:
        answer = prompt(secret=secret, purpose=purpose, agent=agent_id, act=act)
    except Exception:
        answer = None                     # an error is not an approval
    allowed = _is_yes(answer)
    reason = (f"you allowed {act} on {secret} for this use"
              if allowed else
              f"not allowed: {act} on {secret} was refused or unanswered")
    # NOTE: nothing here writes a policy. Promotion from stage 2 to stage 1 is an
    # owner act (`write_policy`), never an inference from repeated approvals.
    return _record(config, Decision(allowed, 2, secret, reason,
                                    value=store.get(secret) if allowed else None),
                   agent_id=agent_id, act=act, now=now)


def _is_yes(answer: Any) -> bool:
    if answer is True:
        return True
    return str(answer or "").strip().lower() in {"y", "yes", "allow", "approve", "ok"}


def _record(config: Config, decision: Decision, *, agent_id: str, act: str,
            now) -> Decision:
    # which secret, and what was decided — never the value
    ledger.append(config, "vault",
                  {"agent": agent_id, "secret": decision.secret, "act": act,
                   "decision": ALLOW if decision.allowed else DENY,
                   "stage": decision.stage, "reason": decision.reason},
                  now=now)
    return decision


# ── files ─────────────────────────────────────────────────────────────

def _path(config: Config, name: str) -> Path:
    return config.vault_dir / name


def _read(config: Config, name: str):
    path = _path(config, name)
    if not path.exists():
        return [] if name == POLICIES_NAME else {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return [] if name == POLICIES_NAME else {}


def _write(config: Config, name: str, data) -> None:
    path = _path(config, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True))
    try:
        path.chmod(0o600)
    except Exception:
        pass
