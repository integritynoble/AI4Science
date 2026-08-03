"""The independent verifier — the only thing here that may rule.

Its contract is fixed and narrow: **judge only visible evidence; an unproven
claim fails.** Everything else in the system reports.

The rule with the sharpest edge is the one about absence: when no verifier can
be reached, the answer is FAIL, never PASS. Silence is never success.
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


def test_an_unreadable_answer_fails_rather_than_passing():
    """An unparseable verdict is not a verdict. Defaulting to PASS would let a
    confused model finish a task."""
    out = vf.model_verifier(_fake_model("hmm, hard to say"))(
        goal="g", criteria=["x"], evidence="")
    assert out["state"] == "FAIL"


def test_a_model_that_raises_fails_rather_than_passing():
    def boom(prompt):
        raise RuntimeError("no API key")

    out = vf.model_verifier(boom)(goal="g", criteria=["x"], evidence="the screen said done")
    assert out["state"] == "FAIL" and "no API key" in out["why"]


def test_no_verifier_available_is_a_fail_not_a_pass():
    """Silence is never success."""
    out = vf.unavailable("no model configured")(goal="g", criteria=["x"], evidence="")
    assert out["state"] == "FAIL"
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


def test_empty_evidence_fails_without_asking_the_model():
    """Nothing visible cannot prove anything, and paying for a model call to
    learn that is waste."""
    call = _fake_model("PASS")
    out = vf.model_verifier(call)(goal="g", criteria=["x"], evidence="   ")
    assert out["state"] == "FAIL"
    assert not hasattr(call, "prompt")
