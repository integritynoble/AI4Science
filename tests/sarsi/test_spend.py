"""`spend` — what a task actually cost.

One task burned about eight minutes of unattended waiting and nothing recorded
it. Both proposals asked for this independently, and the reason is the same:
without it, "is this agent worth running?" is answered from memory.

The numbers are real, not estimated. Claude Code writes a transcript per
working directory, each sarsi session has its own, and the transcript carries
per-turn `usage`. So tokens are **read**, not modelled.

What matters more than the numbers is the shape of the not-knowing:

  * **unknown is not zero.** A transcript that cannot be read gives `None`, and
    the report says so. Printing `0 tokens` for a session that ran for an hour
    is the most confident kind of wrong.
  * **cached input is counted apart from fresh input.** They are both "input"
    and they are not the same cost; adding them makes a cheap session look
    expensive.
  * **PWM is not reported as 0.** These sessions are Claude Code, which this
    system does not charge in PWM — "0 PWM" reads as free, and the truth is
    "not charged here".
"""
import json
import time

import pytest

from ai4science.harness.agents.sarsi import (plan as pl, registry as reg,
                                             session as ses, spend as sp,
                                             task as tsk, worker)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path / "state"))
    return tmp_path


@pytest.fixture
def config(tmp_path):
    c = reg.parse(reg.default_config(owner_id="7007143162"),
                  root=tmp_path / "state")
    c.ensure_dirs()
    return c


@pytest.fixture
def agent(config):
    return config.agents["work"]


class FakeRuntime:
    engine = "claude"

    def start(self, name, cwd, *, govern, ceiling, env=None, spec=None):
        return {"ok": True, "name": name, "pid": 1, "cwd": cwd}

    def send(self, name, text):
        return {"ok": True}

    def set_ceiling(self, name, ceiling):
        return {"ok": True}


def _task(config, agent, goal="finish the export"):
    d = worker.Directive(agent_id=agent.id, goal=goal)
    t = tsk.attach_plan(config, agent, tsk.create(config, agent, d), pl.draft(d))
    return tsk.start(config, agent, t)


def _running(config, agent, goal="finish the export"):
    return ses.assign(config, agent, _task(config, agent, goal),
                      runtime=FakeRuntime())


def _transcript(*turns):
    """A stand-in for Claude Code's per-turn transcript."""
    def read(cwd):
        return list(turns)
    return read


# ── tokens, read rather than modelled ─────────────────────────────────

def test_tokens_come_from_the_transcript(config, agent):
    t = _running(config, agent)
    got = sp.for_task(config, agent, t, usage=_transcript(
        {"input_tokens": 100, "output_tokens": 20},
        {"input_tokens": 50, "output_tokens": 10}))
    assert got.input_tokens == 150
    assert got.output_tokens == 30


def test_cached_input_is_counted_apart_from_fresh_input(config, agent):
    """Both are 'input' and they are not the same cost."""
    t = _running(config, agent)
    got = sp.for_task(config, agent, t, usage=_transcript(
        {"input_tokens": 10, "cache_read_input_tokens": 90_000,
         "cache_creation_input_tokens": 500, "output_tokens": 5}))
    assert got.input_tokens == 10
    assert got.cached_tokens == 90_000
    assert got.cache_write_tokens == 500


def test_a_session_that_never_started_has_no_token_record(config, agent):
    got = sp.for_task(config, agent, _task(config, agent))
    assert got.input_tokens is None
    assert "not started" in got.summary.lower()


# ── unknown is not zero ───────────────────────────────────────────────

def test_an_unreadable_transcript_gives_unknown_not_zero(config, agent):
    """Printing '0 tokens' for a session that ran for an hour is the most
    confident kind of wrong."""
    def broken(cwd):
        raise OSError("no transcript")

    t = _running(config, agent)
    got = sp.for_task(config, agent, t, usage=broken)
    assert got.input_tokens is None and got.output_tokens is None
    assert "not recorded" in got.summary.lower() or "unknown" in got.summary.lower()


