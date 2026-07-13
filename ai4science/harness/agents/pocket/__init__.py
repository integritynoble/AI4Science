"""Pocket agent — the on-device (Tier-D) fixed-tool agent.

A testable Python reference of the iPhone agent's architecture: a closed,
vetted tool registry executed directly (no sandbox, no arbitrary code), gated
by OS-style permissions and a low risk ceiling. Consequential actions are not
in the registry — they route out to a Host agent under an owner gate. The
reference tools are stubs; a native iOS app swaps in EventKit/HealthKit/Notes
implementations behind the same interface.
"""
from ai4science.harness.agents.pocket.tools import (
    Tool,
    default_registry,
    CONSEQUENTIAL_KINDS,
    consequential_kind,
)
from ai4science.harness.agents.pocket.agent import run_pocket

__all__ = [
    "Tool",
    "default_registry",
    "CONSEQUENTIAL_KINDS",
    "consequential_kind",
    "run_pocket",
]
