"""Not typing into a session this loop cannot read.

Observed live, running `social` on grace. `social` is marked **attended** — its
spec runs the ai4science TUI, not Claude Code's, and the loop's screen-reading
is tuned to the latter. The table said so before the run started.

The loop started it anyway and **typed the brief into it three times**, because
"attended" was reported and never enforced. The ai4science trust prompt is a
*menu*: `j` and `k` move the selection and Enter chooses. A brief is full of
`j`s and `k`s. The cursor walked down to **"No, exit"**, Enter selected it, and
the session was gone — killed by its own supervisor, which then reported
`briefing — waiting to see the brief land` three times about a session that no
longer existed.

Two rules come out of it:

  * **a loop that cannot read a screen must not type at it.** Blind keystrokes
    at an unknown interface are not a brief; they are input to whatever menu
    happens to be showing, and one of the options is always the worst one.
  * **"the pane is gone" and "the pane is empty" are different answers.** They
    were the same string, so a dead session read as a quiet one and `attention`
    reported nothing waiting about a task whose terminal had died.
"""
import pytest

from ai4science.harness.agents.sarsi import (attention as att, plan as pl,
                                             registry as reg, session as ses,
                                             task as tsk, worker)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def config(tmp_path):
    c = reg.parse(reg.default_config(owner_id="7007143162"), root=tmp_path)
    c.ensure_dirs()
    return c


class FakeRuntime:
    engine = "claude"

    def __init__(self):
        self.sent = []

    def start(self, name, cwd, *, govern, ceiling, env=None, spec=None,
              writable=None):
        return {"ok": True, "name": name, "pid": 1, "cwd": cwd}

    def send(self, name, text):
        self.sent.append(text)
        return {"ok": True}

    def set_ceiling(self, name, ceiling):
        return {"ok": True}


def _running(config, agent, rt):
    d = worker.Directive(agent_id=agent.id, goal="draft the post")
    t = tsk.attach_plan(config, agent, tsk.create(config, agent, d), pl.draft(d))
    t = tsk.start(config, agent, t)
    t.plan_agreed = True
    return ses.assign(config, agent, t, runtime=rt)


class Menu:
    """An interface the loop cannot read — a menu, as ai4science renders one."""

    def __init__(self):
        self.typed = []

    def capture(self, name):
        return (" Quick safety check: is this a folder you created or trust?\n"
                " ❯ Yes, I trust this folder\n   No, exit\n")

    def send(self, name, text):
        self.typed.append(text)

    def key(self, name, key):
        self.typed.append(key)


# ── it does not type at what it cannot read ───────────────────────────

def test_an_attended_session_is_not_typed_into(config):
    """Blind keystrokes at an unknown menu are input to whatever is showing,
    and one of the options is always the worst one."""
    rt = FakeRuntime()
    social = config.agents["social"]
    t = _running(config, social, rt)
    pane = Menu()
    action = ses.deliver_kickoff(config, social, t, runtime=_Typer(pane),
                                 screen=pane.capture(t.session["name"]))
    assert pane.typed == []
    assert action.kickoff_pending                # still owed, not lost


def test_the_loop_says_it_is_attended_rather_than_briefing(config):
    from ai4science.harness.agents.sarsi import operator as op
    rt = FakeRuntime()
    social = config.agents["social"]
    t = _running(config, social, rt)
    pane = Menu()
    action = op.tick(config, social, t, pane=pane)
    assert action.kind == "attended"
    assert pane.typed == []


def test_the_reason_names_the_attach_line(config):
    from ai4science.harness.agents.sarsi import operator as op
    rt = FakeRuntime()
    social = config.agents["social"]
    t = _running(config, social, rt)
    assert "tmux attach" in op.tick(config, social, t, pane=Menu()).detail


def test_a_drivable_session_is_still_briefed(config):
    """`work` runs Claude Code, whose screen this loop does read."""
    from ai4science.harness.agents.sarsi import operator as op
    rt = FakeRuntime()
    work = config.agents["work"]
    t = _running(config, work, rt)

    class Claude:
        def __init__(self):
            self.typed = []

        def capture(self, name):
            return "\n".join(self.typed) + "\n❯ "

        def send(self, name, text):
            self.typed.append(text)

        def key(self, name, key):
            pass

    pane = Claude()
    op.tick(config, work, t, pane=pane)
    assert pane.typed                            # it was briefed


# ── attention says an attended session needs the owner ────────────────

def test_attention_says_an_attended_session_is_waiting_on_you(config):
    rt = FakeRuntime()
    social = config.agents["social"]
    _running(config, social, rt)
    got = att.needs(config, social, pane=Menu(), live=lambda: set())
    kinds = [i.kind for i in got.items]
    assert "attended" in kinds


# ── gone is not empty ─────────────────────────────────────────────────

def test_a_pane_that_is_gone_is_not_read_as_empty(config):
    """They were the same string, so a dead session read as a quiet one."""
    from ai4science.harness.agents.sarsi import operator as op
    pane = op.TmuxPane()
    assert pane.capture("a-session-that-does-not-exist") is None


def test_attention_reports_the_dead_session_it_used_to_miss(config):
    rt = FakeRuntime()
    work = config.agents["work"]
    _running(config, work, rt)

    class Gone:
        def capture(self, name):
            return None                          # tmux has no such session

    kinds = [i.kind for i in att.needs(config, work, pane=Gone(),
                                       live=lambda: set()).items]
    assert "dead-session" in kinds


class _Typer:
    """Adapts a pane to the runtime interface `deliver_kickoff` sends through."""

    def __init__(self, pane):
        self._pane = pane

    def send(self, name, text):
        return self._pane.send(name, text)