def test_a_transcript_with_no_usage_entries_is_also_unknown(config, agent):
    t = _running(config, agent)
    got = sp.for_task(config, agent, t, usage=_transcript())
    assert got.input_tokens is None


# ── time ──────────────────────────────────────────────────────────────

def test_a_running_session_reports_the_time_so_far(config, agent):
    t = _running(config, agent)
    t.session["started_at"] = time.time() - 600
    tsk._touch(agent, t, time.time)
    got = sp.for_task(config, agent, tsk.get(config, agent, t.id),
                      usage=_transcript())
    assert 590 <= got.wall_seconds <= 610
    assert got.still_running is True


def test_a_finished_task_reports_the_time_it_took_not_the_time_since(config, agent):
    t = _running(config, agent)
    t.session["started_at"] = time.time() - 600
    t = tsk.finish(config, agent, t, verdict={"state": "PASS", "why": "done"})
    got = sp.for_task(config, agent, tsk.get(config, agent, t.id),
                      usage=_transcript())
    assert got.still_running is False


def test_a_session_with_no_start_time_says_so_rather_than_guessing(config, agent):
    """An older record has no start stamp. Using the task's creation time would
    report the hours it sat unstarted as time it spent working."""
    t = _running(config, agent)
    t.session.pop("started_at", None)
    tsk._touch(agent, t, time.time)
    got = sp.for_task(config, agent, tsk.get(config, agent, t.id),
                      usage=_transcript())
    assert got.wall_seconds is None


def test_assign_stamps_the_session_with_its_start(config, agent):
    t = _running(config, agent)
    assert t.session.get("started_at")


# ── PWM ───────────────────────────────────────────────────────────────

def test_pwm_is_reported_as_not_charged_here_rather_than_zero(config, agent):
    """'0 PWM' reads as free. These sessions are Claude Code, which this system
    does not charge."""
    t = _running(config, agent)
    got = sp.for_task(config, agent, t, usage=_transcript())
    assert "not charged" in got.summary.lower()
    assert "0 pwm" not in got.summary.lower()


# ── totals ────────────────────────────────────────────────────────────

def test_an_agent_total_sums_what_is_known(config, agent):
    a = _running(config, agent, "job one")
    b = _running(config, agent, "job two")
    total = sp.for_agent(config, agent, usage=_transcript(
        {"input_tokens": 10, "output_tokens": 2}))
    assert total.input_tokens == 20


def test_a_total_says_how_many_it_could_not_measure(config, agent):
    _running(config, agent, "job one")
    _task(config, agent, "job two")            # never started

    total = sp.for_agent(config, agent, usage=_transcript(
        {"input_tokens": 10, "output_tokens": 2}))
    assert total.unmeasured == 1
    assert "1" in total.summary


def test_the_fleet_total_names_each_worker(config):
    work, social = config.agents["work"], config.agents["social"]
    _running(config, work, "job one")
    _running(config, social, "draft it")
    rows = sp.across(config, usage=_transcript({"input_tokens": 5,
                                                "output_tokens": 1}))
    assert {r.agent_id for r in rows} == {"work", "social"}


def test_an_archived_task_still_counts_towards_what_was_spent(config, agent):
    """It is finished, not undone. Dropping it would make the total fall over
    time, which is the one thing a spend figure must never do."""
    t = _running(config, agent)
    tsk.archive(config, agent, t)
    total = sp.for_agent(config, agent, usage=_transcript(
        {"input_tokens": 10, "output_tokens": 2}))
    assert total.input_tokens == 10


# ── the transcript lookup ─────────────────────────────────────────────

def test_the_transcript_is_found_for_a_path_with_dots_and_underscores(
        tmp_path, monkeypatch):
    """Claude Code encodes `/`, `.` AND `_` as `-`. Replacing only `/` misses
    every sarsi session, because their cwd is `~/.sarsi/.../tsk_<hex>` — which
    is how `spend` reported "not recorded" for tasks whose transcripts were
    sitting on disk.
    """
    from ai4science.harness.agents.machine import sessions

    home = tmp_path / "home"
    projects = home / ".claude" / "projects"
    encoded = "-home-grace--sarsi-agents-work-tasks-tsk-676ba83f94"
    (projects / encoded).mkdir(parents=True)
    (projects / encoded / "abc.jsonl").write_text(
        json.dumps({"type": "assistant",
                    "message": {"usage": {"input_tokens": 7,
                                          "output_tokens": 3}}}) + "\n")
    monkeypatch.setenv("HOME", str(home))

    found = sessions._transcript_path("/home/grace/.sarsi/agents/work/tasks/tsk_676ba83f94")
    assert found is not None


