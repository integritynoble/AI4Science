"""`EC` — scan the screen for failure signatures.

Deterministic: a literal match, no model call, so nothing can be talked into a
finding or out of one.

**It reports; it never rules.** A scan that matches nothing means *no signature
matched*, not *the work is good* — most ways of being wrong leave no trace. So
there is no API here for a positive verdict, and an empty scan renders as an
empty string rather than as reassurance.
"""
import pytest

from ai4science.harness.agents.sarsi import resultcheck as rc


TRACEBACK = """\
Traceback (most recent call last):
  File "run.py", line 12, in <module>
    main()
ValueError: no such column
"""

PYTEST_FAIL = """\
FAILED tests/test_export.py::test_rows - assert 3 == 1204
1 failed, 12 passed in 0.44s
"""

CONFLICT = """\
<<<<<<< HEAD
rows = 1204
=======
rows = 3
>>>>>>> feature
"""

CLEAN = """\
  Done. Wrote export.csv with 1,204 rows.
❯
"""


# ── what it finds ─────────────────────────────────────────────────────

def test_a_traceback_is_found():
    found = rc.scan(TRACEBACK)
    assert found and found[0].kind == "traceback"


def test_a_failing_test_is_found():
    assert any(f.kind == "test-failure" for f in rc.scan(PYTEST_FAIL))


def test_an_unmerged_conflict_is_found():
    assert any(f.kind == "merge-conflict" for f in rc.scan(CONFLICT))


def test_a_finding_carries_the_line_it_matched():
    assert "ValueError" in rc.scan(TRACEBACK)[0].line or \
        "Traceback" in rc.scan(TRACEBACK)[0].line


# ── what it must not find ─────────────────────────────────────────────

def test_a_clean_screen_finds_nothing():
    assert rc.scan(CLEAN) == []


def test_prose_is_not_evidence():
    """`fix the FAILED test` is an instruction, not a failure."""
    assert rc.scan("Next, please fix the FAILED test in test_export.py") == []


def test_a_sentence_about_an_error_is_not_an_error():
    assert rc.scan("I will check whether this raises a ValueError.") == []


def test_the_words_alone_do_not_match_without_their_shape():
    assert rc.scan("traceback") == []
    assert rc.scan("there was a conflict about the design") == []


# ── it reports, it never rules ────────────────────────────────────────

def test_there_is_no_positive_verdict_api():
    """Only the verifier may rule. Nothing here can declare success."""
    assert not hasattr(rc, "passed")
    assert not hasattr(rc, "ok")


def test_an_empty_scan_renders_as_nothing_not_as_reassurance():
    assert rc.render([]) == ""


def test_findings_render_for_the_composer():
    text = rc.render(rc.scan(PYTEST_FAIL))
    assert "test-failure" in text and "test_rows" in text


# ── de-duplication, so one traceback is not a stream ──────────────────

def test_the_same_error_twice_is_one_finding():
    assert len(rc.scan(TRACEBACK + TRACEBACK)) == len(rc.scan(TRACEBACK))


def test_different_errors_are_kept_apart():
    kinds = {f.kind for f in rc.scan(TRACEBACK + PYTEST_FAIL)}
    assert kinds == {"traceback", "test-failure"}
