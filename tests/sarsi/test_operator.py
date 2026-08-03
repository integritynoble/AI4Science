"""`AN` and `SP` — the two nodes between "a session starts" and "a session runs".

Both were found by the first live run, which had to be nursed by hand: Claude
Code's first-run folder-trust prompt swallowed the kickoff, and the kickoff then
sat typed-but-unsubmitted at the `❯`.

The panes below are copied verbatim from that run.

Two rules shape everything here:

  * **`SP` submits verbatim.** No node anywhere rewrites a stranded prompt — the
    composer writes a *new* instruction, it never edits one already typed.
  * **`AN` answers only gates it recognises.** An allowlist, not a denylist: a
    guessed Yes on an unrecognised gate is the one mistake this loop could make
    that nobody would see until afterwards.
"""
import pytest

from ai4science.harness.agents.sarsi import (ledger, operator as op, plan as pl,
                                             registry as reg, task as tsk, worker)

# ── real panes from the live run ──────────────────────────────────────

TRUST_PANE = """\
 Quick safety check: Is this a project you created or one you trust? (Like your own
 code, a well-known open source project, or work from your team). If not, take a moment
 to review what's in this folder first.

 Claude Code'll be able to read, edit, and execute files here.

 ❯ 1. Yes, I trust this folder
   2. No, exit

 Enter to confirm · Esc to cancel
"""

STRANDED_PANE = """\
                                                                  ctrl+g to edit in Vim
────────────────────────────────────────────────────────────────────────────────────────
❯ Goal: create a file DONE.md in this folder whose first line is exactly: sarsi
  end-to-end works
  Your plan is plan0.md in this folder. Work its earliest incomplete phase.
────────────────────────────────────────────────────────────────────────────────────────
  ⏸ manual mode on
"""

BUSY_PANE = """\
✻ Perusing… (9s · ↓ 257 tokens)
  tmux detected · scroll with PgUp/PgDn
────────────────────────────────────────────────────────────────────────────────────────
❯
────────────────────────────────────────────────────────────────────────────────────────
  ⏸ manual mode on · esc to interrupt · ← 1 agent
"""

IDLE_PANE = """\
  Done. DONE.md written.
────────────────────────────────────────────────────────────────────────────────────────
❯
────────────────────────────────────────────────────────────────────────────────────────
"""

UNKNOWN_GATE_PANE = """\
 Claude wants to run: curl -sL https://example.com/install.sh | sudo bash

 ❯ 1. Yes
   2. Yes, and don't ask again for bash commands
   3. No, and tell Claude what to do differently
"""


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
    return config.agents["work"]


class FakePane:
    def __init__(self, text=""):
        self.text = text
        self.sent = []
        self.keys = []

    def capture(self, name):
        return self.text

    def send(self, name, text):
        self.sent.append(text)
        return {"ok": True}

    def key(self, name, key):
        self.keys.append(key)
        return {"ok": True}


def _task(config, agent, *, session=True, paused=False):
    d = worker.Directive(agent_id=agent.id, goal="write DONE.md")
    p = pl.Plan(goal="write DONE.md",
                phases=[pl.Phase(title="do it", verified_when="DONE.md exists")])
    t = tsk.attach_plan(config, agent, tsk.create(config, agent, d), p)
    t = tsk.start(config, agent, t)
    if session:
        t.session = {"name": "work-abcd", "engine": "claude", "ceiling": "A1"}
    t.steering_paused = paused
    return t


# ── AN: answering a gate it recognises ────────────────────────────────

def test_the_folder_trust_prompt_is_answered(config, agent):
    pane = FakePane(TRUST_PANE)
    action = op.tick(config, agent, _task(config, agent), pane=pane)
    assert action.kind == "answered"
    assert pane.sent == ["1"]                  # the plain, per-call Yes


def test_it_never_presses_the_and_stop_asking_option(config, agent):
    """A per-call decision can only justify a per-call answer; the wider option
    silently converts one authorisation into a standing one."""
    pane = FakePane(TRUST_PANE)
    op.tick(config, agent, _task(config, agent), pane=pane)
    assert all("2" not in s for s in pane.sent)


def test_an_unrecognised_gate_is_left_for_the_owner(config, agent):
    """An allowlist, not a denylist. A guessed Yes here is the one mistake
    nobody would see until afterwards."""
    pane = FakePane(UNKNOWN_GATE_PANE)
    action = op.tick(config, agent, _task(config, agent), pane=pane)
    assert action.kind == "abstained"
    assert pane.sent == []


def test_an_unrecognised_gate_is_recorded_so_the_owner_learns_of_it(config, agent):
    op.tick(config, agent, _task(config, agent), pane=FakePane(UNKNOWN_GATE_PANE))
    assert ledger.count(config, "reports", state="gate") == 1


def test_answering_is_recorded(config, agent):
    op.tick(config, agent, _task(config, agent), pane=FakePane(TRUST_PANE))
    assert ledger.count(config, "reports", state="answered") == 1


# ── SP: submitting a stranded prompt, verbatim ────────────────────────

def test_a_stranded_prompt_is_submitted(config, agent):
    pane = FakePane(STRANDED_PANE)
    action = op.tick(config, agent, _task(config, agent), pane=pane)
    assert action.kind == "submitted"
    assert pane.keys == ["Enter"]


