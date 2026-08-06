"""Two ways a measured number lost the thing that made it true.

Both were found on the same live run: the computational-imaging agent compared
two CASSI forward operators, got the right answer, and the right answer did not
survive being reported.

  1. **The recap asserted a result the answer had qualified.** The report said
     the difference is `1.047e-07` as the operators actually ship, and `0.0`
     *only when (b) is recomputed in float64 without its output cast*. The
     one-line recap kept the `0.0` and dropped the condition — so the sentence
     most people read said the two operators are bit-identical, and they are
     not. The recap is a separate cheap model call given the last 800 characters
     of the answer; it was asked to say what was FOUND, which is an invitation
     to state a result without the clause that bounds it.

  2. **A criterion claimed a measurement and named nowhere to find it.** The
     verifier refused, correctly: the task folder held a report and no run — no
     script, no captured output — so the numbers were *"unverified assertions
     rather than demonstrated measurements"*, and it closed with the line worth
     keeping: **coherence is not evidence of a run.** That refusal is right and
     it arrives late. A criterion that asks for a measured number should have to
     say where the number will be, at plan time, when it costs one edit.
"""
import pytest

from ai4science.harness import recap
from ai4science.harness.agents.sarsi import plan as pl


# ── 1. a recap does not out-claim the answer ──────────────────────────

def test_the_recap_is_told_to_report_the_act_not_the_finding():
    """It is narration. This system already keeps narration and evidence apart
    everywhere else — the pane is labelled narration when it reaches a verifier
    — and the recap is the one place narration was allowed to carry a result."""
    s = recap._SYSTEM.lower()
    assert "do not" in s or "never" in s
    assert "number" in s or "result" in s or "finding" in s


def test_and_told_to_keep_a_condition_attached_to_its_number():
    """The exact failure: "0.0" survived and "when recomputed in float64
    without the cast" did not."""
    s = recap._SYSTEM.lower()
    assert "condition" in s or "qualif" in s or "hedge" in s


def test_a_recap_that_states_a_number_absent_from_the_answer_is_dropped():
    """Cheap and mechanical, and it catches the worst case — a figure the model
    produced rather than read. A recap is decoration; dropping one costs
    nothing, and printing an invented measurement costs the reader everything.
    """
    got = recap.vet("measured a max difference of 0.0 between the operators",
                    final_text="I ran both and the difference was 1.05e-07.")
    assert got is None


def test_a_recap_whose_numbers_are_all_in_the_answer_survives():
    got = recap.vet("ran both operators; the difference was 1.05e-07",
                    final_text="I ran both and the difference was 1.05e-07.")
    assert got == "ran both operators; the difference was 1.05e-07"


def test_a_recap_with_no_numbers_at_all_survives():
    """The shape we want: what was done, not what it came to."""
    got = recap.vet("compared the two CASSI forward operators by running them",
                    final_text="… long answer …")
    assert got is not None


def test_a_version_or_a_path_is_not_a_measurement(  ):
    """`float64`, `8x8x4`, `coded.py:118` — a recap that named a file and line
    would otherwise be thrown away for looking like a claim."""
    got = recap.vet("read coded.py:118 and forward.py:29 in float64",
                    final_text="the cast is at coded.py:118; forward.py:29 keeps float64")
    assert got is not None


# ── 2. a measured criterion names where the number will be ────────────

def test_a_criterion_claiming_a_measurement_is_flagged():
    """Late is the problem, not the refusal — the verifier already says this,
    after the work. Reported at collection it costs one edit.

    A READ rather than a raise, and that placement is the whole lesson: put on
    `Phase` it also rejected the SEED plan, because `pl.draft()` writes criteria
    from the goal and any goal mentioning a benchmark tripped it. The system
    arguing with its own draft is not a check, it is a wall in the wrong place.
    """
    plan = pl.parse("# g\n\n## Phase 1 — compare them\n"
                    "Verified when: the max absolute difference is measured and reported\n")
    assert pl.needs_artefacts(plan) == ["compare them"]


def test_naming_the_artefact_satisfies_it():
    plan = pl.parse("# g\n\n## Phase 1 — compare them\n"
                    "Verified when: compare.py is run and its output saved to "
                    "compare-out.txt, showing the max absolute difference\n")
    assert pl.needs_artefacts(plan) == []


def test_a_criterion_that_claims_nothing_measured_is_left_alone():
    """Narrow on purpose. Most criteria are not measurements, and a check that
    argued with all of them would be worked around rather than satisfied."""
    plan = pl.parse("# g\n\n## Phase 1 — state it\n"
                    "Verified when: the report states the mask convention in words\n")
    assert pl.needs_artefacts(plan) == []


def test_the_seed_plan_is_never_argued_with():
    """`pl.draft()` builds the stub the session is asked to improve. It tripped
    the first version of this rule for any goal containing "benchmark", which
    took out fifteen tests and would have taken out every real run."""
    from ai4science.harness.agents.sarsi import worker
    d = worker.Directive(agent_id="sarsi-worker", goal="produce the benchmark numbers")
    assert pl.draft(d) is not None


def test_the_existing_no_criterion_refusal_is_unchanged():
    with pytest.raises(pl.BadPlan, match="Verified when"):
        pl.Phase(title="do the thing", verified_when="")


def test_it_names_the_phase_so_the_owner_can_act_on_it():
    """A finding that does not say which phase is a finding nobody can act on."""
    plan = pl.parse("# g\n\n## Phase 1 — fine\n"
                    "Verified when: report.md says so\n\n"
                    "## Phase 2 — measure it\n"
                    "Verified when: report the measured PSNR\n")
    assert pl.needs_artefacts(plan) == ["measure it"]


# ── the bare launch passes every parameter, or none of them work ──────

def test_the_bare_launch_passes_every_chat_parameter():
    """`ai4science` with no arguments calls `chat()` DIRECTLY, so any parameter
    it omits keeps its `typer.Option(...)` sentinel instead of the option's
    default. The file says so in a comment — and then `writable` was added and
    not added here, so `list(writable or [])` got an `OptionInfo`, which is
    truthy and not iterable.

    The result was the whole bare launch dying with
    `[tui] worker error: TypeError: 'OptionInfo' object is not iterable`, on the
    commonest entry point there is. A comment warning about a trap does not
    stop anyone walking into it; this does.
    """
    import inspect, re as _re
    from pathlib import Path as _P
    from ai4science.commands import chat as chat_cmd
    src = (_P(__file__).resolve().parents[2] / "ai4science/cli.py").read_text()
    call = src[src.index("chat_cmd.chat("):]
    call = call[:call.index("\n        except")]
    passed = set(_re.findall(r"(\w+)\s*=", call))
    expected = set(inspect.signature(chat_cmd.chat).parameters)
    assert not (expected - passed), (
        "the bare launch omits %s — each reaches the code as an OptionInfo"
        % sorted(expected - passed))
