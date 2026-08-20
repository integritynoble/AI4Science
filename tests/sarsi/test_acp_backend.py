"""Both backends driven through **OpenClaw ACP**, not through a screen.

WHY THIS EXISTS, in one paragraph, because the tradeoff is the point.

`MachineRuntime` starts a tmux session and the supervision loop then reads the
SESSION SCREEN to decide what happened. There is a recorded defect in exactly
that, on this machine: a screen-scoring verifier cannot tell a CORRECT REFUSAL
from a FAILURE, nor an IDLE session from a dead one -- so a backend that did the
right thing and said no scores the same as one that crashed. ACP replaces the
screen with a gateway-managed session that has a durable handle and a
STRUCTURED end-of-turn reason. `refusal` is a first-class ACP stop reason. That
is the whole reason to move.

So the tests below are not "does it spawn". They are:

  1. the three outcomes a supervisor must never collapse, kept apart;
  2. acceptance is not a verdict -- the known consequence that the spawn returns
     at `accepted` while the executor runs on, which loses the verdict for a
     naive caller. The answer is to YIELD for the turn, and `verdict_of` refuses
     to read an acceptance as an answer;
  3. the durable handle is recorded on the task, so "which session ran this"
     survives the process that started it;
  4. both backends resolve to a real ACP agent id.

Everything here runs against an INJECTED transport. No subprocess, no gateway,
no network. The live end-to-end proof is a separate artifact-and-checksum run --
a test that needs a model is a test that fails for reasons that are not the
code's.
"""
import json
import sys
import time

import pytest

# This file tests the BACKEND implementation, which the reconciliation moved
# to `acp_backend.py`; `acp.py` is now the transport. Imported under the
# name `acp` so the body reads unchanged.
from ai4science.harness.agents.sarsi import acp_backend as acp
# `_rt` dispatch returns the TRANSPORT runtime (acp.py); the backend runtime
# is a different class since the reconciliation. Both are real; assert the
# one the dispatcher actually hands back.
from ai4science.harness.agents.sarsi import acp as acp_transport
from ai4science.harness.agents.sarsi import (backends, registry as reg,
                                             session as ses, task as tsk,
                                             worker as wk)


@pytest.fixture
def config(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path / "s"))
    root = tmp_path / "s"
    root.mkdir(parents=True, exist_ok=True)
    p = reg.config_path(root)
    p.write_text(json.dumps(reg.default_config(owner_id="7007143162")))
    c = reg.load(p)
    c.ensure_dirs()
    return c


class FakeConnection:
    """An ACP peer that says exactly what it was told to say.

    Written here, in the test, and NOT by the code under test: the whole claim
    being made is about how replies are CLASSIFIED, so a fake that borrowed the
    classifier would be marking its own work.
    """

    def __init__(self, reply=None, *, session_id="sid-1", fail_new=False):
        self.reply = reply if reply is not None else {
            "stop_reason": "end_turn", "text": "done"}
        self.session_id = session_id
        self.fail_new = fail_new
        self.prompts = []
        self.closed = False

    def initialize(self):
        return {"protocolVersion": 1}

    def new_session(self, cwd, env=None):
        if self.fail_new:
            raise RuntimeError("agent process exited before session/new")
        self.cwd = cwd
        return self.session_id

    def prompt(self, session_id, text):
        self.prompts.append((session_id, text))
        return dict(self.reply)

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def _no_leaked_sessions():
    """The live-connection registry is module-level, so one test's session
    would otherwise answer another test's send."""
    acp._LIVE.clear()
    yield
    acp._LIVE.clear()


def _runtime(reply=None, **kw):
    conn = FakeConnection(reply, **kw)
    rt = acp.AcpRuntime(connect=lambda **_: conn, agent_id="sarsi-ai4sci")
    return rt, conn


def _started(reply=None, name="s", **kw):
    """A runtime with a session already open — because a send with nothing
    open is a different test, and it is below."""
    rt, conn = _runtime(reply, **kw)
    out = rt.start(name, "/tmp", govern=True, ceiling="A0")
    assert out["ok"] is True, out
    return rt, conn