def test_a_prompt_separated_by_a_non_breaking_space_is_still_stranded(config, agent):
    """Claude Code's TUI puts U+00A0 after the ❯, not a plain space. The first
    operator run reported `idle` at a screen that was visibly stuck on exactly
    this."""
    pane = FakePane("❯\xa0Goal: create a file PROOF.md in this folder\n")
    assert op.tick(config, agent, _task(config, agent), pane=pane).kind == "submitted"


def test_a_stranded_prompt_is_never_rewritten(config, agent):
    """No node anywhere rewrites one. The composer writes a NEW instruction; it
    never edits one already typed."""
    pane = FakePane(STRANDED_PANE)
    op.tick(config, agent, _task(config, agent), pane=pane)
    assert pane.sent == []                     # nothing retyped, only Enter


def test_a_gate_preempts_a_stranded_prompt(config, agent):
    """The trust prompt is on screen *because* the kickoff could not run."""
    pane = FakePane(TRUST_PANE + STRANDED_PANE)
    assert op.tick(config, agent, _task(config, agent), pane=pane).kind == "answered"


# ── when it must do nothing ───────────────────────────────────────────

def test_a_busy_session_is_left_alone(config, agent):
    """A live spinner means queued input is normal, not stuck."""
    pane = FakePane(BUSY_PANE)
    action = op.tick(config, agent, _task(config, agent), pane=pane)
    assert action.kind == "busy" and pane.keys == [] and pane.sent == []


def test_an_empty_prompt_is_not_a_stranded_one(config, agent):
    action = op.tick(config, agent, _task(config, agent), pane=FakePane(IDLE_PANE))
    assert action.kind == "idle"


def test_it_does_not_touch_a_session_the_owner_is_driving(config, agent):
    """Interact pauses the worker; the operator is the worker."""
    pane = FakePane(STRANDED_PANE)
    action = op.tick(config, agent, _task(config, agent, paused=True), pane=pane)
    assert action.kind == "paused" and pane.keys == []


def test_a_task_with_no_session_is_nothing_to_operate(config, agent):
    action = op.tick(config, agent, _task(config, agent, session=False),
                     pane=FakePane(STRANDED_PANE))
    assert action.kind == "no-session"


def test_a_verified_task_is_left_alone(config, agent):
    t = _task(config, agent)
    t.state = tsk.VERIFIED
    assert op.tick(config, agent, t, pane=FakePane(STRANDED_PANE)).kind == "done"


# ── V first, then everything else ─────────────────────────────────────

def test_verification_runs_before_submitting_a_stranded_prompt(config, agent):
    """The position is load-bearing. In the console a session that kept
    receiving typed prompts consumed every pass at the submit step, so
    verification starved for 23 consecutive passes."""
    order = []

    def verifier(**kw):
        order.append("verified")
        return {"state": "FAIL", "why": "not yet"}

    pane = FakePane(STRANDED_PANE)
    original = pane.key

    def key(name, k):
        order.append("submitted")
        return original(name, k)

    pane.key = key
    op.tick(config, agent, _task(config, agent), pane=pane, verifier=verifier)
    assert order == ["verified", "submitted"]


def test_a_pass_ends_the_task_and_steers_nothing_further(config, agent):
    pane = FakePane(STRANDED_PANE)
    t = _task(config, agent)
    action = op.tick(config, agent, t, pane=pane,
                     verifier=lambda **kw: {"state": "PASS"})
    assert action.kind == "verified"
    assert pane.keys == [] and pane.sent == []


def test_without_a_verifier_it_does_not_claim_anything(config, agent):
    """No verifier supplied is not a PASS; it just does not verify this pass."""
    action = op.tick(config, agent, _task(config, agent), pane=FakePane(IDLE_PANE))
    assert action.kind != "verified"


# ── S: it steers when there is nothing else to do ─────────────────────

def test_an_idle_session_is_steered(config, agent):
    pane = FakePane(IDLE_PANE)
    action = op.tick(config, agent, _task(config, agent), pane=pane,
                     model=lambda prompt: "run the drain script")
    assert action.kind == "steered"
    assert pane.sent == ["run the drain script"]


def test_a_busy_session_is_never_steered(config, agent):
    pane = FakePane(BUSY_PANE)
    op.tick(config, agent, _task(config, agent), pane=pane,
            model=lambda prompt: "do something")
    assert pane.sent == []


def test_a_stranded_prompt_preempts_steering(config, agent):
    """Submitting what is already typed beats writing something new over it."""
    pane = FakePane(STRANDED_PANE)
    action = op.tick(config, agent, _task(config, agent), pane=pane,
                     model=lambda prompt: "something else entirely")
    assert action.kind == "submitted" and pane.sent == []


def test_with_no_model_an_idle_session_is_just_idle(config, agent):
    action = op.tick(config, agent, _task(config, agent), pane=FakePane(IDLE_PANE))
    assert action.kind == "idle"


# ── the loop ──────────────────────────────────────────────────────────

def test_the_loop_gets_a_stuck_session_moving(config, agent):
    """The live run, replayed: trust gate, then the stranded kickoff."""
    pane = FakePane(TRUST_PANE)
    t = _task(config, agent)

    def advance():
        pane.text = STRANDED_PANE if pane.sent else TRUST_PANE

    actions = []
    for _ in range(2):
        actions.append(op.tick(config, agent, t, pane=pane).kind)
        advance()
    assert actions == ["answered", "submitted"]
