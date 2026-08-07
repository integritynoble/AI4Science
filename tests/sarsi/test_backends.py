"""`sarsi-pwm` and `sarsi-claude` as named, per-task session backends.

A session already runs one of two things: `claude-code` launches Anthropic's
`claude` binary, and every other spec launches `ai4science chat --mode <spec>`.
The mechanism is there; what was missing is the *concept* — a backend the owner
can name, choose at the confirmation, and switch on an existing task.

Two rules the design fixes and this module has to hold:

  * **the backend belongs to the TASK, not the agent.** One worker runs many
    tasks, and "which engine ran this one" is a fact about the task — it is
    recorded with it, and switching it does not reach back and rewrite what an
    earlier task ran on.
  * **switching does not migrate a running session.** It takes effect on the
    next `run`, and says so. Moving a live session between engines mid-plan
    would silently change who wrote what, and the plan record is the one thing
    that must stay attributable.
"""
import pytest

from ai4science.harness.agents.sarsi import backends


# ── the two backends ──────────────────────────────────────────────────

def test_both_backends_exist_and_name_a_real_spec():
    from ai4science.harness.agents import registry as ar
    ar.reload()
    for name in ("sarsi-claude", "sarsi-pwm"):
        spec = backends.spec_for(name)
        assert spec, name
        assert ar.get(spec) is not None, (name, spec)


def test_sarsi_claude_runs_anthropics_binary():
    """This is the one backend that launches a vendor CLI rather than an
    ai4science mode, which is why removing the `claude-code` spec would stop
    sarsi-worker being able to launch anything."""
    assert backends.spec_for("sarsi-claude") == "claude-code"


def test_sarsi_pwm_runs_ai4science():
    """PWM Code — the agent the owner lands in — in a tmux session, so the
    interface they work in and the one a worker's session runs are the same."""
    assert backends.spec_for("sarsi-pwm") != "claude-code"


def test_the_default_is_named_once():
    """Two places that both decide the default will disagree, and the one that
    disagrees quietly is the one that picks the wrong engine."""
    assert backends.DEFAULT in backends.NAMES


def test_an_unknown_backend_is_refused_not_guessed():
    with pytest.raises(backends.NoSuchBackend, match="dogecoin"):
        backends.spec_for("dogecoin")


def test_the_refusal_lists_what_there_is():
    """A refusal that does not say what would satisfy it is a wall."""
    with pytest.raises(backends.NoSuchBackend) as e:
        backends.spec_for("typo")
    assert "sarsi-pwm" in str(e.value) and "sarsi-claude" in str(e.value)


# ── which backend the loop can drive ──────────────────────────────────

def test_drivability_is_asked_of_the_spec_not_assumed_of_the_backend():
    """`DRIVABLE_SPECS` is a claim the loop has been SEEN reading an interface.
    A backend does not become drivable by being added here."""
    from ai4science.harness.agents.sarsi import session as ses
    assert ses.drivable(backends.spec_for("sarsi-claude")) is True


def test_pwm_became_drivable_only_after_a_live_run():
    """This test asserted the OPPOSITE until 2026-08-07, deliberately, so the
    claim could not be made without evidence. The evidence: a real session
    started by sarsi-worker on grace, running

        ai4science chat --mode unified-LLM

    with the loop's own matchers confirming, against that live screen, that it
    saw a gate and recognised it as the folder-trust prompt answered by "1".

    It also makes `jobs` loop-driven — same spec, same TUI. Drivability is a
    property of the interface, not the agent."""
    from ai4science.harness.agents.sarsi import session as ses
    assert ses.drivable(backends.spec_for("sarsi-pwm")) is True
    assert ses.drivable("unified-LLM") is True


# ── naming ────────────────────────────────────────────────────────────

def test_a_backend_reports_what_it_actually_launches():
    """For the confirmation block: an owner choosing an engine should be told
    what will run, not just a label."""
    assert "claude" in backends.describe("sarsi-claude").lower()
    assert "ai4science" in backends.describe("sarsi-pwm").lower()


def test_describing_an_unknown_backend_does_not_raise():
    """This text reaches a confirmation prompt. A raise there would drop the
    REPL the owner is standing in."""
    assert isinstance(backends.describe("nonsense"), str)


# ── the task carries it ───────────────────────────────────────────────

import json
import pytest as _pytest
from ai4science.harness.agents.sarsi import registry as reg, task as tsk, worker as wk


@_pytest.fixture
def config(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path / "s"))
    root = tmp_path / "s"; root.mkdir(parents=True, exist_ok=True)
    p = reg.config_path(root)
    p.write_text(json.dumps(reg.default_config(owner_id="7007143162")))
    c = reg.load(p); c.ensure_dirs()
    return c