# -- 1. the three outcomes, kept apart --------------------------------------
#
# (a) refused and said why -- CORRECT, not a failure
# (b) attempted and errored
# (c) nothing happened
#
# The screen-scoring verifier collapses all three into FAIL. If this file ever
# collapses two of them, it has reintroduced the defect it was written for.

def test_a_refusal_is_a_correct_outcome_and_carries_its_reason():
    rt, _ = _started({"stop_reason": "refusal",
                      "text": "I will not delete the production database."})
    out = rt.send("s", "delete prod")

    assert out["outcome"] == acp.REFUSED
    assert out["ok"] is True, "a backend that refuses did its job"
    assert out["refused"] is True
    assert "production database" in out["reason"], out
    assert out["attempted"] is True


def test_an_error_is_a_failure_and_says_so():
    rt, _ = _started({"error": {"code": -32603, "message": "spawn ENOENT"}})
    out = rt.send("s", "do it")

    assert out["outcome"] == acp.ERRORED
    assert out["ok"] is False
    assert out["refused"] is False
    assert "ENOENT" in out["reason"]


def test_nothing_happening_is_its_own_outcome():
    """The idle-vs-dead half of the recorded defect. No stop reason and no text
    is not a refusal and not an error -- it is the absence of a turn, and
    reporting it as either is the lie."""
    rt, _ = _started({})
    out = rt.send("s", "do it")

    assert out["outcome"] == acp.SILENT
    assert out["ok"] is False
    assert out["refused"] is False
    assert out["attempted"] is False


def test_a_completed_turn_is_answered():
    rt, conn = _started({"stop_reason": "end_turn", "text": "wrote the file"})
    out = rt.send("s", "write the file")

    assert out["outcome"] == acp.ANSWERED
    assert out["ok"] is True
    assert out["text"] == "wrote the file"
    assert conn.prompts and conn.prompts[0][1] == "write the file"


def test_a_send_to_a_session_that_was_never_opened_is_an_error_not_a_silence():
    """Distinguished from (c): there IS no session, which is a caller mistake,
    not an executor that stayed quiet. Collapsing the two would hide a lost
    handle behind "it did nothing"."""
    rt, _ = _runtime()
    out = rt.send("never-opened", "go")
    assert out["outcome"] == acp.ERRORED
    assert "never-opened" in out["reason"]


def test_the_outcomes_are_distinct_strings():
    """A guard, not a tautology: collapsing two of these constants is exactly
    how the screen-scoring defect gets rebuilt, and it would otherwise be
    invisible -- every test above would still pass."""
    names = [acp.ANSWERED, acp.REFUSED, acp.ERRORED, acp.SILENT, acp.ACCEPTED]
    assert len(set(names)) == 5, names


# -- 2. acceptance is not a verdict -----------------------------------------

def test_starting_a_session_yields_no_verdict():
    """The known consequence, handled rather than rediscovered: the spawn
    returns while the executor runs on. A caller that reads the spawn result as
    an answer has invented one."""
    rt, _ = _runtime()
    out = rt.start("nm", "/tmp", govern=True, ceiling="A0")

    assert out["ok"] is True, "the session did start"
    assert out["outcome"] == acp.ACCEPTED
    assert acp.verdict_of(out) is None, "acceptance is not an answer"


def test_only_the_yield_carries_a_verdict():
    rt, _ = _started({"stop_reason": "end_turn", "text": "ok"}, name="nm")
    assert acp.verdict_of(rt.send("nm", "go")) == acp.ANSWERED


def test_a_refusal_survives_verdict_of_rather_than_reading_as_nothing():
    rt, _ = _started({"stop_reason": "refusal", "text": "no: that is outside A0"},
                     name="nm")
    assert acp.verdict_of(rt.send("nm", "go")) == acp.REFUSED


# -- 3. the durable handle --------------------------------------------------

