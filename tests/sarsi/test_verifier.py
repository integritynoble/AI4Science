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
