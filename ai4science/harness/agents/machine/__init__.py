"""Machine Agent — governed local-machine + Claude-Code bootstrap (work family).

An untrusted proposer that manages the local machine (Linux/macOS/Windows) and
bootstraps other agents (Claude Code first): detect the OS, install Claude Code,
grant the specific permissions it needs, and broker account logins. Safer than an
autonomous computer-use agent by construction: a CLOSED registry of vetted
operations (no arbitrary host commands), consequential actions owner-gated,
logins credential-brokered (the agent never sees the secret), everything audited.
"""
from ai4science.harness.agents.machine.capabilities import detect_machine
from ai4science.harness.agents.machine.operations import (
    Operation,
    default_operations,
    CONSEQUENTIAL_SIDE_EFFECTS,
)
from ai4science.harness.agents.machine.agent import run_machine
from ai4science.harness.agents.machine.session import (
    classify_command,
    decide_tool_call,
    SessionDriver,
)

__all__ = [
    "detect_machine",
    "Operation",
    "default_operations",
    "CONSEQUENTIAL_SIDE_EFFECTS",
    "run_machine",
    "classify_command",
    "decide_tool_call",
    "SessionDriver",
]
