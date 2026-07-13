"""The fixed tool registry for the on-device Pocket agent.

Every action surface is a vetted `Tool` executed *directly* — there is no
code-execution path and no sandbox. Each tool declares:

  * `permission`  — an OS-style grant it needs ("" = none). The agent may only
                    use a tool whose permission is in the owner's granted set;
                    ungranted → refused, never attempted.
  * `side_effect` — "read" | "reversible_write" | "notification" | "none".
                    Only these low-risk classes exist on-device. Anything
                    irreversible/external is deliberately absent from the
                    registry (see CONSEQUENTIAL_KINDS) and routes to a Host agent.
  * `fn(intent, ctx)` — the reference implementation (stub). A native iOS app
                    replaces `fn` with an EventKit/HealthKit/Notes call behind
                    this same signature.
  * `match`       — keywords for deterministic tool selection.

`ctx` is a plain dict the caller owns (the on-device app supplies the real
backing store); the reference tools use `ctx["notes"]`, `ctx["reminders"]`,
`ctx["calendar"]`, and `ctx["capabilities"]`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Tuple

# Action kinds that are NEVER performed on-device. If an intent maps to one of
# these, the Pocket agent refuses and hands off to a Host agent under an owner
# gate — the risk ceiling is enforced by the registry's *absence* of such tools
# plus this explicit route-out set.
CONSEQUENTIAL_KINDS: Tuple[str, ...] = (
    "spend",
    "publish",
    "delete_external",
    "deploy",
    "credentialed_call",
)

# Keyword → consequential kind. Deterministic; the native layer may replace this
# with a classifier, but the default must stay conservative (over-refuse, never
# under-refuse) because refusing merely defers to the owner-gated Host path.
_CONSEQUENTIAL_MATCH: Dict[str, Tuple[str, ...]] = {
    "spend": ("pay", "buy", "purchase", "transfer", "send money", "checkout", "order"),
    "publish": ("publish", "post", "tweet", "send email", "share publicly", "broadcast"),
    "delete_external": ("delete account", "wipe", "erase remote", "drop table", "delete file"),
    "deploy": ("deploy", "release", "ship to prod", "push to production"),
    "credentialed_call": ("api key", "with my password", "log in to", "authenticate to"),
}


def consequential_kind(intent: str) -> Optional[str]:
    """Return the consequential kind an intent triggers, or None. Conservative."""
    low = (intent or "").lower()
    for kind, phrases in _CONSEQUENTIAL_MATCH.items():
        if any(p in low for p in phrases):
            return kind
    return None


@dataclass(frozen=True)
class Tool:
    name: str
    permission: str                       # "" = no OS permission required
    side_effect: str                      # read | reversible_write | notification | none
    fn: Callable[[str, Dict[str, Any]], Any]
    match: Tuple[str, ...] = field(default_factory=tuple)


# --- reference tool implementations (stubs; native iOS swaps these fn's) ------

def _advise(intent: str, ctx: Dict[str, Any]) -> str:
    # A0 advisory text. The real device brokers this to a remote LLM; the
    # reference returns a deterministic acknowledgement so the loop is testable
    # without a model. An injected `advise` in run_pocket overrides this.
    return f"advisory: {intent.strip()}"


def _note_write(intent: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
    notes = ctx.setdefault("notes", [])
    text = intent.strip()
    notes.append(text)
    return {"written": text, "count": len(notes)}


def _note_read(intent: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
    return {"notes": list(ctx.get("notes", []))}


def _reminder_create(intent: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
    reminders = ctx.setdefault("reminders", [])
    text = intent.strip()
    reminders.append(text)
    return {"created": text, "count": len(reminders)}


def _calendar_read(intent: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
    # Read-only view of a calendar the device owns; never mutates.
    return {"events": list(ctx.get("calendar", []))}


def _capability_status(intent: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
    # Read-only peek at the learning agent's capability graph (owner's frontier),
    # if the device has synced one into ctx. No permission — it's the owner's own
    # data on the owner's device.
    caps = ctx.get("capabilities", {})
    return {"capabilities": dict(caps)}


def default_registry() -> Tuple[Tool, ...]:
    """The closed, vetted tool set. Ordered; selection prefers the first match."""
    return (
        Tool("note_write", "notes", "reversible_write", _note_write,
             match=("note", "write down", "jot", "remember that", "save note")),
        Tool("note_read", "notes", "read", _note_read,
             match=("my notes", "read notes", "what did i note", "show notes")),
        Tool("reminder_create", "reminders", "reversible_write", _reminder_create,
             match=("remind me", "reminder", "don't forget", "set a reminder")),
        Tool("calendar_read", "calendar", "read", _calendar_read,
             match=("calendar", "my schedule", "agenda", "what's on today", "appointments")),
        Tool("capability_status", "", "read", _capability_status,
             match=("my progress", "capability", "what have i learned", "learning status")),
        Tool("advise", "", "none", _advise,
             match=()),  # fallback only; never keyword-selected
    )