def test_the_session_handle_is_durable_and_names_the_acp_agent():
    rt, _ = _runtime(session_id="ai4sci-abc123")
    out = rt.start("nm", "/tmp", govern=True, ceiling="A0")

    assert out["runtime"] == "acp"
    assert out["acp_session_id"] == "ai4sci-abc123"
    assert out["agent_id"] == "sarsi-ai4sci"
    assert out["name"] == "nm"


def test_a_session_that_will_not_start_is_reported_not_pretended():
    rt, _ = _runtime(fail_new=True)
    out = rt.start("nm", "/tmp", govern=True, ceiling="A0")
    assert out["ok"] is False
    assert "session/new" in (out.get("reason") or "")


def test_assign_records_the_acp_handle_on_the_task(config, monkeypatch):
    """Read back OFF DISK. The point of a durable handle is that it outlives
    the process that made it."""
    conn = FakeConnection(session_id="ai4sci-durable")
    monkeypatch.setattr(acp, "connect_stdio", lambda **_: conn)

    a = config.agents["sarsi-worker"]
    t = tsk.create(config, a, wk.Directive(agent_id=a.id, goal="g"))
    t.plan_agreed = True
    t = ses.assign(config, a, t, runtime=ses._rt(None, t),
                   installed=lambda: set())

    record = json.loads((tsk.dir_of(a, t.id) / tsk.RECORD_NAME).read_text())
    assert record["session"]["runtime"] == "acp"
    assert record["session"]["acp_session_id"] == "ai4sci-durable"
    assert record["session"]["agent_id"] == "sarsi-ai4sci"


# -- 4. both backends are ACP-driven ----------------------------------------

def test_both_backends_name_an_acp_agent():
    assert backends.acp_agent_for("sarsi-ai4sci") == "sarsi-ai4sci"
    assert backends.acp_agent_for("sarsi-claude") == "sarsi-claude"
    assert backends.acp_agent_for("sarsi-pwm") == "sarsi-ai4sci", "the alias too"


def test_every_backend_is_driven_through_acp():
    for name in backends.NAMES:
        assert backends.driver_for(name) == "acp", name


def test_runtime_for_a_task_is_the_acp_runtime(config):
    a = config.agents["sarsi-worker"]
    for backend in ("sarsi-ai4sci", "sarsi-claude", "sarsi-pwm"):
        t = tsk.create(config, a, wk.Directive(agent_id=a.id, goal="g"),
                       backend=backend)
        rt = ses._rt(None, t)
        assert isinstance(rt, acp.AcpRuntime), backend
        assert rt.agent_id == backends.acp_agent_for(backend)


OPENCLAW = {
    "agents": {"list": [
        {"id": "sarsi-worker"},
        {"id": "sarsi-claude", "runtime": {"type": "acp", "acp": {
            "agent": "claude", "backend": "acpx", "cwd": "/w"}}},
        {"id": "sarsi-ai4sci", "runtime": {"type": "acp", "acp": {
            "agent": "ai4sci", "backend": "acpx", "cwd": "/w"}}},
        {"id": "sarsi-orphan", "runtime": {"type": "acp", "acp": {
            "agent": "nothing-installed", "backend": "acpx"}}},
    ]},
    "plugins": {"entries": {"acpx": {"config": {
        "agents": {"ai4sci": {"command": "/bin/echo"}}}}}},
}


@pytest.fixture
def openclaw(tmp_path):
    p = tmp_path / "openclaw.json"
    p.write_text(json.dumps(OPENCLAW))
    return p


def test_the_command_is_found_through_the_engine_not_the_agent_id(openclaw):
    """Two hops, on purpose. `agents.list[id].runtime.acp.agent` names an
    ENGINE, and the engine is what has a command. Looking the agent id up
    directly in the acpx table is how a rename silently stops resolving."""
    assert acp.engine_of("sarsi-ai4sci", config_path=openclaw) == "ai4sci"
    assert acp.agent_command("sarsi-ai4sci", config_path=openclaw) == "/bin/echo"


