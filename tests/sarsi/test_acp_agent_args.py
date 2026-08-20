"""An acpx agent entry may carry `args`, and dropping them is silent.

`openclaw.json` declares a launcher as a command PLUS an argument vector:

    "opencode": {"command": ".../bin/opencode", "args": ["acp"]}

`agent_command()` read only `command`. For `opencode` the difference is not
cosmetic: bare `opencode` is documented `[default] = start opencode tui`, so
under a non-TTY pipe it emits terminal-control bytes and blocks forever. The
ACP client then sees no stdout, an EMPTY stderr, and a timeout — which reads
exactly like a hung agent rather than a wrong invocation. Measured, same
binary, same account:

    bare `opencode`      exit 124, 3801 bytes of ANSI art, ZERO json-rpc
    `opencode acp`       exit 0,   valid initialize result, sub-second

The config was right the whole time. This client was launching something the
config never asked for, and the failure named the wrong culprit — which is why
the fault was first attributed to the agent's owner rather than to us.
"""
import pytest
from ai4science.harness.agents.sarsi import acp_backend as acp


def _cfg(tmp_path, agent_entry):
    import json
    p = tmp_path / "openclaw.json"
    p.write_text(json.dumps({
        "agents": {"list": [
            {"id": "sarsi-open",
             "runtime": {"type": "acp", "acp": {"agent": "opencode"}}}]},
        "plugins": {"entries": {"acpx": {"config": {"agents": agent_entry}}}},
    }))
    return p


def test_args_are_carried_into_the_argv(tmp_path):
    """The whole point: `acp` must survive into what is executed."""
    cfg = _cfg(tmp_path, {"opencode": {"command": "/bin/opencode",
                                       "args": ["acp"]}})
    assert acp.agent_argv("sarsi-open", config_path=cfg) == \
        ["/bin/opencode", "acp"]


def test_no_args_is_just_the_command(tmp_path):
    cfg = _cfg(tmp_path, {"opencode": {"command": "/bin/opencode"}})
    assert acp.agent_argv("sarsi-open", config_path=cfg) == ["/bin/opencode"]


def test_a_declared_vector_makes_the_command_literal(tmp_path):
    """When `args` is declared the command is a PATH, so a launcher under a
    directory with a space survives instead of becoming two argv entries."""
    cfg = _cfg(tmp_path, {"opencode": {"command": "/opt/my tools/opencode",
                                       "args": ["acp"]}})
    assert acp.agent_argv("sarsi-open", config_path=cfg) == \
        ["/opt/my tools/opencode", "acp"]


def test_without_a_vector_an_embedded_argument_still_splits(tmp_path):
    """Existing configs bake arguments into the command string. Re-reading
    those as one path would break every one of them, so that shape is kept."""
    cfg = _cfg(tmp_path, {"opencode": {"command": "/usr/bin/python /some/x.py"}})
    assert acp.agent_argv("sarsi-open", config_path=cfg) == \
        ["/usr/bin/python", "/some/x.py"]


def test_args_must_be_strings(tmp_path):
    """A number or None in the vector would reach subprocess and raise there,
    far from the config that caused it."""
    cfg = _cfg(tmp_path, {"opencode": {"command": "/bin/opencode",
                                       "args": ["acp", 3, None]}})
    assert acp.agent_argv("sarsi-open", config_path=cfg) == \
        ["/bin/opencode", "acp", "3"]


def test_agent_command_still_returns_the_bare_command(tmp_path):
    """Kept for callers that want the executable itself, not the invocation."""
    cfg = _cfg(tmp_path, {"opencode": {"command": "/bin/opencode",
                                       "args": ["acp"]}})
    assert acp.agent_command("sarsi-open", config_path=cfg) == "/bin/opencode"