def test_spend_reads_that_transcript(tmp_path, monkeypatch):
    from ai4science.harness.agents.sarsi import spend as _sp

    home = tmp_path / "home"
    projects = home / ".claude" / "projects"
    encoded = "-home-grace--sarsi-agents-work-tasks-tsk-676ba83f94"
    (projects / encoded).mkdir(parents=True)
    (projects / encoded / "abc.jsonl").write_text(
        json.dumps({"type": "assistant",
                    "message": {"usage": {"input_tokens": 7,
                                          "output_tokens": 3}}}) + "\n")
    monkeypatch.setenv("HOME", str(home))

    blocks = _sp.usage_of("/home/grace/.sarsi/agents/work/tasks/tsk_676ba83f94")
    assert blocks == [{"input_tokens": 7, "output_tokens": 3}]


# ── the cost survives the session ─────────────────────────────────────

def test_stopping_a_task_keeps_what_it_cost(config, agent):
    """`ses.stop` clears `task.session`, so on the real path — archive, which
    stops first — the cwd went with it and the task became unmeasurable. A
    spend figure that falls when you tidy up is worse than none."""
    t = _running(config, agent)
    cwd = t.session["cwd"]
    t = ses.stop(config, agent, t, runtime=FakeRuntime())
    got = sp.for_task(config, agent, tsk.get(config, agent, t.id),
                      usage=_transcript({"input_tokens": 11, "output_tokens": 4}))
    assert got.input_tokens == 11


def test_archiving_keeps_it_too(config, agent):
    t = _running(config, agent)
    t = ses.stop(config, agent, t, runtime=FakeRuntime(), archive=True)
    got = sp.for_task(config, agent, tsk.get(config, agent, t.id),
                      usage=_transcript({"input_tokens": 11, "output_tokens": 4}))
    assert got.input_tokens == 11


def test_a_task_that_ran_twice_is_read_once_per_folder(config, agent):
    """Stop, resume, run again: two sessions, one task — and one folder, so one
    transcript directory. Reading it per session would double the cost of every
    restarted task."""
    t = _running(config, agent)
    t = ses.stop(config, agent, t, runtime=FakeRuntime())
    t = tsk.resume(config, agent, tsk.get(config, agent, t.id))
    t = ses.assign(config, agent, t, runtime=FakeRuntime())
    seen = []

    def usage(cwd):
        seen.append(cwd)
        return [{"input_tokens": 5, "output_tokens": 1}]

    got = sp.for_task(config, agent, tsk.get(config, agent, t.id), usage=usage)
    assert len(seen) == 1
    assert got.input_tokens == 5


def test_every_transcript_in_the_folder_is_read_not_just_the_newest(tmp_path,
                                                                   monkeypatch):
    """Each `claude` launch writes a NEW jsonl in the same project directory.
    Taking only the newest would drop the cost of every earlier run in that
    folder — which is exactly what a restarted task has."""
    home = tmp_path / "home"
    encoded = "-work-tasks-tsk-abc"
    d = home / ".claude" / "projects" / encoded
    d.mkdir(parents=True)
    (d / "run1.jsonl").write_text(json.dumps(
        {"type": "assistant", "message": {"usage": {"input_tokens": 3,
                                                    "output_tokens": 1}}}) + "\n")
    (d / "run2.jsonl").write_text(json.dumps(
        {"type": "assistant", "message": {"usage": {"input_tokens": 4,
                                                    "output_tokens": 2}}}) + "\n")
    monkeypatch.setenv("HOME", str(home))

    blocks = sp.usage_of("/work/tasks/tsk_abc")
    assert sum(b["input_tokens"] for b in blocks) == 7