def test_the_bundled_claude_wrapper_is_used_by_name_only(openclaw, monkeypatch,
                                                         tmp_path):
    """acpx supplies a claude wrapper, so `sarsi-claude` has no command entry.
    It is reached BY ENGINE NAME -- never as a general fallback, or every
    misconfigured agent would quietly launch Claude."""
    wrapper = tmp_path / "claude-agent-acp-wrapper.mjs"
    wrapper.write_text("// pretend")
    monkeypatch.setattr(acp, "BUNDLED", {"claude": wrapper})

    assert acp.agent_command("sarsi-claude", config_path=openclaw) == str(wrapper)
    with pytest.raises(acp.AcpUnavailable):
        acp.agent_command("sarsi-orphan", config_path=openclaw)


def test_an_unconfigured_agent_refuses_rather_than_guessing_a_command(openclaw):
    """Running the wrong engine under the right label is the failure
    `backends.spec_for` already refuses to commit."""
    with pytest.raises(acp.AcpUnavailable) as e:
        acp.agent_command("sarsi-nobody", config_path=openclaw)
    assert "sarsi-nobody" in str(e.value)

    with pytest.raises(acp.AcpUnavailable) as e:
        acp.agent_command("sarsi-worker", config_path=openclaw)
    assert "sarsi-worker" in str(e.value)


# -- 5. the wire, against a REAL subprocess ---------------------------------
#
# Everything above uses an injected transport, which cannot show a framing
# defect. These two drive an actual child process over an actual pipe, because
# the one bug this module has had was invisible to every fake:
#
#   `_read` used `select.select()` on the reader. A peer that writes its
#   `session/update` and its `session/prompt` response in one go leaves both
#   lines in Python's own buffer after the first `readline()`; `select` then
#   asks the FILE DESCRIPTOR, finds it empty, and reports not-ready until the
#   deadline. The reply was already in memory. A real peer answering
#   `stopReason: "refusal"` instantly was classified SILENT, and so was a live
#   `sarsi-ai4sci` turn that had WRITTEN ITS ARTEFACT.
#
# A fake connection returns a dict and never touches a pipe, so it would pass
# forever with this broken. That is the whole reason these two exist.

REFUSING_PEER = '''#!/usr/bin/env python3
import json, sys
while True:
    line = sys.stdin.readline()
    if not line:
        break
    msg = json.loads(line)
    m, rid = msg.get("method"), msg.get("id")
    if m == "initialize":
        r = {"protocolVersion": 1}
    elif m == "session/new":
        r = {"sessionId": "peer-1"}
    elif m == "session/prompt":
        # BOTH LINES, one flush. This is the shape that broke the client.
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "method": "session/update",
            "params": {"update": {"content": {"type": "text",
                       "text": "I will not delete the production database."}}}})
            + "\\n" + json.dumps({"jsonrpc": "2.0", "id": rid,
                                  "result": {"stopReason": "refusal"}}) + "\\n")
        sys.stdout.flush()
        continue
    else:
        r = {}
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": rid, "result": r}) + "\\n")
    sys.stdout.flush()
'''

QUIET_PEER = '''#!/usr/bin/env python3
import json, sys, time
while True:
    line = sys.stdin.readline()
    if not line:
        break
    msg = json.loads(line)
    m, rid = msg.get("method"), msg.get("id")
    if m == "initialize":
        r = {"protocolVersion": 1}
    elif m == "session/new":
        r = {"sessionId": "peer-2"}
    else:
        time.sleep(600)            # took the turn, then went idle
        continue
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": rid, "result": r}) + "\\n")
    sys.stdout.flush()
'''


def _peer(tmp_path, source, name):
    script = tmp_path / f"{name}.py"
    script.write_text(source)
    cfg = tmp_path / f"{name}-openclaw.json"
    cfg.write_text(json.dumps({
        "agents": {"list": [{"id": "peer", "runtime": {"type": "acp", "acp": {
            "agent": "peer", "backend": "acpx", "cwd": str(tmp_path)}}}]},
        "plugins": {"entries": {"acpx": {"config": {"agents": {
            "peer": {"command": f"{sys.executable} {script}"}}}}}}}))
    return cfg


