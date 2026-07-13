"""Read-only monitoring views for the manager console. No writes, fail-safe."""
from __future__ import annotations


def registry_view(specs) -> list:
    """A read-only enumeration of the owner's available agents."""
    return [{"name": s.name, "title": s.title, "tier": s.tier, "category": s.category,
             "profiles": list(s.supported_profiles), "keywords": list(s.keywords or ())}
            for s in specs]


def run_status(client, run_id: str) -> dict:
    """Live per-run status via a read-only client query; fail-safe."""
    if client is None:
        return {"active": False, "stop_reason": "no client"}
    try:
        tripped = client.tripwire_triggered(run_id)   # True if inactive/tripped/unreachable
        return {"active": not tripped,
                "stop_reason": None if not tripped else "inactive-or-tripped"}
    except Exception:
        return {"active": False, "stop_reason": "unavailable"}


def agent_lkg(client, name: str) -> dict | None:
    """The RSI-promoted last-known-good config for an agent (read-only)."""
    if client is None:
        return None
    try:
        return client.get_last_known_good("agent", name)
    except Exception:
        return None