def test_a_new_task_records_the_default_backend(config):
    """Recorded at creation, not inferred later. 'Which engine ran this' is a
    fact about the task, and a task that never wrote it down cannot answer."""
    a = config.agents["sarsi-worker"]
    t = tsk.create(config, a, wk.Directive(agent_id=a.id, goal="g"))
    assert t.backend == backends.DEFAULT


def test_a_task_can_be_created_on_the_other_backend(config):
    a = config.agents["sarsi-worker"]
    t = tsk.create(config, a, wk.Directive(agent_id=a.id, goal="g"),
                   backend="sarsi-claude")
    assert t.backend == "sarsi-claude"


def test_an_unknown_backend_is_refused_at_creation(config):
    """Refused before the task exists, rather than at run time when the owner
    has already confirmed and walked away."""
    a = config.agents["sarsi-worker"]
    with _pytest.raises(backends.NoSuchBackend):
        tsk.create(config, a, wk.Directive(agent_id=a.id, goal="g"),
                   backend="nonsense")


def test_the_backend_survives_a_round_trip(config):
    a = config.agents["sarsi-worker"]
    t = tsk.create(config, a, wk.Directive(agent_id=a.id, goal="g"),
                   backend="sarsi-claude")
    again = [x for x in tsk.all_of(config, a) if x.id == t.id][0]
    assert again.backend == "sarsi-claude"


def test_switching_says_it_takes_effect_next_run(config):
    """Switching must not migrate a running session: moving a live session
    between engines mid-plan silently changes who wrote what, and the plan
    record is the one thing that must stay attributable."""
    a = config.agents["sarsi-worker"]
    t = tsk.create(config, a, wk.Directive(agent_id=a.id, goal="g"))
    t.session = {"name": "sarsi-worker-abcd"}
    msg = tsk.set_backend(config, a, t, "sarsi-claude")
    assert t.backend == "sarsi-claude"
    assert "next" in msg.lower() and "sarsi-worker-abcd" in msg


def test_switching_with_no_session_does_not_pretend_there_was_one(config):
    a = config.agents["sarsi-worker"]
    t = tsk.create(config, a, wk.Directive(agent_id=a.id, goal="g"))
    msg = tsk.set_backend(config, a, t, "sarsi-claude")
    assert "next" in msg.lower()


# ── and the session actually starts on it ─────────────────────────────

def test_assign_launches_the_backend_the_task_chose(config, monkeypatch):
    """The point of the whole piece. A backend recorded on the task and then
    ignored at launch would be a setting that looks honoured and is not."""
    from ai4science.harness.agents.sarsi import session as ses
    seen = {}

    class _RT:
        engine = "claude"
        def start(self, name, cwd, *, govern, ceiling, env=None,
                  spec="claude-code", writable=None):
            seen["spec"] = spec
            return {"ok": True, "name": name}
        def send(self, name, text):
            return {"ok": True}

    a = config.agents["sarsi-worker"]
    t = tsk.create(config, a, wk.Directive(agent_id=a.id, goal="g"),
                   backend="sarsi-claude")
    ses.assign(config, a, t, runtime=_RT(), installed=lambda: set())
    assert seen["spec"] == backends.spec_for("sarsi-claude")


def test_and_the_other_one_too(config):
    from ai4science.harness.agents.sarsi import session as ses
    seen = {}

    class _RT:
        engine = "claude"
        def start(self, name, cwd, *, govern, ceiling, env=None,
                  spec="claude-code", writable=None):
            seen["spec"] = spec
            return {"ok": True, "name": name}
        def send(self, name, text):
            return {"ok": True}

    a = config.agents["sarsi-worker"]
    t = tsk.create(config, a, wk.Directive(agent_id=a.id, goal="g"),
                   backend="sarsi-pwm")
    ses.assign(config, a, t, runtime=_RT(), installed=lambda: set())
    assert seen["spec"] == backends.spec_for("sarsi-pwm")


def test_a_task_written_before_backends_existed_still_runs(config):
    """Blank means the default, not a crash. Records predate this field."""
    from ai4science.harness.agents.sarsi import session as ses
    seen = {}

    class _RT:
        engine = "claude"
        def start(self, name, cwd, *, govern, ceiling, env=None,
                  spec="claude-code", writable=None):
            seen["spec"] = spec
            return {"ok": True, "name": name}
        def send(self, name, text):
            return {"ok": True}

    a = config.agents["sarsi-worker"]
    t = tsk.create(config, a, wk.Directive(agent_id=a.id, goal="g"))
    t.backend = ""                       # as an old record would deserialise
    ses.assign(config, a, t, runtime=_RT(), installed=lambda: set())
    assert seen["spec"] == backends.spec_for(backends.DEFAULT)
