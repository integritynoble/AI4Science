"""The independent verifier — the only thing here that may rule.

Its contract is fixed and narrow: **judge only visible evidence; an unproven
claim fails.** Everything else in the system reports.

Three verdicts, not two, and the third is the point:

  * **PASS** — a judge saw the evidence and the criteria were met.
  * **FAIL** — a judge saw the evidence and they were not.
  * **UNVERIFIED** — **no judgment happened at all.**

Collapsing the third into FAIL looks safe (it never passes) and is not: the
session is then told "the verifier says this is not done yet" when nothing
judged it, and asked to address a reason it cannot act on. Pretending to know is
worse than either answer.

What never changes: **UNVERIFIED is not a pass.** Silence is never success.
"""
import pytest

from ai4science.harness.agents.sarsi import verifier as vf


def _fake_model(reply):
    def call(prompt: str) -> str:
        call.prompt = prompt
        return reply
    return call


# ── the verdict it returns ────────────────────────────────────────────

def test_a_clear_pass_is_a_pass():
    v = vf.model_verifier(_fake_model("PASS: export.csv has 1,204 rows"))
    assert v(goal="finish the export", criteria=["1,204 rows"],
             evidence="rows: 1204")["state"] == "PASS"


def test_a_clear_fail_is_a_fail_and_keeps_its_reason():
    v = vf.model_verifier(_fake_model("FAIL: only 3 rows are visible"))
    out = v(goal="g", criteria=["1,204 rows"], evidence="rows: 3")
    assert out["state"] == "FAIL" and "3 rows" in out["why"]


def test_an_unreadable_answer_is_unverified_not_failed():
    """An unparseable verdict is not a verdict — and it is not a judgment that
    the work is wrong either."""
    out = vf.model_verifier(_fake_model("hmm, hard to say"))(
        goal="g", criteria=["x"], evidence="the screen")
    assert out["state"] == "UNVERIFIED"
    assert vf.is_pass(out) is False


def test_a_model_that_raises_is_unverified():
    def boom(prompt):
        raise RuntimeError("no API key")

    out = vf.model_verifier(boom)(goal="g", criteria=["x"], evidence="the screen said done")
    assert out["state"] == "UNVERIFIED" and "no API key" in out["why"]
    assert vf.is_pass(out) is False


def test_no_verifier_available_is_unverified_and_never_a_pass():
    out = vf.unavailable("no model configured")(goal="g", criteria=["x"], evidence="")
    assert out["state"] == "UNVERIFIED"
    assert vf.is_pass(out) is False
    assert "no model configured" in out["why"]


# ── reading the verdict out of a real answer ──────────────────────────

#: Verbatim from a live run. The model narrated before it judged, and the word
#: it narrated with was "PASS/FAIL". The old parser matched PASS at position 0
#: and recorded a task VERIFIED that this answer rejects.
LIVE_FALSE_PASS = (
    "PASS/FAIL judgment on visible evidence only — let me read what's "
    "actually shown.\n\n"
    "FAIL: The visible pane contains no `ls`/`cat`/`grep` output for "
    "report.md — only narration about the harness's capture mechanism and an "
    'in-progress "Running 1 shell command…" spinner; neither the file\'s '
    "existence in the task folder nor the total 111 appears anywhere in the "
    "evidence."
)


def test_a_narrated_answer_is_read_by_its_verdict_line_not_its_first_word():
    """The live bug: `PASS/FAIL` is not a verdict, it is the word "verdict"."""
    out = vf.parse(LIVE_FALSE_PASS)
    assert out["state"] == "FAIL"
    assert "no `ls`" in out["why"]


def test_pass_slash_fail_alone_is_not_a_verdict():
    assert vf.parse("PASS/FAIL: unclear")["state"] == "UNVERIFIED"


def test_a_verdict_word_inside_a_sentence_is_not_a_verdict():
    out = vf.parse("I would PASS this if the file were shown.")
    assert out["state"] == "UNVERIFIED"


def test_two_disagreeing_verdict_lines_are_unreadable():
    """Better to say nothing was decided than to pick one."""
    assert vf.parse("PASS: looks right\nFAIL: on reflection, no")["state"] == "UNVERIFIED"


def test_a_clean_verdict_after_a_preamble_is_found():
    out = vf.parse("Let me check the evidence.\n\nPASS: 1,204 rows are visible")
    assert out["state"] == "PASS" and "1,204 rows" in out["why"]


def test_a_bare_verdict_word_on_its_own_line_still_counts():
    assert vf.parse("FAIL")["state"] == "FAIL"


# ── what it is told ───────────────────────────────────────────────────

def test_the_prompt_carries_every_criterion():
    call = _fake_model("PASS")
    vf.model_verifier(call)(goal="g", criteria=["the queue reads 0", "1,204 rows"],
                            evidence="screen")
    assert "the queue reads 0" in call.prompt and "1,204 rows" in call.prompt


