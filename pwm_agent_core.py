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
    """Boot the standard AI4Science CLI/TUI, defaulted to one agent (mode).

    A standalone `pwm-<agent>` command calls run_cli("<agent>"). When
    default_agent is set and the user passes no explicit --mode/AI4SCIENCE_MODE,
    that agent's mode is preselected. (The persona/agent is chosen via the
    session MODE; AI4SCIENCE_AGENT selects the engine and is left untouched.)
    """
    import os
    # Re-discover installed agent packages now that the (possibly agent-package)
    # root import has fully initialized. The import-time reload in registry.py can
    # miss the root package's own entry point when THAT package is the entrypoint.
    from ai4science.harness.agents import registry
    registry.reload()
    from ai4science.cli import main as _main
    if default_agent and not os.environ.get("AI4SCIENCE_MODE"):
        os.environ["AI4SCIENCE_MODE"] = default_agent
    _main()