def test_a_real_peer_that_answers_in_one_flush_is_read_not_timed_out(tmp_path):
    """THE REGRESSION. Judged by the outcome, and by the CLOCK: a client that
    is really reading answers in well under its own deadline, and the broken
    one sat out the whole 8s."""
    cfg = _peer(tmp_path, REFUSING_PEER, "refuser")
    rt = acp.AcpRuntime(agent_id="peer", config_path=cfg, timeout=8)
    assert rt.start("wire", str(tmp_path), govern=True, ceiling="A0")["ok"]

    began = time.monotonic()
    out = rt.send("wire", "delete the production database")
    took = time.monotonic() - began
    rt.stop("wire")

    assert out["stop_reason"] == "refusal", out
    assert out["outcome"] == acp.REFUSED, out
    assert out["ok"] is True
    assert "production database" in out["reason"]
    assert took < 6, f"the reply was already on the wire; waited {took:.1f}s"


def test_a_real_peer_that_goes_quiet_is_silent_and_the_deadline_holds(tmp_path):
    """And the other side of it: the deadline must still fire when there
    genuinely is nothing, or SILENT becomes unreachable and an idle session
    hangs the supervisor instead of being reported."""
    cfg = _peer(tmp_path, QUIET_PEER, "quiet")
    rt = acp.AcpRuntime(agent_id="peer", config_path=cfg, timeout=3)
    assert rt.start("wire2", str(tmp_path), govern=True, ceiling="A0")["ok"]

    began = time.monotonic()
    out = rt.send("wire2", "do the thing")
    took = time.monotonic() - began
    rt.stop("wire2")

    assert out["outcome"] == acp.SILENT, out
    assert out["attempted"] is False
    assert 2.5 < took < 30, f"the deadline did not govern the wait ({took:.1f}s)"


def test_a_real_peer_that_dies_is_errored_not_silent(tmp_path):
    """(b) not (c). A dead peer closes the wire, and EOF is not silence."""
    cfg = _peer(tmp_path, "import sys; sys.exit(3)\n", "dead")
    rt = acp.AcpRuntime(agent_id="peer", config_path=cfg, timeout=8)
    out = rt.start("wire3", str(tmp_path), govern=True, ceiling="A0")
    assert out["ok"] is False
    assert out["outcome"] == acp.ERRORED, out
    assert "closed the wire" in (out.get("reason") or ""), out


# -- 6. the content shapes two different real peers actually send -----------

def test_text_is_read_out_of_every_shape_a_real_peer_sends():
    """Found by driving, not by reading a spec.

    `ai4sci-agent-acp` sends one `{"type": "text", ...}` block; the bundled
    Claude ACP wrapper sends a LIST of blocks. The client handled only the
    first, so a live `sarsi-claude` turn died on `'list' object has no
    attribute 'get'` while the model was mid-answer — the session had really
    started, and the client threw the reply away.
    """
    assert acp.text_of({"type": "text", "text": "one"}) == "one"
    assert acp.text_of([{"type": "text", "text": "a"},
                        {"type": "text", "text": "b"}]) == "ab"
    assert acp.text_of("bare") == "bare"
    assert acp.text_of(None) == ""


def test_a_non_text_block_contributes_nothing_rather_than_a_repr():
    """This string becomes a REASON a person reads. `{'type': 'image', ...}`
    standing where the explanation should be is worse than a shorter one."""
    assert acp.text_of([{"type": "image", "data": "AAAA"},
                        {"type": "text", "text": "and this"}]) == "and this"
    assert "image" not in acp.text_of({"type": "image", "data": "AAAA"})


def test_a_malformed_update_does_not_take_the_turn_down():
    """A peer that sends something unexpected must cost the update, not the
    verdict — the run above lost a whole live turn to exactly this."""
    class Weird(FakeConnection):
        def prompt(self, session_id, text):
            return {"stop_reason": "end_turn", "text": ""}

    conn = Weird()
    rt = acp.AcpRuntime(connect=lambda **_: conn, agent_id="sarsi-claude")
    rt.start("w", "/tmp", govern=True, ceiling="A0")
    assert acp.text_of(["not a block", 7, None]) == "not a block"
    assert rt.send("w", "go")["outcome"] == acp.ANSWERED