def test_the_prompt_states_that_an_unproven_claim_fails():
    call = _fake_model("PASS")
    vf.model_verifier(call)(goal="g", criteria=["x"], evidence="e")
    assert "unproven" in call.prompt.lower()


def test_with_no_criteria_it_judges_against_the_goal_alone():
    """A stale plan's criteria are withheld; the goal still stands."""
    call = _fake_model("PASS")
    vf.model_verifier(call)(goal="finish the export", criteria=[], evidence="e")
    assert "finish the export" in call.prompt


# ── which judge this machine can actually reach ───────────────────────

def test_the_claude_cli_verifier_parses_its_answer():
    def run(argv, prompt, timeout):
        run.argv = argv
        return 0, "PASS: DONE.md reads exactly that", ""

    out = vf.claude_verifier(run=run)(goal="g", criteria=["c"], evidence="e")
    assert out["state"] == "PASS"
    assert "-p" in run.argv                      # headless, not interactive


def test_a_claude_cli_that_will_not_run_is_unverified():
    """A judge that could not start did not judge — and "not logged in" is not a
    finding about the work."""
    def run(argv, prompt, timeout):
        return 1, "", "not logged in"

    out = vf.claude_verifier(run=run)(goal="g", criteria=["c"], evidence="e")
    assert out["state"] == "UNVERIFIED" and "not logged in" in out["why"]
    assert vf.is_pass(out) is False


def test_default_prefers_a_judge_this_machine_can_reach():
    """An unreachable judge fails everything, which is safe but useless. Prefer
    the engine that is actually installed here."""
    chosen = vf.chosen_engine(which=lambda n: "/usr/bin/claude" if n == "claude" else None)
    assert chosen == "claude"


def test_with_nothing_installed_the_default_is_the_honest_refusal():
    judge = vf.default_verifier(which=lambda n: None, has_api_key=lambda: False)
    out = judge(goal="g", criteria=["c"], evidence="e")
    assert out["state"] == "UNVERIFIED"
    assert vf.is_pass(out) is False


def test_empty_evidence_is_unverified_without_asking_the_model():
    """Nothing visible means nothing was judged — and paying for a model call to
    learn that is waste."""
    call = _fake_model("PASS")
    out = vf.model_verifier(call)(goal="g", criteria=["x"], evidence="   ")
    assert out["state"] == "UNVERIFIED"
    assert not hasattr(call, "prompt")


def test_a_judge_that_says_fail_is_a_real_failure_not_an_unverified():
    """The distinction that matters: a judgment was made, and it was no."""
    out = vf.model_verifier(_fake_model("FAIL: only 3 rows"))(
        goal="g", criteria=["1204 rows"], evidence="rows: 3")
    assert out["state"] == "FAIL"
    assert vf.was_judged(out) is True


def test_an_unverified_result_was_not_judged():
    out = vf.unavailable("nothing installed")(goal="g", criteria=["x"], evidence="e")
    assert vf.was_judged(out) is False


# ── a stale plan is not judged at all ─────────────────────────────────

def test_a_stale_plan_is_refused_rather_than_judged_against_the_goal(
        monkeypatch, tmp_path):
    """The owner drove the session by hand, so the plan no longer describes
    what happened.

    Withholding the criteria and judging against the goal alone silently
    lowers the standard: the verifier then answers PASS about a weaker
    question than the one the owner set, without saying that is what it did.
    Refusing, and saying why, is the only honest move.
    """
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path))
    from ai4science.harness.agents.sarsi import (plan as pl, registry as reg,
                                                 session as ses, task as tsk,
                                                 worker)
    config = reg.parse(reg.default_config(owner_id="1"), root=tmp_path)
    config.ensure_dirs()
    agent = config.agents["work"]
    d = worker.Directive(agent_id=agent.id, goal="finish the export")
    t = tsk.attach_plan(config, agent, tsk.create(config, agent, d), pl.draft(d))
    t.plan_stale = True
    tsk._touch(agent, t, __import__("time").time)

    asked = []

    def judge(**kw):
        asked.append(kw)
        return {"state": "PASS", "why": "looks done to me"}

    out = ses.verify(config, agent, t, verifier=judge, evidence="whatever")
    assert asked == []                              # never even asked
    assert out.verdict["state"] == "UNVERIFIED"   # the record's real key
    assert "stale" in out.verdict["why"].lower()
    assert out.state != tsk.VERIFIED


