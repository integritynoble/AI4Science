"""Supervising a session that has no screen.

The `do → run → supervise` path stalls on the ACP transport, and the stall is
two problems that separate cleanly:

  * the gateway session starts, stays alive and never returns a plan — outside
    this repo;
  * **`supervise` cannot tell that from work in progress** — squarely inside it,
    and the half that makes the stall pathological rather than merely slow.

Measured on the first live run: the `openclaw` process was genuinely ours, still
alive 85 minutes later, task still `planning`, reports ledger empty, workspace
holding only `.claude` and `.git`. Six supervision passes printed `planning`
six times.

The cause is that `supervise_cmd` hands `operator.run` an `op.TmuxPane()`
unconditionally, and an ACP session has no tmux pane. `TmuxPane.capture`
correctly returns `None`, `tick` coerces it to `""`, and every screen-based
branch then reasons about a blank terminal: no gate, not busy, nothing
stranded — so the pass falls through having learned nothing and reports the
task's own state back at the owner.

What an ACP session *does* expose is the gateway's session store, keyed by the
`openclaw_id` the session record already carries.
"""
import json
import time

import pytest

from ai4science.harness.agents.sarsi import (operator as op, plan as pl,
                                             registry as reg, session as ses,
                                             task as tsk, worker as wk)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def config(tmp_path):
    c = reg.parse(reg.default_config(owner_id="7007143162"), root=tmp_path)
    c.ensure_dirs()
    return c


@pytest.fixture
def agent(config):
    return config.agents["sarsi-worker"]


class NoPane:
    """The real behaviour: there is no tmux pane, so `capture` says None.

    `send` raises rather than no-opping, because a loop that types at a session
    with no terminal is typing somewhere, and stopping that is half the fix.
    """

    def __init__(self):
        self.sent = []

    def capture(self, name):
        return None

    def capture_styled(self, name):
        return None

    def send(self, name, text):
        raise AssertionError(f"typed {text!r} at a session with no pane")


def _acp_task(config, agent, *, state=tsk.PLANNING, artifacts=None):
    t = tsk.create(config, agent, wk.Directive(agent_id=agent.id, goal="do it"))
    p = pl.Plan(goal="do it",
                phases=[pl.Phase(title="p", verified_when="out.txt exists")])
    (tsk.dir_of(agent, t.id) / "plan0.md").write_text(p.render())
    t = tsk.attach_plan(config, agent, t, p)
    t.plan_owner_edited = True
    t.session = {"name": "sarsi-worker-abcd", "transport": "acp",
                 "openclaw_id": "sess_k1", "ceiling": "A2", "engine": "claude"}
    t.state = state
    work = ses.work_dir_for(agent, t)
    work.mkdir(parents=True, exist_ok=True)
    (work / ".claude").mkdir(exist_ok=True)
    for name, body in (artifacts or {}).items():
        (work / name).write_text(body)
    tsk._save(agent, t)
    return t


def _store(home, *, status, started_ms=None, ended_ms=None, engine="claude"):
    d = home / ".openclaw" / "agents" / engine / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    entry = {"status": status, "startedAt": started_ms or int(time.time() * 1000)}
    if ended_ms:
        entry["endedAt"] = ended_ms
    (d / "sessions.json").write_text(json.dumps({"sess_k1": entry}))
    return d / "sessions.json"


# ── the state is readable, and it is read ──────────────────────────────────

def test_an_acp_session_reports_the_state_the_gateway_recorded(config, agent, tmp_path):
    t = _acp_task(config, agent)
    _store(tmp_path, status="running")

    st = ses.acp_status(t, home=tmp_path)

    assert st and st["status"] == "running"


def test_a_session_the_store_does_not_know_is_unknown_not_absent(config, agent, tmp_path):
    """Absence of evidence is not evidence of absence — the rule the store's own
    lookup already states. No store, or no entry, must not read as 'ended'."""
    t = _acp_task(config, agent)

    assert ses.acp_status(t, home=tmp_path) is None


# ── the loop no longer types at a terminal that is not there ───────────────

