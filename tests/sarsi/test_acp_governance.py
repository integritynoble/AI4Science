"""Amendment: an ACP session must be governed by the SAME boundary a tmux
session is — the project `.claude/settings.json` PreToolUse hook.

Proven live before this was written: an acpx-spawned `claude` DOES load the
project hook and DOES block on it (`hook_event_name: PreToolUse`, the artifact
absent, the agent reporting the block in its own words). So the hook is a real
control on this channel, not a hopeful one — which is what makes refusing to
start without it the honest behaviour rather than theatre.

`AcpRuntime.start` accepted `govern` and `writable` and used NEITHER. Every
caller asking for a governed session got an ungoverned one and `ok: True`.
"""
import pytest
from ai4science.harness.agents.sarsi import acp_backend as acp


class _Conn:
    def __init__(self): self.closed = False
    def initialize(self): return {"protocolVersion": 1}
    def new_session(self, cwd, env=None): return "sid-1"
    def close(self): self.closed = True


def _runtime(calls, *, wire=None, connect=None):
    def _connect(**kw):
        calls.append(("connect", kw.get("cwd")))
        return _Conn()
    return acp.AcpRuntime(agent_id="ai4sci", connect=connect or _connect,
                          wire=wire)


def test_governed_start_writes_the_hook_before_the_peer_spawns(tmp_path):
    """The hook must exist BEFORE the executor launches: claude reads project
    settings at session start, so a hook written afterwards governs nothing."""
    calls = []
    def wire(cwd, *, ceiling, writable):
        calls.append(("wire", str(cwd), ceiling, tuple(writable or ())))
    rt = _runtime(calls, wire=wire)
    out = rt.start("t", str(tmp_path), govern=True, ceiling="A2",
                   writable=[str(tmp_path / "w")])
    assert out["ok"] is True
    assert calls[0] == ("wire", str(tmp_path), "A2", (str(tmp_path / "w"),))
    assert calls[1][0] == "connect", "the hook must be wired before the spawn"


def test_ungoverned_start_writes_no_hook(tmp_path):
    """`govern=False` is a real choice, not a synonym for 'governed anyway'."""
    calls = []
    def wire(cwd, **kw): calls.append(("wire",))
    rt = _runtime(calls, wire=wire)
    out = rt.start("t", str(tmp_path), govern=False, ceiling="A2")
    assert out["ok"] is True
    assert not any(c[0] == "wire" for c in calls)


def test_a_hook_that_cannot_be_written_REFUSES_the_session(tmp_path):
    """The whole point. An ungoverned session is not the one that was asked
    for, so it is not started — and the peer is never spawned."""
    calls = []
    def wire(cwd, **kw):
        calls.append(("wire",))
        raise OSError("read-only .claude")
    rt = _runtime(calls, wire=wire)
    out = rt.start("t", str(tmp_path), govern=True, ceiling="A2")
    assert out["ok"] is False
    assert out["outcome"] == acp.ERRORED
    assert "govern" in out["reason"].lower()
    assert not any(c[0] == "connect" for c in calls), \
        "refusing to govern must also refuse to spawn"


def test_the_refusal_says_nothing_ran(tmp_path):
    """A governance refusal IS an error — `verdict_of` says `errored`, and that
    is correct: `None` means "no verdict yet", which would leave a supervisor
    waiting on a session that will never exist.

    What must stay distinguishable is *never started* from *ran and failed*.
    The discriminator is physical rather than editorial: no session id and no
    pid, because no peer was ever spawned.
    """
    def wire(cwd, **kw): raise OSError("nope")
    rt = _runtime([], wire=wire)
    out = rt.start("t", str(tmp_path), govern=True, ceiling="A2")
    assert out["ok"] is False
    assert acp.verdict_of(out) == acp.ERRORED
    assert out.get("acp_session_id") is None
    assert out.get("pid") is None


def test_default_wire_is_the_same_writer_the_tmux_path_uses(tmp_path):
    """Two governance writers would be two boundaries that can disagree."""
    from ai4science.harness.agents.machine import claude_driver
    assert acp._default_wire() is claude_driver.ensure_governance_hook