def test_the_refusal_says_how_to_clear_it(monkeypatch, tmp_path):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path))
    from ai4science.harness.agents.sarsi import (plan as pl, registry as reg,
                                                 session as ses, task as tsk,
                                                 worker)
    config = reg.parse(reg.default_config(owner_id="1"), root=tmp_path)
    config.ensure_dirs()
    agent = config.agents["work"]
    d = worker.Directive(agent_id=agent.id, goal="finish the export")
    t = tsk.attach_plan(config, agent, tsk.create(config, agent, d), pl.draft(d))
    t.plan_stale = True
    tsk._touch(agent, t, __import__("time").time)
    out = ses.verify(config, agent, t,
                     verifier=lambda **kw: {"state": "PASS", "why": "x"})
    assert "/edit" in out.verdict["why"]


def test_a_fresh_plan_is_judged_normally(monkeypatch, tmp_path):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path))
    from ai4science.harness.agents.sarsi import (plan as pl, registry as reg,
                                                 session as ses, task as tsk,
                                                 worker)
    config = reg.parse(reg.default_config(owner_id="1"), root=tmp_path)
    config.ensure_dirs()
    agent = config.agents["work"]
    d = worker.Directive(agent_id=agent.id, goal="finish the export")
    t = tsk.attach_plan(config, agent, tsk.create(config, agent, d), pl.draft(d))
    out = ses.verify(config, agent, t,
                     verifier=lambda **kw: {"state": "PASS", "why": "done"})
    assert out.verdict["state"] == "PASS"


# ── a verdict LINE, not a word that appears in prose ──────────────────

def test_the_declared_verdict_wins_over_the_word_in_its_reasoning():
    """Observed on grace: `the verifier's answer gave more than one verdict:
    ['FAIL', 'PASS']`. Refusing was right — but the ambiguity was invited. A
    reply that OPENS with a proper verdict line has decided; the same words
    inside its own reasoning are prose, not a second judgment."""
    got = vf.parse(
        "FAIL: result.json is absent.\n"
        "For a PASS I would need to see the file listed with a psnr above 15.")
    assert got["state"] == "FAIL"
    assert "absent" in got["why"]


def test_a_reply_that_explains_the_format_is_not_two_verdicts():
    got = vf.parse(
        "PASS: the listing shows result.json with a psnr of 25.41.\n"
        "(Criteria are judged PASS or FAIL on visible evidence only.)")
    assert got["state"] == "PASS"


def test_two_real_verdict_lines_are_still_refused():
    """Genuinely competing judgments must not be resolved by taking the first.
    A model that decides and then reverses has said two things."""
    got = vf.parse("PASS: looks right to me.\nFAIL: on reflection the file is empty.")
    assert got["state"] == "UNVERIFIED"
    assert "more than one" in got["why"]


def test_the_narrated_pass_that_caused_the_false_verdict_still_fails():
    """The original: a task recorded VERIFIED off an answer that said
    `PASS/FAIL judgment on visible evidence only` and then FAILED it."""
    got = vf.parse(
        "PASS/FAIL judgment on visible evidence only, as instructed.\n"
        "FAIL: nothing in the evidence shows the export ran.")
    assert got["state"] == "FAIL"


def test_a_reply_with_no_verdict_line_at_all_is_unverified():
    got = vf.parse("I would need to see the file before I could judge this.")
    assert got["state"] == "UNVERIFIED"


def test_the_contract_asks_for_the_verdict_first_and_nothing_before_it():
    prompt = vf.build_prompt(goal="g", criteria=["c"], evidence="e")
    low = prompt.lower()
    assert "first line" in low
    assert "do not restate" in low or "nothing before" in low


# ── a verdict wearing markdown is still a verdict ─────────────────────

def test_a_bolded_verdict_is_read():
    """Models write `**PASS**: …` constantly. Discarding it as unreadable turns
    a real judgment into UNVERIFIED — a false not-judged, which stalls the loop
    and wastes the work that earned the verdict."""
    assert vf.parse("**PASS**: the listing shows result.json")["state"] == "PASS"


def test_a_bolded_verdict_keeps_its_reason():
    assert "result.json" in vf.parse("**PASS**: the listing shows result.json")["why"]


def test_a_colon_inside_the_emphasis_is_read():
    assert vf.parse("**FAIL:** the folder is empty")["state"] == "FAIL"


def test_a_bulleted_verdict_is_read():
    assert vf.parse("- FAIL: nothing was written")["state"] == "FAIL"


def test_a_numbered_verdict_is_read():
    assert vf.parse("1. PASS: every criterion is met")["state"] == "PASS"


def test_decoration_does_not_make_prose_into_a_verdict():
    """Stripping `*` and `-` must not turn a sentence into a judgment."""
    got = vf.parse("**The criteria are judged PASS or FAIL on evidence.**")
    assert got["state"] == "UNVERIFIED"


def test_decoration_does_not_hide_a_second_verdict():
    got = vf.parse("**PASS**: looks right\n- FAIL: on reflection it is empty")
    assert got["state"] == "UNVERIFIED"
