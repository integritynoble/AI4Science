"""Port B->A: the persistent transport must GOVERN before it spawns.

`session.assign` already calls `runtime.start(..., govern=True, ceiling=...,
writable=...)`. Side A's `AcpRuntime.start(self, name, cwd, **_)` swallowed all
of it through `**_` and spawned an ungoverned peer while returning ok=True —
every caller that asked for governance got none and was told it succeeded. That
is the more dangerous half of the split.

The fix reuses the SAME writer the backend and the tmux path use (`_default_wire
-> ensure_governance_hook`), so there are not two governance boundaries that can
disagree. A `govern=True` request is honoured or the session is refused, never
dropped.
"""
from ai4science.harness.agents.sarsi import acp
from ai4science.harness.agents.sarsi import acp_backend


def test_default_wire_is_shared_with_the_backend():
    assert acp._default_wire is acp_backend._default_wire


def _no_subprocess(monkeypatch, order):
    def fake_connect(self, timeout=30.0):
        order.append("connect")
        self._session_id = "sid"
    monkeypatch.setattr(acp.AcpClient, "connect", fake_connect)


def test_governed_start_refuses_when_the_wire_fails(tmp_path, monkeypatch):
    """govern=True and an unwritable hook => refused, and the peer is NOT
    spawned. Returning ok=True here would hand back an ungoverned executor."""
    order = []
    _no_subprocess(monkeypatch, order)

    def wire(cwd, *, ceiling, writable):
        raise RuntimeError("cannot write .claude/settings.json")

    rt = acp.AcpRuntime()
    out = rt.start("t", str(tmp_path), govern=True, ceiling="A2", wire=wire)
    assert out["ok"] is False
    assert "govern" in out["reason"].lower()
    assert "t" not in rt._clients          # nothing was spawned
    assert "connect" not in order          # the peer never launched


def test_governed_start_writes_the_hook_before_connecting(tmp_path, monkeypatch):
    """The hook must exist BEFORE the peer launches — a hook written after the
    session opens governs nothing."""
    order = []
    _no_subprocess(monkeypatch, order)
    seen = {}

    def wire(cwd, *, ceiling, writable):
        order.append("wire")
        seen.update(cwd=str(cwd), ceiling=ceiling, writable=tuple(writable or ()))

    rt = acp.AcpRuntime()
    out = rt.start("t", str(tmp_path), govern=True, ceiling="A2",
                   writable=[str(tmp_path / "w")], wire=wire)
    assert out["ok"] is True
    assert order == ["wire", "connect"]           # ordering is the whole point
    assert seen["ceiling"] == "A2"
    assert seen["writable"] == (str(tmp_path / "w"),)


def test_ungoverned_start_stays_backward_compatible(tmp_path, monkeypatch):
    """A caller that does not ask to be governed is not forced to be, and no
    wire is called."""
    order = []
    _no_subprocess(monkeypatch, order)
    rt = acp.AcpRuntime()
    out = rt.start("t", str(tmp_path))
    assert out["ok"] is True
    assert order == ["connect"]
