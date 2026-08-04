"""What an attended session is waiting for, not merely that it is waiting.

`attention` told the owner:

    [attended] social/tsk_… — social runs the 'social' interface, which the
    supervision loop cannot read — it needs you
    → tmux attach -t social-976c

True, and it made the owner attach to find out what for. During the live run
that session sat on a folder-trust menu, then on `Do you want to proceed?` for a
command reaching into another agent's task folders, and `attention` said the
same sentence to both.

The confusion worth naming: **not driving a screen is not the same as not
reading one.** `tmux capture-pane` is read-only. What the loop cannot safely do
is *type* — blind keystrokes at an unknown menu are how a session got killed —
and nothing about that argues for keeping the owner in the dark about a pane
that can be read perfectly well.

So the attended item carries the screen. The care goes into not over-claiming:

  * **it shows, it does not interpret.** The lines are labelled as what is on
    the screen, not as "it is asking X". Gate detection is tuned to Claude
    Code's TUI, and this is by definition not that — a confident label on an
    interface nobody parsed is the same mistake as driving it.
  * **"it looks like a choice" is hedged, and only on a shape.** A numbered
    option block is worth pointing at; it is not worth asserting what the
    options mean.
  * **a pane that will not read says so.** Unknown is not "nothing is waiting":
    an attended session whose terminal is gone is a different fact, and a more
    urgent one, than one sitting quietly at its prompt.
  * **it reads and never writes.** The whole reason this is safe.
"""
import time

import pytest

from ai4science.harness.agents.sarsi import (attention as att, plan as pl,
                                             registry as reg, task as tsk,
                                             worker)


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
def attended(config):
    agent = config.agents["social"]
    from ai4science.harness.agents.sarsi import session as ses
    assert not ses.drivable(agent.spec)
    return agent


class Pane:
    """Reads. Records any attempt to do anything else."""

    def __init__(self, screen):
        self.screen = screen
        self.captured = []
        self.sent = []

    def capture(self, name):
        self.captured.append(name)
        return self.screen

    def send(self, name, text):        # must never be called from here
        self.sent.append((name, text))
        return {"ok": True}


def _task(config, agent, *, name="social-976c"):
    d = worker.Directive(agent_id=agent.id, goal="draft three posts")
    t = tsk.attach_plan(config, agent, tsk.create(config, agent, d), pl.draft(d))
    t = tsk.start(config, agent, t)
    t.session = {"name": name, "cwd": str(tsk.dir_of(agent, t.id))}
    return tsk._touch(agent, t, time.time)


GATE = """\
⏺ bash
  $ grep -rl "registry" /home/grace/.sarsi2/agents/
Do you want to proceed?
  1. Yes
  2. Yes, and don't ask again for bash this session
  3. No, and tell the agent what to do differently (esc)
Type a number (1-3) and press Enter ❯
"""

IDLE = """\
 ai4science · social · claude-opus-4-8 · ~/.sarsi/agents/social/tasks/tsk_212d
────────────────────────────────────────────────────────────────────────────
❯
────────────────────────────────────────────────────────────────────────────
"""


def _attended(config, agent, screen, live=("social-976c",)):
    t = _task(config, agent)
    pane = Pane(screen)
    items = att.needs(config, agent, pane=pane, live=list(live)).items
    return t, pane, [i for i in items if i.kind == "attended"]


# ── it reads ──────────────────────────────────────────────────────────

def test_the_attended_item_carries_what_is_on_the_screen(config, attended):
    """The whole point: the owner learns WHAT it is waiting for."""
    _, _, items = _attended(config, attended, GATE)
    assert items and "Do you want to proceed?" in items[0].detail


def test_it_reads_the_pane_rather_than_guessing(config, attended):
    _, pane, _ = _attended(config, attended, GATE)
    assert pane.captured == ["social-976c"]


def test_it_never_types(config, attended):
    """Reading is safe; typing is what killed a session. The distinction is
    the entire basis for doing this at all."""
    _, pane, _ = _attended(config, attended, GATE)
    assert pane.sent == []


def test_it_still_says_which_interface_and_how_to_reach_it(config, attended):
    _, _, items = _attended(config, attended, GATE)
    assert attended.spec in items[0].detail
    assert items[0].action == "tmux attach -t social-976c"


# ── it does not over-claim ────────────────────────────────────────────

def test_it_labels_the_lines_as_a_screen_not_as_a_question(config, attended):
    """Gate detection is tuned to Claude Code's TUI and this is by definition
    not that. A confident label on an interface nobody parsed is the same
    mistake as driving it."""
    _, _, items = _attended(config, attended, GATE)
    said = items[0].detail.lower()
    assert "on its screen" in said or "showing" in said
    assert "it is asking" not in said


def test_a_numbered_choice_is_pointed_at_but_hedged(config, attended):
    _, _, items = _attended(config, attended, GATE)
    said = items[0].detail.lower()
    assert "looks like" in said and "choice" in said


def test_an_idle_screen_is_not_called_a_choice(config, attended):
    _, _, items = _attended(config, attended, IDLE)
    assert "looks like" not in items[0].detail.lower()


def test_the_screen_is_bounded(config, attended):
    """A pane is a screenful; an attention line is a line. Everything a session
    ever printed does not belong in "what is waiting on you"."""
    _, _, items = _attended(config, attended, "\n".join(
        f"line {i}" for i in range(200)))
    assert len(items[0].detail) < 700


# ── unknown is not nothing ────────────────────────────────────────────

def test_a_pane_that_will_not_read_says_so(config, attended):
    """Distinct from a quiet session — and more urgent."""
    _, _, items = _attended(config, attended, None)
    assert items and "could not be read" in items[0].detail


def test_it_does_not_claim_a_screen_it_did_not_get(config, attended):
    _, _, items = _attended(config, attended, None)
    assert "looks like" not in items[0].detail.lower()


def test_with_no_pane_at_all_it_reports_as_before(config, attended):
    """`needs` is called without a pane in plenty of places; that must keep
    working rather than becoming an error or a silence."""
    _task(config, attended)
    items = [i for i in att.needs(config, attended,
                                  live=["social-976c"]).items
             if i.kind == "attended"]
    assert items and "needs you" in items[0].detail


# ── and it is still the same obligation ───────────────────────────────

def test_a_drivable_agent_gets_no_attended_item(config):
    """This is about the interfaces the loop cannot read, and nothing else."""
    agent = config.agents["work"]
    t = _task(config, agent, name="work-abcd")
    items = att.needs(config, agent, pane=Pane(GATE),
                      live=["work-abcd"]).items
    assert [i for i in items if i.kind == "attended"] == []
