"""Port A->B: the backend gains `resume`, A's best idea.

Side A can re-open a session after the gateway dies (`resume` = stop + start).
The backend had no such method. It gets one with the SAME honest limit A has and
B already documents for `_LIVE`: `resume` re-SPAWNS a fresh peer in THIS process
and reuses the recorded ceiling/cwd; it does not re-attach to a peer that is
still alive in ANOTHER OS process — that needs the gateway session API and is
implemented in neither module.
"""
from ai4science.harness.agents.sarsi import acp_backend as acp


class _Conn:
    def __init__(self):
        self.closed = False
        self.proc = None

    def initialize(self):
        return {"protocolVersion": 1}

    def new_session(self, cwd, env=None):
        return "sid"

    def close(self):
        self.closed = True


def _runtime(conns):
    def _connect(**kw):
        c = _Conn()
        conns.append(c)
        return c
    return acp.AcpRuntime(agent_id="ai4sci", connect=_connect,
                          wire=lambda *a, **k: None)


def test_resume_respawns_and_closes_the_old_peer(tmp_path):
    conns = []
    rt = _runtime(conns)
    rt.start("res-1", str(tmp_path), govern=True, ceiling="A1")
    assert len(conns) == 1 and conns[0].closed is False

    out = rt.resume("res-1", str(tmp_path))
    assert out["ok"] is True
    assert conns[0].closed is True         # the old peer was stopped
    assert len(conns) == 2                 # a fresh peer was spawned
    rt.stop("res-1")


def test_resume_preserves_the_prior_ceiling(tmp_path):
    conns = []
    rt = _runtime(conns)
    rt.start("res-2", str(tmp_path), govern=True, ceiling="A2")
    rt.resume("res-2", str(tmp_path))
    import ai4science.harness.agents.sarsi.acp_backend as m
    assert m._LIVE["res-2"]["ceiling"] == "A2"   # carried across the respawn
    rt.stop("res-2")


def test_resume_without_a_cwd_or_a_prior_session_is_errored():
    conns = []
    rt = _runtime(conns)
    out = rt.resume("never-started-here")
    assert out["ok"] is False
    assert out["outcome"] == acp.ERRORED