def test_supervising_an_acp_session_never_types_at_a_missing_pane(config, agent, tmp_path):
    """`NoPane.send` raises. Before this the pass reached a typing branch with
    an empty screen and sent keystrokes into nothing."""
    t = _acp_task(config, agent)
    _store(tmp_path, status="running")

    op.tick(config, agent, t, pane=NoPane(), acts=[], home=tmp_path)


# ── and it says what is actually happening ─────────────────────────────────

def test_a_live_session_that_has_produced_nothing_is_named_as_such(config, agent, tmp_path):
    """The whole point. Six passes printed `planning` six times while the
    session sat there; a pass has to tell 'working' from 'silent'."""
    t = _acp_task(config, agent)
    _store(tmp_path, status="running",
           started_ms=int((time.time() - 3600) * 1000))

    action = op.tick(config, agent, t, pane=NoPane(), acts=[], home=tmp_path)

    assert action.kind == "acp-silent", action
    assert "produced nothing" in action.detail


def test_a_session_that_has_written_something_reads_as_working(config, agent, tmp_path):
    t = _acp_task(config, agent, artifacts={"draft.md": "progress\n"})
    _store(tmp_path, status="running",
           started_ms=int((time.time() - 3600) * 1000))

    action = op.tick(config, agent, t, pane=NoPane(), acts=[], home=tmp_path)

    assert action.kind == "acp-working", action


def test_dotfiles_the_session_did_not_author_are_not_progress(config, agent, tmp_path):
    """`.claude` and `.git` appear because the session opened, not because it
    did anything. Counting them as output is what would let a stalled run read
    as a working one."""
    t = _acp_task(config, agent)
    (ses.work_dir_for(agent, t) / ".git").mkdir(exist_ok=True)
    _store(tmp_path, status="running",
           started_ms=int((time.time() - 3600) * 1000))

    assert op.tick(config, agent, t, pane=NoPane(), acts=[],
                   home=tmp_path).kind == "acp-silent"


def test_a_session_that_ended_with_nothing_to_show_is_a_finding(config, agent, tmp_path):
    """An ended session and an empty workspace is not 'still planning'. It is
    the run having failed, and saying so is the difference between a loop that
    hands control back and one that waits forever."""
    t = _acp_task(config, agent)
    now_ms = int(time.time() * 1000)
    _store(tmp_path, status="ended", started_ms=now_ms - 600_000, ended_ms=now_ms)

    action = op.tick(config, agent, t, pane=NoPane(), acts=[], home=tmp_path)

    assert action.kind == "acp-ended-empty", action
    assert "ended" in action.detail


def test_a_young_session_is_given_room_before_it_is_called_silent(config, agent, tmp_path):
    """A session that started ten seconds ago has not stalled, it has started.
    Calling it silent immediately would replace one useless report with
    another."""
    t = _acp_task(config, agent)
    _store(tmp_path, status="running", started_ms=int((time.time() - 5) * 1000))

    assert op.tick(config, agent, t, pane=NoPane(), acts=[],
                   home=tmp_path).kind == "acp-starting"


def test_verification_still_runs_over_acp(config, agent, tmp_path):
    """Verification reads the WORKSPACE, not the screen, so it is the one
    screen-era branch that works unchanged over a transport with no screen —
    and it must keep working, or the ACP path could never finish a task."""
    t = _acp_task(config, agent, state=tsk.RUNNING,
                  artifacts={"out.txt": "done\n"})
    _store(tmp_path, status="running")

    action = op.tick(config, agent, t, pane=NoPane(), acts=[],
                     verifier=lambda **kw: {"state": "FAIL", "why": "stub"},
                     engine="stub", home=tmp_path)

    assert action.kind == "verified", action


def test_a_tmux_task_is_untouched_by_any_of_this(config, agent, tmp_path):
    """The branch is on the TRANSPORT. A tmux session still reads its pane, and
    a change that quietly rerouted it would trade one broken path for another."""
    t = _acp_task(config, agent)
    t.session = dict(t.session, transport="tmux", openclaw_id=None)
    tsk._save(agent, t)

    seen = {}

    class Pane(NoPane):
        def capture(self, name):
            seen["read"] = name
            return "a terminal with words on it"
        def send(self, name, text):
            seen["sent"] = text

    op.tick(config, agent, t, pane=Pane(), acts=[], home=tmp_path)

    assert seen.get("read") == "sarsi-worker-abcd"
