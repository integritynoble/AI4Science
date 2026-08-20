"""Port B->A: the persistent transport must build its launch argv from the
config's declared `args`, not a hardcoded vector.

Side A's factories hardcode the argv (`opencode acp --pure`, `openclaw acp
--session ...`). None of them read the acpx entry's `args`, so a config that
says `{"command": ".../opencode", "args": ["acp"]}` would still launch bare
`opencode` on the direct path — which hangs forever on a non-TTY pipe. B solved
this with `agent_argv`; A reuses it (shared, not re-implemented) via a
config-resolving factory.
"""
import json

from ai4science.harness.agents.sarsi import acp
from ai4science.harness.agents.sarsi import acp_backend


def _cfg(tmp_path):
    p = tmp_path / "openclaw.json"
    p.write_text(json.dumps({
        "agents": {"list": [
            {"id": "sarsi-open",
             "runtime": {"type": "acp", "acp": {"agent": "opencode"}}}]},
        "plugins": {"entries": {"acpx": {"config": {"agents": {
            "opencode": {"command": "/bin/opencode", "args": ["acp"]}}}}}},
    }))
    return p


def test_agent_argv_is_shared_with_the_backend():
    assert acp.agent_argv is acp_backend.agent_argv


def test_config_factory_carries_the_declared_args(tmp_path):
    """The whole point: `acp` must survive into the runtime's launch command."""
    rt = acp.acp_runtime_from_config("sarsi-open", config_path=str(_cfg(tmp_path)))
    assert rt._cmd == ["/bin/opencode", "acp"]


def test_config_factory_caches_like_the_other_factories(tmp_path):
    p = str(_cfg(tmp_path))
    a = acp.acp_runtime_from_config("sarsi-open", config_path=p)
    b = acp.acp_runtime_from_config("sarsi-open", config_path=p)
    assert a is b
