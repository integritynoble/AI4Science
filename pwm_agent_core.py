"""Stable runtime contract for standalone PWM agent packages.

Agent repos import the runtime ONLY through this module. Everything here is
version-guaranteed by CONTRACT_VERSION; deep imports of ai4science.harness.*
are not. Physical extraction of the runtime into its own distribution moves
files behind this facade without changing it.
"""
from __future__ import annotations

CONTRACT_VERSION = 1

try:                                             # dist version, best-effort
    from importlib.metadata import version, PackageNotFoundError
    try:
        __version__ = version("pwm-agent-core")
    except PackageNotFoundError:
        __version__ = version("pwm-ai4science")
except Exception:
    __version__ = "0+unknown"

from ai4science.harness.agents.spec import AgentSpec
from ai4science.harness.agents.context import BuildContext
from ai4science.harness.tools.base import Registry, Tool
from ai4science.harness.agents.registry import (
    reload, get, dispatchable_targets, build_registry_for,
)
from ai4science.harness.agents.capabilities import register_agent_bundle


def run_cli(default_agent: str | None = None) -> None:
    """Boot the standard AI4Science CLI/TUI, defaulted to one agent.

    A standalone `pwm-<agent>` command calls run_cli("<agent>"). When
    default_agent is set and the user passes no explicit --agent/AI4SCIENCE_AGENT,
    that agent is preselected.
    """
    import os
    from ai4science.cli import main as _main
    if default_agent and not os.environ.get("AI4SCIENCE_AGENT"):
        os.environ["AI4SCIENCE_AGENT"] = default_agent
    _main()
