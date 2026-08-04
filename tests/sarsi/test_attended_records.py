"""Measuring the agents whose sessions Claude Code never wrote a transcript for.

Three live runs in a row — `social`, `abraham`, `funding` — ended with the same
two lines:

    blast: no record of what it touched — the session transcript could not be read
    spend: tokens: not recorded

Honest, and useless. Both read Claude Code's transcript, and the four attended
agents run the ai4science TUI, which writes its own records somewhere else. More
than half the fleet was unmeasurable.

Everything needed already existed and was simply not joined up:

  * the harness persists a session per workspace — `index.json` maps a working
    directory to a session id, and each record carries its `tool_calls` with
    names and arguments. That is what `blast` needs;
  * the meter already records every metered call into the LLM ledger with its
    tokens and its cost. What it did not record was **which session** — every
    interactive call was `common-interactive`, so nothing could be attributed
    to a task. That is the one thing added here.

The rule the fallbacks keep: **a record that cannot be read still says so.** An
agent with neither transcript reports *not recorded*, exactly as before. This
widens what can be measured; it never invents a measurement.
"""
import json

import pytest

from ai4science.harness.agents.sarsi import blast, registry as reg, spend as sp


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    return tmp_path


@pytest.fixture
def config(tmp_path):
    c = reg.parse(reg.default_config(owner_id="7007143162"),
                  root=tmp_path / "state")
    c.ensure_dirs()
    return c


def _ai4_session(tmp_path, cwd, *, records, session_id="abc123"):
    """What the ai4science harness writes: one jsonl per session, plus an index
    mapping the workspace to it."""
    d = tmp_path / "home" / ".config" / "ai4science" / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{session_id}.jsonl").write_text(
        "\n".join(json.dumps(r) for r in records) + "\n")
    index = d / "index.json"
    idx = json.loads(index.read_text()) if index.exists() else {}
    idx[str(cwd)] = session_id
    index.write_text(json.dumps(idx))
    return session_id


def _write(path):
    return {"role": "assistant", "content": "",
            "tool_calls": [{"id": "1", "name": "write",
                            "arguments": {"path": path, "content": "x"}}]}


def _bash(command="ls"):
    return {"role": "assistant", "content": "",
            "tool_calls": [{"id": "2", "name": "bash",
                            "arguments": {"cmd": command}}]}


# ── blast reads the harness's own records ─────────────────────────────

def test_the_acts_of_an_attended_session_are_read(tmp_path):
    cwd = tmp_path / "work"
    cwd.mkdir()
    _ai4_session(tmp_path, cwd, records=[_write("outline.md")])
    acts = blast.acts_of(str(cwd))
    assert [a["name"] for a in acts] == ["Write"]


def test_a_relative_path_is_resolved_against_the_workspace(tmp_path):
    """The harness records `path: outline.md`, not an absolute one. Left
    relative it resolves against whatever the reader's cwd happens to be."""
    cwd = tmp_path / "work"
    cwd.mkdir()
    _ai4_session(tmp_path, cwd, records=[_write("outline.md")])
    acts = blast.acts_of(str(cwd))
    assert acts[0]["input"]["file_path"] == str(cwd / "outline.md")


def test_its_shell_calls_are_opaque_here_too(tmp_path):
    cwd = tmp_path / "work"
    cwd.mkdir()
    _ai4_session(tmp_path, cwd, records=[_bash("cp x /tmp/y")])
    assert [a["name"] for a in blast.acts_of(str(cwd))] == ["Bash"]


def test_an_attended_session_can_now_be_checked(config, tmp_path):
    from ai4science.harness.agents.sarsi import plan as pl, task as tsk, worker
    agent = config.agents["funding"]
    d = worker.Directive(agent_id=agent.id, goal="draft it")
    t = tsk.attach_plan(config, agent, tsk.create(config, agent, d), pl.draft(d))
    folder = tsk.dir_of(agent, t.id)
    t.session = {"name": "n", "cwd": str(folder)}
    tsk._touch(agent, t, __import__("time").time)
    _ai4_session(tmp_path, folder, records=[_write("outline.md")])

    got = blast.check(config, agent, t)
    assert got.read is True
    assert got.escaped is False and got.inside


def test_neither_transcript_still_reports_not_a_clean_bill(config, tmp_path):
    from ai4science.harness.agents.sarsi import plan as pl, task as tsk, worker
    agent = config.agents["funding"]
    d = worker.Directive(agent_id=agent.id, goal="draft it")
    t = tsk.attach_plan(config, agent, tsk.create(config, agent, d), pl.draft(d))
    t.session = {"name": "n", "cwd": str(tmp_path / "nowhere")}
    tsk._touch(agent, t, __import__("time").time)
    got = blast.check(config, agent, t)
    assert got.read is False
    assert "not a clean bill" in got.summary


def test_the_step_budget_now_binds_on_an_attended_session_too(config, tmp_path):
    """`budget` counts steps through `blast.acts_of`, so it inherited the same
    blindness and the same fix: a declared step ceiling was unenforceable on
    four of the seven agents, and "unknown is not over" meant they simply ran.
    """
    from ai4science.harness.agents.sarsi import (budget, plan as pl,
                                                 task as tsk, worker)
    agent = config.agents["funding"]
    d = worker.Directive(agent_id=agent.id, goal="draft it")
    t = tsk.attach_plan(config, agent, tsk.create(config, agent, d), pl.draft(d))
    folder = tsk.dir_of(agent, t.id)
    t.max_steps = 2
    t.session = {"name": "n", "cwd": str(folder)}
    tsk._touch(agent, t, __import__("time").time)
    _ai4_session(tmp_path, folder,
                 records=[_write("a.md"), _write("b.md"), _write("c.md")])

    got = budget.check(config, agent, t)
    assert got.steps == 3
    assert got.over is True


# ── spend reads the metered calls, attributed ─────────────────────────

def _metered(tmp_path, session_id, *, i, o):
    from ai4science.llm import ledger
    ledger.record(agent="funding", backend="anthropic", model="m",
                  wallet=None, usage={"input": i, "output": o, "total": i + o},
                  cost={"usd_official": 0.0, "usd_billed": 0.0, "pwm": 0.0},
                  session=session_id)


def test_the_ledger_can_record_which_session_a_call_belongs_to(tmp_path):
    """Without it every interactive call is `common-interactive` and nothing
    can be attributed to a task."""
    from ai4science.llm import ledger
    _metered(tmp_path, "abc123", i=10, o=2)
    assert ledger.load()[-1]["session"] == "abc123"


def test_the_meter_files_its_calls_under_the_running_session(tmp_path,
                                                             monkeypatch):
    """The half that is easy to leave out. A ledger that CAN hold a session id
    and a meter that never passes one reads exactly like the bug it fixes: all
    tests green, and `spend` still blind on the machine."""
    from ai4science.harness.adapters import factory
    from ai4science.llm import ledger

    class _U:
        input, output, total = 11, 4, 15

    factory.make_meter(backend="anthropic", model="m", session="abc123")(_U())
    rows = [r for r in ledger.load() if r.get("session") == "abc123"]
    assert rows and rows[-1]["input_tokens"] == 11


def test_the_repl_hands_the_meter_the_session_it_persists_under(tmp_path):
    """It must be the SAME id `persistence.save` uses, or the ledger is
    attributed to a session no index maps a workspace to."""
    import inspect

    from ai4science.harness import repl

    src = inspect.getsource(repl.run_common_repl)
    meter = src.index("make_meter(")
    assert "session=_sid" in src[meter:meter + 120]
    # and the id must exist by then
    assert src.index("_sid = session_id") < meter


def test_spend_reads_the_metered_calls_of_an_attended_session(tmp_path):
    sid = _ai4_session(tmp_path, tmp_path / "work", records=[_write("a.md")])
    _metered(tmp_path, sid, i=10, o=2)
    _metered(tmp_path, sid, i=5, o=1)
    blocks = sp.usage_of(str(tmp_path / "work"))
    assert sum(b["input_tokens"] for b in blocks) == 15
    assert sum(b["output_tokens"] for b in blocks) == 3


def test_another_sessions_calls_are_not_counted(tmp_path):
    sid = _ai4_session(tmp_path, tmp_path / "work", records=[_write("a.md")])
    _metered(tmp_path, sid, i=10, o=2)
    _metered(tmp_path, "someone-else", i=999, o=999)
    blocks = sp.usage_of(str(tmp_path / "work"))
    assert sum(b["input_tokens"] for b in blocks) == 10


# ── and the PWM line has to stop lying ────────────────────────────────

def test_an_attended_sessions_pwm_is_reported_not_denied(config, tmp_path):
    """`spend` ends every report with "PWM: not charged here (Claude Code
    sessions)". True of a claude-code session, and flatly false of the four
    attended ones — their calls go through the meter, which prices them. Fixing
    the token blindness without this would just move the confident wrong one
    line down."""
    from ai4science.harness.agents.sarsi import plan as pl, task as tsk, worker
    from ai4science.llm import ledger

    agent = config.agents["funding"]
    d = worker.Directive(agent_id=agent.id, goal="draft it")
    t = tsk.attach_plan(config, agent, tsk.create(config, agent, d), pl.draft(d))
    folder = tsk.dir_of(agent, t.id)
    t.session = {"name": "n", "cwd": str(folder)}
    tsk._touch(agent, t, __import__("time").time)
    sid = _ai4_session(tmp_path, folder, records=[_write("a.md")])
    ledger.record(agent="funding", backend="anthropic", model="m", wallet=None,
                  usage={"input": 10, "output": 2, "total": 12},
                  cost={"usd_official": 0.0, "usd_billed": 0.0, "pwm": 0.25},
                  session=sid)

    got = sp.for_task(config, agent, t)
    assert got.pwm == pytest.approx(0.25)
    assert "not charged here" not in got.summary
    assert "0.25" in got.summary


def test_a_claude_code_session_still_says_it_is_not_metered(config, tmp_path):
    """Unchanged where it was true — and never `0 PWM`, which reads as free."""
    got = sp.Spend(input_tokens=5, output_tokens=1)
    assert "PWM: not charged here" in got.summary


def test_a_workspace_with_no_session_is_still_unmeasured(tmp_path):
    """Widened, never invented."""
    with pytest.raises(Exception):
        sp.usage_of(str(tmp_path / "nowhere"))


def test_a_claude_code_transcript_still_wins_when_there_is_one(tmp_path):
    """The fallback is a fallback. A claude-code session keeps reading the
    record that has its cache figures, which the harness ledger has not."""
    cwd = tmp_path / "cc"
    cwd.mkdir()
    d = tmp_path / "home" / ".claude" / "projects" / str(cwd).replace("/", "-").replace(".", "-").replace("_", "-")
    d.mkdir(parents=True)
    (d / "s.jsonl").write_text(json.dumps(
        {"type": "assistant",
         "message": {"usage": {"input_tokens": 7, "output_tokens": 3,
                               "cache_read_input_tokens": 900}}}) + "\n")
    blocks = sp.usage_of(str(cwd))
    assert sum(b.get("cache_read_input_tokens", 0) for b in blocks) == 900
